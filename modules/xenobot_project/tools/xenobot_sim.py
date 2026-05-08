"""
Xenobot Kinematics Simulator

Description: Simulates xenobot locomotion where motor force emerged from a
    biochemical simulation.

    Layer 1 Gillespie Stochastic Simulation Algorithm:
        - Models enzyme production inside each motor cell as a genetic circuit:
            DNA --[k_synth]--> DNA + E (promoter-driven synthesis)
            E --[k_deg]--> ∅ (first-order degradation)
        - species: E (enzyme molecules), S (substrate/ATP molecules)
        - promoter strength (J23100 / J23106 / J23114) sets k_synth
        (determines how many enzyme molecules accumulate over time)

    Layer 2 Euler Integration:
        The mean enzyme count ⟨E⟩ from Layer 1 drives cell force:
            motor_force = (E_mean / E_ref) * base_motor_strength
        This force is then integrated with Euler steps + noise to produce
        the 2D trajectory, exactly as in v1.

Input:
    cells (list[dict]): each dict must contain:
        - "promoter" (str): one of "J23100" (High), "J23106" (Medium), "J23114" (Low), or "custom".
        - "direction_x" (float): Unit direction component x (default 1.0).
        - "direction_y" (float): Unit direction component y (default 0.0).
        - "label" (str, optional): Display name.
        - "k_synth" (float, optional): Override synthesis rate (if promoter="custom").
    steps (int, optional): Kinematic integration steps (default 50).
    noise (float, optional): Gaussian noise in µm/step (default 0.05).
    gillespie_t_end (float, optional): Biochemical sim duration in msec (default 10.0).
    base_motor (float, optional): Max motor force µm/step at full enzyme load (default 2.0).
    atp_init (int, optional): Initial ATP substrate molecules (default 500).

Output:
    dict with a "content" list:
        [0] {"type": "text", "text": "<summary string including promoter strengths>"}
    Plot saved to modules/outputs/xenobot_TIMESTAMP.png

Tests:
    >>> sim = XenobotSim()
    >>> r = sim.run([{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0}])
    >>> assert "J23100" in r["content"][0]["text"]
    >>> assert "displacement" in r["content"][0]["text"].lower()

    >>> # strong promoter should produce more displacement than weak
    >>> r_strong = sim.run([{"promoter": "J23100"}], steps=20, noise=0.0)
    >>> r_weak   = sim.run([{"promoter": "J23114"}], steps=20, noise=0.0)
    >>> # summary text where E_mean is reported
"""

from __future__ import annotations

import math
import time as _time
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import numpy as np


# Promoter Library 
# k_synth values are proportional to the measured relative strengths
# J23100 = 1.00, J23106 = 0.47, J23114 = 0.10 per iGEM characterization
# units: molecules / msec (scaled to Gillespie simulation time).

PROMOTER_LIBRARY: dict[str, dict] = {"J23100": {"label": "J23100 (Strong)",
                                                "k_synth": 2.5, # ≈ 1.00 × 2.5
                                                "color":"#3FB950",
                                                "strength": "High"},
                                    "J23106": {"label": "J23106 (Medium)",
                                                "k_synth": 1.175,  # ≈ 0.47 × 2.5
                                                "color":"#E3B341",
                                                "strength": "Medium"},
                                    "J23114": {"label": "J23114 (Weak)",
                                                "k_synth": 0.25,   # ≈ 0.10 × 2.5
                                                "color":"#F85149",
                                                "strength": "Low"}}

# degradation rate constant (first-order): E → ∅
K_DEG: float = 0.1 # molecules / msec per molecule

# reference enzyme count: at this level, force = base_motor (full strength)
E_REF: float = 20.0 # molecules


# Gillespie SSA

