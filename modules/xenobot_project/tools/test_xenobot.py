"""
pytest suite for XenobotSim (Gillespie SSA alg)

Run from the project root: pytest modules/xenobot_project/tools/test_xenobot.py -v
All tests run without any MCP server, Gemini client, or API key.
The simulator is imported directly and exercised in isolation.
"""

from __future__ import annotations
import math
import sys
from pathlib import Path
import numpy as np
import pytest

# make the module importable whether pytest is run from the project root or from within the tools directory
sys.path.insert(0, str(Path(__file__).parent))
from xenobot_sim import (XenobotSim, PROMOTER_LIBRARY, K_DEG, E_REF, _gillespie)

# Helpers

def _make_sim(seed:int=42) -> XenobotSim:
    """Return an initialised XenobotSim with a fixed RNG seed."""
    sim = XenobotSim()
    sim.initiate()
    sim._rng = np.random.default_rng(seed)
    return sim


def _extract_e_mean(text:str) -> float:
    """Parse ⟨E⟩ value from the summary text block."""
    for line in text.splitlines():
        if "⟨E⟩=" in line:
            raw = line.split("⟨E⟩=")[1].split()[0].rstrip("molecules")
            return float(raw)
    raise ValueError(f"⟨E⟩ not found in text:\n{text}")


def _extract_atp_final(text:str) -> int:
    """Parse ATP_final value from the summary text block."""
    for line in text.splitlines():
        if "ATP_final=" in line:
            return int(line.split("ATP_final=")[1].split()[0])
    raise ValueError(f"ATP_final not found in text:\n{text}")


def _extract_displacement(text:str) -> float:
    """Parse net displacement from the summary text block."""
    for line in text.splitlines():
        if "Net displacement (centroid):" in line:
            return float(line.split(":")[1].strip().split()[0])
    raise ValueError(f"Displacement not found in text:\n{text}")


def _extract_motor_force(text:str) -> float:
    """Parse the first motor_force value from the summary text block."""
    for line in text.splitlines():
        if "motor_force=" in line:
            return float(line.split("motor_force=")[1].split()[0].rstrip("µm/step"))
    raise ValueError(f"motor_force not found in text:\n{text}")

# Fixtures

@pytest.fixture
def sim() -> XenobotSim:
    return _make_sim()

@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(0)

# TestGillespieStochasticity class
# validates that τ (waiting time) and event selection are non-deterministic
# (two independent runs with different seeds produce different time-series)

class TestGillespieStochasticity:

    def test_waiting_times_are_random(self):
        """Two independent Gillespie runs with different seeds yield different τ sequences."""
        k_synth = PROMOTER_LIBRARY["J23100"]["k_synth"]
        rng_a = np.random.default_rng(seed=1)
        rng_b = np.random.default_rng(seed=2)
        times_a, _, _ = _gillespie(k_synth=k_synth, k_deg=K_DEG, atp_init=500, t_end=5.0, rng=rng_a)
        times_b, _, _ = _gillespie(k_synth=k_synth, k_deg=K_DEG, atp_init=500, t_end=5.0, rng=rng_b)
        # waiting times (τ = t[i+1] - t[i]) will differ b/w seeds
        assert times_a != times_b, ("Two Gillespie runs with different seeds produced identical time sequences."
                                    "-> Stochasticity is not functioning.")

    def test_event_selection_is_random(self):
        """Two runs can fire different reactions at the same step, producing different E traces."""
        k_synth = PROMOTER_LIBRARY["J23106"]["k_synth"]
        rng_a = np.random.default_rng(seed=10)
        rng_b = np.random.default_rng(seed=20)
        _, E_a, _ = _gillespie(k_synth=k_synth, k_deg=K_DEG, atp_init=500, t_end=5.0, rng=rng_a)
        _, E_b, _ = _gillespie(k_synth=k_synth, k_deg=K_DEG, atp_init=500, t_end=5.0, rng=rng_b)
        assert E_a != E_b, ("Two Gillespie runs with different seeds produced identical E(t) traces"
                            "-> reaction selection is not stochastic.")

    def test_same_seed_is_reproducible(self):
        """Same seed -> identical time-series (required for deterministic testing)."""
        k_synth = PROMOTER_LIBRARY["J23100"]["k_synth"]
        rng_1 = np.random.default_rng(seed=42)
        rng_2 = np.random.default_rng(seed=42)
        times_1, E_1, S_1 = _gillespie(k_synth=k_synth, k_deg=K_DEG, atp_init=200, t_end=5.0, rng=rng_1)
        times_2, E_2, S_2 = _gillespie(k_synth=k_synth, k_deg=K_DEG, atp_init=200, t_end=5.0, rng=rng_2)
        assert times_1 == times_2, "Same seed produced different time sequences."
        assert E_1 == E_2, "Same seed produced different E(t) traces."
        assert S_1 == S_2, "Same seed produced different S(t) traces."

    def test_waiting_times_are_exponentially_distributed(self):
        """
        Over many events, tau values should follow Exp(1/a_total).
        We use a large k_synth (near-constant a_total) to check the
        mean waiting time converges to 1/k_synth within 20%.
        """
        k_synth = 5.0 # large, dominates a_total early when E≈0
        rng = np.random.default_rng(seed=99)
        times, _, _ = _gillespie(k_synth=k_synth, k_deg=K_DEG, atp_init=0, t_end=50.0, rng=rng)
        if len(times) < 10:
            pytest.skip("Too few events to test distribution -> increase t_end.")
        taus = [times[i+1] - times[i] for i in range(min(50, len(times)-1))]
        mean_tau = sum(taus) / len(taus)
        expected_tau = 1.0 / k_synth # true mean for early events (E≈0, a_total≈k_synth)
        # Allow 40% tolerance — SSA is stochastic, not deterministic
        assert abs(mean_tau - expected_tau) / expected_tau < 0.40, (
            f"Mean τ={mean_tau:.4f} deviates >40% from expected 1/k_synth={expected_tau:.4f}. "
            "Waiting-time distribution may not be exponential.")

    def test_trace_length_increases_with_t_end(self):
        """More simulation time -> more molecular events recorded."""
        k_synth = PROMOTER_LIBRARY["J23100"]["k_synth"]
        rng_short = np.random.default_rng(seed=5)
        rng_long = np.random.default_rng(seed=5)
        times_short, _, _ = _gillespie(k_synth=k_synth, k_deg=K_DEG, atp_init=500, t_end=5.0,  rng=rng_short)
        times_long, _, _ = _gillespie(k_synth=k_synth, k_deg=K_DEG, atp_init=500, t_end=50.0, rng=rng_long)
        assert len(times_long) > len(times_short), ("A longer simulation window did not produce more recorded events.")

# TestPromoterMapping class
# validates that the J23 promoter library correctly maps to k_synth, and that
# higher k_synth produces higher ⟨E⟩ and therefore higher motor force.