def _gillespie(k_synth:float,
                k_deg:float,
                atp_init:int,
                t_end:float,
                rng:np.random.Generator) -> tuple[list[float], list[int], list[int]]:
    """
    First-reaction Gillespie SSA for a minimal enzyme production circuit:
        Reaction 0: ∅ --(k_synth)--> E (production, 0th-order)
        Reaction 1: E --(k_deg)--> ∅ (degradation, 1st-order)
        Reaction 2: E + S --(k_cat)--> E + ∅ (ATP consumption, catalysis)
    Returns (times, E_trace, S_trace) — lists of timepoints and molecule counts.
    Computes propensities, draws exponential waiting time, picks reaction
    proportional to propensity, updates state, advances time, and repeat.
    """
    # initial state
    E:int=0
    S:int=atp_init
    k_cat:float=0.05  # ATP consumption rate per enzyme molecule
    t:float=0.0
    times:list[float]=[t]
    E_trace:list[int]=[E]
    S_trace:list[int] =[S]

    while t < t_end:
        # Propensities
        # a0: synthesis (0th-order — DNA is constant, not a variable)
        # a1: degradation (1st-order in E)
        # a2: catalysis / ATP consumption (1st-order in E, capped by S)
        a0 = k_synth
        a1 = k_deg * E
        a2 = k_cat * E if S > 0 else 0.0
        a_total = a0 + a1 + a2

        if a_total == 0:
            break  # no reactions possible -> system is quiescent

        # Time to next reaction: exponential distribution
        tau = rng.exponential(1.0 / a_total)
        t += tau

        if t > t_end:
            break

        # which reaction fires? -> proportional to propensity
        r = rng.uniform(0, a_total)
        if r < a0: # reaction 0: synthesis -> E increases by 1
            E += 1
        elif r < a0 + a1: # reaction 1: degradation -> E decreases by 1 (if any)
            if E > 0:
                E -= 1
        else: # reaction 2: catalysis / ATP consumption
            if S > 0:
                S -= 1  # one ATP consumed per catalytic event

        times.append(t)
        E_trace.append(E)
        S_trace.append(S)

    return times, E_trace, S_trace


# Main simulator class