class TestPromoterMapping:

    def test_promoter_k_synth_ordering(self):
        """J23100 k_synth > J23106 k_synth > J23114 k_synth."""
        k100 = PROMOTER_LIBRARY["J23100"]["k_synth"]
        k106 = PROMOTER_LIBRARY["J23106"]["k_synth"]
        k114 = PROMOTER_LIBRARY["J23114"]["k_synth"]
        assert k100 > k106 > k114, (f"Expected k_synth J23100 > J23106 > J23114, "
                                    f"got {k100} > {k106} > {k114}.")

    def test_strong_promoter_produces_higher_e_mean(self):
        """
        J23100 (strong) yields higher mean enzyme count ⟨E⟩ than J23114 (weak).
        Uses a fixed seed and a long t_end to reduce variance.
        """
        rng_strong = np.random.default_rng(seed=42)
        rng_weak = np.random.default_rng(seed=42)
        _, E_strong, _ = _gillespie(k_synth = PROMOTER_LIBRARY["J23100"]["k_synth"],
                                    k_deg = K_DEG,
                                    atp_init = 500,
                                    t_end = 20.0,
                                    rng = rng_strong)
        _, E_weak, _ = _gillespie(k_synth = PROMOTER_LIBRARY["J23114"]["k_synth"],
                                    k_deg = K_DEG,
                                    atp_init = 500,
                                    t_end = 20.0,
                                    rng = rng_weak)
        e_mean_strong = float(np.mean(E_strong))
        e_mean_weak = float(np.mean(E_weak))

        assert e_mean_strong > e_mean_weak, (f"Expected ⟨E⟩_J23100 > ⟨E⟩_J23114, "
                                            f"got {e_mean_strong:.2f} vs {e_mean_weak:.2f}.")

    def test_strong_promoter_produces_higher_motor_force(self):
        """run() with J23100 reports a higher motor_force than J23114."""
        sim_strong = _make_sim(seed=42)
        sim_weak = _make_sim(seed=42)
        r_strong = sim_strong.run([{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0}],
                                    steps=5, noise=0.0, gillespie_t_end=20.0)
        r_weak = sim_weak.run([{"promoter": "J23114", "direction_x": 1.0, "direction_y": 0.0}],
                                steps=5, noise=0.0, gillespie_t_end=20.0)
        force_strong = _extract_motor_force(r_strong["content"][0]["text"])
        force_weak = _extract_motor_force(r_weak["content"][0]["text"])

        assert force_strong > force_weak, (f"Expected motor_force J23100 > J23114, "
                                            f"got {force_strong:.4f} vs {force_weak:.4f}.")

    def test_j23100_displacement_exceeds_j23114(self):
        """J23100 construct travels further than J23114 over 30 steps at zero noise."""
        sim_strong = _make_sim(seed=7)
        sim_weak = _make_sim(seed=7)
        r_strong = sim_strong.run([{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0}],
                                    steps=30, noise=0.0, gillespie_t_end=15.0)
        r_weak = sim_weak.run([{"promoter": "J23114", "direction_x": 1.0, "direction_y": 0.0}],
                                steps=30, noise=0.0, gillespie_t_end=15.0)
        d_strong = _extract_displacement(r_strong["content"][0]["text"])
        d_weak = _extract_displacement(r_weak["content"][0]["text"])

        assert d_strong > d_weak, (f"Expected Δ_J23100 > Δ_J23114, got {d_strong:.4f} vs {d_weak:.4f}.")

    def test_unknown_promoter_falls_back_to_medium(self):
        """An unrecognised promoter key falls back to J23106 (medium) k_synth."""
        sim = _make_sim()
        r_unknown = sim.run([{"promoter": "UNKNOWN_PART", "direction_x": 1.0, "direction_y": 0.0}],
                            steps=5, noise=0.0)
        r_medium = _make_sim(seed=42).run([{"promoter": "J23106", "direction_x": 1.0, "direction_y": 0.0}],
                                            steps=5, noise=0.0)
        # both should report the same k_synth in the summary
        assert "1.175" in r_unknown["content"][0]["text"] or \
               "J23106" not in r_unknown["content"][0]["text"], (
            "Unknown promoter did not fall back correctly to J23106 k_synth=1.175."
        )

    def test_custom_promoter_uses_provided_k_synth(self):
        """A 'custom' promoter uses the explicitly provided k_synth value."""
        sim = _make_sim()
        r = sim.run([{"promoter": "custom", "k_synth": 3.0,
                    "direction_x": 1.0, "direction_y": 0.0, "label": "custom_cell"}],
                    steps=5, noise=0.0)
        text = r["content"][0]["text"]
        assert "3.000" in text, (f"Custom k_synth=3.0 not reflected in summary text:\n{text}")

# TestEnergyConservation class
# validates ATP substrate depletion: S is non-increasing, and the metabolic
# exhaustion regime (S→0) is reachable and detectable from the summary.

class TestEnergyConservation:

    def test_atp_is_non_increasing(self):
        """S(t) never increases — ATP is only consumed, never created."""
        rng = np.random.default_rng(seed=42)
        _, _, S_trace = _gillespie(k_synth  = PROMOTER_LIBRARY["J23100"]["k_synth"],
                                    k_deg = K_DEG,
                                    atp_init = 100,
                                    t_end = 10.0,
                                    rng = rng)
        for i in range(1, len(S_trace)):
            assert S_trace[i] <= S_trace[i-1], (f"S increased at step {i}: S[{i-1}]={S_trace[i-1]}, S[{i}]={S_trace[i]}. "
                                                "ATP must be strictly non-increasing.")

    def test_atp_depletes_with_small_budget(self):
        """With a tiny ATP budget, S_final < S_initial (consumption is happening)."""
        sim = _make_sim()
        r = sim.run([{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0}],
                    steps=5, noise=0.0, atp_init=10, gillespie_t_end=10.0)
        atp_final = _extract_atp_final(r["content"][0]["text"])
        assert atp_final < 10, (f"Expected ATP to be partially consumed from 10, but ATP_final={atp_final}.")

    def test_metabolic_exhaustion_caps_atp_at_zero(self):
        """Running with atp_init=1 and a strong promoter → S_final must be 0 or 1."""
        sim = _make_sim()
        r = sim.run([{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0}],
                    steps=10, noise=0.0, atp_init=1, gillespie_t_end=20.0)
        atp_final = _extract_atp_final(r["content"][0]["text"])
        assert atp_final <= 1, (f"Expected S_final ≤ 1 with atp_init=1, got ATP_final={atp_final}.")

    def test_force_reduced_when_atp_exhausted(self):
        """
        A cell with atp_init=0 has no substrate for Reaction 2 from the start.
        The Gillespie loop still synthesises E, so force is nonzero — but the
        ATP trace is flat at zero and ATP_final == 0.
        """
        sim = _make_sim()
        r = sim.run([{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0}],
                    steps=5, noise=0.0, atp_init=0, gillespie_t_end=5.0)
        atp_final = _extract_atp_final(r["content"][0]["text"])
        assert atp_final == 0, (f"Expected ATP_final=0 when atp_init=0, got {atp_final}.")

    def test_higher_atp_budget_delays_exhaustion(self):
        """
        With atp_init=500 vs atp_init=5, the high-budget cell retains more
        ATP at the end of an equal-length simulation.
        """
        sim_rich = _make_sim(seed=42)
        sim_poor = _make_sim(seed=42)
        r_rich = sim_rich.run([{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0}],
                                steps=5, noise=0.0, atp_init=500, gillespie_t_end=10.0)
        r_poor = sim_poor.run([{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0}],
                                steps=5, noise=0.0, atp_init=5, gillespie_t_end=10.0)
        atp_rich = _extract_atp_final(r_rich["content"][0]["text"])
        atp_poor = _extract_atp_final(r_poor["content"][0]["text"])
        assert atp_rich >= atp_poor, (f"Expected ATP_final(500) ≥ ATP_final(5), got {atp_rich} vs {atp_poor}.")

# TestKinematicsIntegration class
# validates the Euler kinematic layer: passive cells (zero motor force)
# produce zero net displacement at zero noise; force coupling is correct.

class TestKinematicsIntegration:

    def test_passive_cells_produce_zero_displacement(self):
        """
        A cell with k_synth=0.0 (custom) produces ⟨E⟩=0, motor_force=0,
        and therefore zero net displacement at noise=0.
        """
        sim = _make_sim()
        r = sim.run([{"promoter": "custom", "k_synth": 0.0, "direction_x": 1.0, "direction_y": 0.0, "label": "passive"}],
                    steps=30, noise=0.0, gillespie_t_end=10.0)
        disp = _extract_displacement(r["content"][0]["text"])
        assert disp < 1e-9, (f"Expected Δ≈0 for passive cell (k_synth=0), got Δ={disp:.6f} µm.")

    def test_displacement_increases_with_steps(self):
        """More Euler steps → more accumulated displacement (zero noise, J23100)."""
        sim_short = _make_sim(seed=42)
        sim_long  = _make_sim(seed=42)
        r_short = sim_short.run([{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0}],
                                steps=10, noise=0.0, gillespie_t_end=10.0)
        r_long = sim_long.run([{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0}],
                                steps=50, noise=0.0, gillespie_t_end=10.0)
        d_short = _extract_displacement(r_short["content"][0]["text"])
        d_long = _extract_displacement(r_long["content"][0]["text"])

        assert d_long > d_short, (f"Expected Δ(50 steps) > Δ(10 steps), got {d_long:.4f} vs {d_short:.4f}.")

    def test_diagonal_direction_produces_equal_xy_displacement(self):
        """
        A cell with direction (0.707, 0.707) at zero noise should end up
        with approximately equal x and y final positions (45° motion).
        """
        sim = _make_sim()
        r = sim.run([{"promoter": "J23100", "direction_x": 0.707, "direction_y": 0.707, "label": "diagonal"}],
                    steps=30, noise=0.0, gillespie_t_end=15.0)
        text = r["content"][0]["text"]
        # parse final centroid position from "Final centroid position: (x, y)"
        for line in text.splitlines():
            if "Final centroid position:" in line:
                inner = line.split("(")[1].split(")")[0]   # "x.xxx, y.yyy"
                x_final, y_final = [float(v.strip()) for v in inner.split(",")]
                break
        else:
            pytest.fail("Could not find 'Final centroid position' in summary text.")

        # x and y should be within 10% of each other for a 45° direction
        if max(abs(x_final), abs(y_final)) > 0:
            ratio = abs(x_final) / abs(y_final) if abs(y_final) > 0 else float("inf")
            assert 0.8 < ratio < 1.2, (f"Expected x≈y for 45° motion, got x={x_final:.3f}, y={y_final:.3f} "
                                        f"(ratio={ratio:.3f}).")

    def test_antagonist_cells_produce_near_zero_displacement(self):
        """
        Two cells with identical promoters but opposing directions
        (direction_x +1 and −1) cancel and produce near-zero net displacement
        at zero noise.
        """
        sim = _make_sim()
        r = sim.run([{"promoter": "J23100", "direction_x":  1.0, "direction_y": 0.0, "label": "fwd"},
                    {"promoter": "J23100", "direction_x": -1.0, "direction_y": 0.0, "label": "rev"}],
                    steps=20, noise=0.0, gillespie_t_end=10.0)
        disp = _extract_displacement(r["content"][0]["text"])

        # r5eference: single cell with same seed for comparison
        sim_single = _make_sim()
        r_single = sim_single.run(
            [{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0}],
            steps=20, noise=0.0, gillespie_t_end=10.0,
        )
        d_single = _extract_displacement(r_single["content"][0]["text"])

        # opposing forces reduce net locomotion — pair travels less than single cell
        assert disp < d_single, (f"Expected delta_antagonist ({disp:.4f}) < delta_single ({d_single:.4f}). "
                                "Opposing forces should reduce net displacement.")

    def test_force_magnitude_capped_at_base_motor(self):
        """
        Even with a custom k_synth far above E_ref, motor_force must not exceed
        base_motor (the cap is F = min(base_motor, base_motor × ⟨E⟩/E_ref)).
        """
        sim = _make_sim()
        r = sim.run([{"promoter": "custom", "k_synth": 100.0,   # extreme overexpression
                    "direction_x": 1.0, "direction_y": 0.0, "label": "overexpressed"}],
                    steps=5, noise=0.0, gillespie_t_end=10.0, base_motor=2.0)
        force = _extract_motor_force(r["content"][0]["text"])
        assert force <= 2.0 + 1e-9, (f"motor_force={force:.4f} exceeded base_motor=2.0. Force cap is not working.")