class XenobotSim:
    """
    Xenobot kinematics simulator with Gillespie biochemical engine.
    """

    def initiate(self) -> None:
        """Seed the RNG and set the ready flag."""
        self._rng = np.random.default_rng(seed=42)
        self._ready = True

    def run(self,
            cells:list[dict[str, Any]],
            steps:int=50,
            noise:float=0.05,
            gillespie_t_end:float=10.0,
            base_motor:float=2.0,
            atp_init:int=500) -> dict[str, Any]:
        """
        Run the coupled biochemical + kinematic simulation.

        Parameters:
            cells : list[dict]
                Each dict should have 'promoter' (str) and optionally
                'direction_x', 'direction_y', 'label', 'k_synth'.
            steps : int
                Kinematic Euler integration steps (default 50).
            noise : float
                Gaussian noise (µm/step) added each kinematic step (default 0.05).
            gillespie_t_end : float
                Duration of biochemical simulation in msec (default 10.0).
            base_motor : float
                Maximum motor force in µm/step at full enzyme expression (default 2.0).
            atp_init : int
                Initial ATP substrate molecule count (default 500).
        """
        if not getattr(self, "_ready", False):
            self.initiate()

        if not cells:
            return {"content": [{"type": "text", "text": "Error: 'cells' list must not be empty."}]}

        n = len(cells)

        # Layer 1 - run the Gillespie SSA to determine how many enzyme molecules each cell produces, 
        # then derive its motor force from [E].

        motor_vectors = np.zeros((n, 2)) # (n, 2) -> motor force per cell
        e_means = [] # mean [E] for each cell (for reporting)
        atp_finals = [] # final ATP for each cell
        biochem_traces = [] # (times, E_trace, S_trace) per cell

        for i, cell in enumerate(cells):
            promoter_key = cell.get("promoter", "J23100")

            if promoter_key == "custom":
                k_synth = float(cell.get("k_synth", PROMOTER_LIBRARY["J23100"]["k_synth"]))
            elif promoter_key in PROMOTER_LIBRARY:
                k_synth = PROMOTER_LIBRARY[promoter_key]["k_synth"]
            else:
                # unknown promoter key -> fall back to medium
                k_synth = PROMOTER_LIBRARY["J23106"]["k_synth"]

            times_g, E_trace, S_trace = _gillespie(k_synth=k_synth,
                                                    k_deg=K_DEG,
                                                    atp_init=atp_init,
                                                    t_end=gillespie_t_end,
                                                    rng=self._rng)
            biochem_traces.append((times_g, E_trace, S_trace))

            # mean enzyme count over the simulation
            e_mean = float(np.mean(E_trace)) if E_trace else 0.0
            e_means.append(e_mean)
            atp_finals.append(S_trace[-1] if S_trace else atp_init)

            # motor force scales with mean [E] relative to reference
            # (capped at base_motor to prevent runaway values)
            force_magnitude = min(base_motor, base_motor * (e_mean / E_REF))

            # Direction unit vector — defaults to rightward (1, 0)
            dx = float(cell.get("direction_x", 1.0))
            dy = float(cell.get("direction_y", 0.0))
            norm = math.hypot(dx, dy)

            if norm > 0:
                dx, dy = dx / norm, dy / norm

            motor_vectors[i] = [force_magnitude * dx, force_magnitude * dy]

        # net motor vector (vector sum across all cells)
        net_motor = motor_vectors.sum(axis=0)

        # Layer 2 - euler kinematic integration
        positions = np.zeros((n, steps+1, 2))
        for t in range(steps):
            noise_arr = self._rng.normal(0.0, noise, size=(n, 2))
            for i in range(n):
                positions[i, t+1] = (positions[i, t] + motor_vectors[i] + noise_arr[i])

        centroid = positions.mean(axis=0)   # (steps+1, 2)
        total_disp = float(np.linalg.norm(centroid[-1] - centroid[0]))

        # Plotting
        fig = plt.figure(figsize=(14, 9))
        fig.patch.set_facecolor("#0d1117")

        # grid layout: [traj_left | traj_right] on top, [biochem traces] below
        gs = fig.add_gridspec(2, n+1, hspace=0.42, wspace=0.38)
        ax_traj = fig.add_subplot(gs[0, :n])
        ax_cent = fig.add_subplot(gs[0, n])
        axs_bio = [fig.add_subplot(gs[1, i]) for i in range(n)]
        colors = cm.plasma(np.linspace(0.2, 0.9, n))

        # trajectory panel
        ax_traj.set_facecolor("#161b22")
        for i, c in enumerate(cells):
            label = c.get("label", f"cell_{i}")
            promoter_key = c.get("promoter", "J23100")
            pinfo = PROMOTER_LIBRARY.get(promoter_key, {})
            pstr  = pinfo.get("strength", "?")
            traj  = positions[i]
            ax_traj.plot(traj[:, 0], traj[:, 1], color=colors[i], lw=1.2, alpha=0.85,
                         label=f"{label} [{promoter_key}, {pstr}]")
            ax_traj.scatter(*traj[0],  color=colors[i], s=35, zorder=5, marker="o")
            ax_traj.scatter(*traj[-1], color=colors[i], s=65, zorder=5, marker="*")

        ax_traj.set_title("Cell Trajectories", color="white", fontsize=11, pad=8)
        ax_traj.set_xlabel("x (µm)", color="#8b949e")
        ax_traj.set_ylabel("y (µm)", color="#8b949e")
        ax_traj.tick_params(colors="#8b949e")
        for sp in ax_traj.spines.values():
            sp.set_edgecolor("#30363d")
        ax_traj.legend(fontsize=7, labelcolor="white", facecolor="#21262d", edgecolor="#30363d")

        # centroid panel
        ax_cent.set_facecolor("#161b22")
        ax_cent.plot(centroid[:, 0], centroid[:, 1], color="#58a6ff", lw=2)
        ax_cent.scatter(*centroid[0],  color="#3fb950", s=60, zorder=5, marker="o", label="start")
        ax_cent.scatter(*centroid[-1], color="#f85149", s=80, zorder=5, marker="*", label="end")
        ax_cent.annotate(f"Δ = {total_disp:.2f} µm",
                            xy=centroid[-1],
                            xytext=(0.05, 0.07),
                            textcoords="axes fraction",
                            color="#e3b341", fontsize=9,
                            arrowprops=dict(arrowstyle="->", color="#e3b341", lw=0.8))
        ax_cent.set_title("Centroid Trajectory", color="white", fontsize=11, pad=8)
        ax_cent.set_xlabel("x (µm)", color="#8b949e")
        ax_cent.set_ylabel("y (µm)", color="#8b949e")
        ax_cent.tick_params(colors="#8b949e")
        for sp in ax_cent.spines.values():
            sp.set_edgecolor("#30363d")
        ax_cent.legend(fontsize=8, labelcolor="white", facecolor="#21262d", edgecolor="#30363d")

        # biochemical trace panels (one per cell)
        for i, (ax_b, (times_g, E_trace, S_trace)) in enumerate(zip(axs_bio, biochem_traces)):
            ax_b.set_facecolor("#161b22")
            promoter_key = cells[i].get("promoter", "J23100")
            pinfo = PROMOTER_LIBRARY.get(promoter_key, {})
            pcolor = pinfo.get("color", "#58a6ff")

            # E trace
            ax_b.step(times_g, E_trace, where="post",
                      color=pcolor, lw=1.2, label="[E] enzyme")
            # S (ATP) trace -> right axis
            ax_b2 = ax_b.twinx()
            ax_b2.step(times_g, S_trace, where="post",
                       color="#8b949e", lw=0.9, alpha=0.6, linestyle="--",
                       label="[S] ATP")
            ax_b2.set_ylabel("ATP", color="#8b949e", fontsize=8)
            ax_b2.tick_params(colors="#8b949e", labelsize=7)
            ax_b2.spines["right"].set_edgecolor("#30363d")

            label_cell = cells[i].get("label", f"cell_{i}")
            ax_b.set_title(
                f"{label_cell}\n{pinfo.get('label', promoter_key)} | "
                f"⟨E⟩={e_means[i]:.1f} | force={float(np.linalg.norm(motor_vectors[i])):.2f} µm/step",
                color="white", fontsize=8, pad=4,
            )
            ax_b.set_xlabel("time (msec)", color="#8b949e", fontsize=8)
            ax_b.set_ylabel("[E] molecules", color=pcolor, fontsize=8)
            ax_b.tick_params(colors="#8b949e", labelsize=7)
            for sp in ax_b.spines.values():
                sp.set_edgecolor("#30363d")

            lines1, labels1 = ax_b.get_legend_handles_labels()
            lines2, labels2 = ax_b2.get_legend_handles_labels()
            ax_b.legend(lines1 + lines2, labels1 + labels2,
                        fontsize=7, labelcolor="white",
                        facecolor="#21262d", edgecolor="#30363d")

        fig.suptitle(
            f"Xenobot Simulation (Gillespie Engine): {n} cell(s), {steps} kinematic steps",
            color="white", fontsize=12, y=1.01,
        )

        # save plot
        output_dir = Path(__file__).parent.parent.parent / "outputs"
        output_dir.mkdir(exist_ok=True)
        filename = f"xenobot_{int(_time.time())}.png"
        out_path  = output_dir / filename
        fig.savefig(out_path, format="png", dpi=120,
                    bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)

        # Summary text
        cell_lines = []
        for i, cell in enumerate(cells):
            pkey = cell.get("promoter", "J23100")
            pinfo = PROMOTER_LIBRARY.get(pkey, {})
            label = cell.get("label", f"cell_{i}")
            force = float(np.linalg.norm(motor_vectors[i]))
            cell_lines.append(f"  [{i}] {label}  promoter={pkey} ({pinfo.get('strength','?')})"
                                f"  k_synth={pinfo.get('k_synth', cell.get('k_synth','?')):.3f}"
                                f"  ⟨E⟩={e_means[i]:.1f} molecules"
                                f"  ATP_final={atp_finals[i]}"
                                f"  motor_force={force:.3f} µm/step")

        summary = (f"Xenobot Gillespie simulation complete.\n"
                    f"  Cells: {n}, Kinematic steps: {steps}, Noise: {noise} µm\n"
                    f"  Gillespie t_end: {gillespie_t_end} msec, ATP_init: {atp_init}\n"
                    f"  Net motor vector: ({net_motor[0]:.3f}, {net_motor[1]:.3f}) µm/step\n"
                    f"  Net displacement (centroid): {total_disp:.4f} µm\n"
                    f"  Final centroid position: ({centroid[-1, 0]:.3f}, {centroid[-1, 1]:.3f}) µm\n"
                    f"\nCell biochemistry summary:\n"
                        + "\n".join(cell_lines)
                        + f"\n\n  Plot saved → {out_path.resolve()}")

        return {"content": [{"type": "text", "text": summary}]}