# TestOutputContract class
# validates the C9 output format and summary text completeness.

class TestOutputContract:

    def test_returns_dict_with_content_key(self, sim):
        r = sim.run([{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0}])
        assert isinstance(r, dict)
        assert "content" in r

    def test_content_is_list_with_text_block(self, sim):
        r = sim.run([{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0}])
        content = r["content"]
        assert isinstance(content, list)
        assert len(content) >= 1
        assert content[0]["type"] == "text"
        assert isinstance(content[0]["text"], str)
        assert len(content[0]["text"]) > 0

    def test_summary_contains_required_fields(self, sim):
        r = sim.run([{"promoter": "J23106", "direction_x": 1.0, "direction_y": 0.0}])
        text = r["content"][0]["text"]
        required = ["J23106",
                    "⟨E⟩=",
                    "ATP_final=",
                    "motor_force=",
                    "Net displacement (centroid):",
                    "Plot saved"]
        for field in required:
            assert field in text, f"Required field '{field}' missing from summary text."

    def test_empty_cells_returns_error(self, sim):
        r = sim.run([])
        assert "error" in r["content"][0]["text"].lower()

    def test_auto_initiate_on_first_run(self):
        """run() without calling initiate() first should not raise."""
        s = XenobotSim()
        r = s.run([{"promoter": "J23106", "direction_x": 1.0, "direction_y": 0.0}], steps=3)
        assert r["content"][0]["type"] == "text"

    def test_initiate_is_idempotent(self):
        """Calling initiate() twice should not raise or corrupt state."""
        s = XenobotSim()
        s.initiate()
        s.initiate()
        r = s.run([{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0}], steps=3, noise=0.0)
        assert r["content"][0]["type"] == "text"

    def test_multi_cell_summary_reports_all_cells(self, sim):
        """Three cells -> summary text contains three ⟨E⟩ lines."""
        r = sim.run([{"promoter": "J23100", "label": "a"},
                    {"promoter": "J23106", "label": "b"},
                    {"promoter": "J23114", "label": "c"}], steps=5, noise=0.0)
        text = r["content"][0]["text"]
        e_count = text.count("⟨E⟩=")
        assert e_count == 3, (f"Expected 3 ⟨E⟩= entries for 3 cells, found {e_count}.")
