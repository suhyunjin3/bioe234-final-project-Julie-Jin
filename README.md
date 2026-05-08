## BIOE 234 Final Project: CAD Tool for Xenobot Design
 
This CAD platform is a model for synthetic biologists designing xenobot locomotion.
A researcher specifies the promoters driving motor enzyme expression in each cell of a construct, and the simulator derives the resulting
phenotype: a spatial trajectory, a biochemical time series for each cell, and a metabolic consumption trace showing ATP flux over time. The tool allows researchers to select genetic parts and simulate it before fabrcation and see if a genetic construct is energetically efficient enough to reach a behavioral target before metabolic depletion.

## Motivation
 
Xenobots were first described by Kriegman, Blackiston, Levin, and Bongard (2020) as sculpted living machines assembled from frog stem cells through microsurgical
arrangement. The findings showed that the spatial configuration of two wild-type cell types (contracting cardiac progenitors and passive epithelial cells) was sufficient to determine emergent locomotive behavior, selected computationally by an evolutionary algorithm scoring designs on net displacement. The motor force was not a design variable.
 
Subsequent developments expanded xenobot functionality toward genetic programming.
Fluorescent reporters like GFP allowed confirming cell identity and viability within constructs. Molecular memory circuits with site-specific recombinase that permanently rearrange a DNA cassette after sensing an environmental stimulus, allowed xenobots to record and retain information about their chemical surroundings. These advances showed that xenobots can be a receptive platform to integrate synthetic circuits that affect cellular behavior.
 
This CAD tool is an extension to these findings, where instead of having a fixed cardiac contractility, it shows synthetic promoters driving the expression of motor proteins at a customizable level (low/medium/high). 

## Contractility as a Tunable Design Variable
 
Contractile force effector (MLCK) - The RhoA/ROCK → MLCK → myosin phosphorylation cascade is the downstream translator of gene expression into mechanical force. 

Graded MLCK regulation under conditional promoter control produces proportional changes in traction force and migration velocity (Surcel et al., 2015). In the simulator, motor enzyme `E` proxies for MLCK. The encoded relationship is: Promoter (J23100 → J23114)  →  k_synth  →  `⟨E⟩`  →  F_motor  →  change in displacement
 
## Simulation Engine
 
### Key Components
 
- Gillespie SSA (Gillespie, 1977) for stochastic biochemical simulation of enzyme production per cell - Propensity $a_j = k_j \times \prod[\text{reactants}]$; $a_j \propto$ Promoter Strength 
- Reaction network for elemental reactions governing [E] and [S] per cell - `∅ →[k_synth]→ E` · `E →[k_deg]→ ∅` · `E+S →[k_cat]→ E+∅` 
- ATP flux (Metabolic Trace) for first-order catalysis depleting substrate S - Propensity $a_2 = k_\text{cat} \times E$; S decrements per catalytic event
- Force coupling for mean enzyme count to motor force - $F = F_\text{base} \times \langle E \rangle / E_\text{ref}$ 
- Euler integrator for Kinematic trajectory from derived force - $x(t+1) = x(t) + F + \varepsilon,\quad \varepsilon \sim \mathcal{N}(0, \sigma^2)$ 

 
## Promoter Library
 
Anderson J23 series (iGEM Parts Registry), validated constitutive promoters spanning ~10× transcriptional activity range:
 
| Promoter | Relative strength | `k_synth` (mol/msec) | Typical `⟨E⟩` | Typical motor force |
|:---------|:-----------------:|:--------------------:|:--------------:|:-------------------:|
| J23100   | High  (1.00)      | 2.500                | ~9–12 mol      | ~0.9–1.2 µm/step   |
| J23106   | Medium (0.47)     | 1.175                | ~4–6 mol       | ~0.4–0.6 µm/step   |
| J23114   | Low (0.10)        | 0.250                | ~1–3 mol       | ~0.1–0.3 µm/step   |
 
Custom promoters: use `"promoter": "custom"` with an explicit `"k_synth"` value (e.g., from BRENDA or SABIO-RK kinetics databases).
 
## Workflow
 
Step 1 Specification: Select a promoter per cell and set the direction vector.
 
Step 2 Simulation via Gemini MCP client:
 
```
python client_gemini.py
 
You: Simulate a xenobot with a strong anterior motor (J23100) and a weak posterior
     cell (J23114). Show the ATP depletion traces.
```
 
Step 3 Analysis: Evaluate the Phenotypic and Metabolic Trace outputs against the design objective.
 
- Phenotypic Trace (Top panels) - cell trajectories + centroid with Δ annotation, compares net displacement across promoter configurations
- Metabolic Trace (Bottom panels) - `[E](t)` solid + `S(t)` dashed per cell, assesses ATP efficiency and detect metabolic exhaustion (`S → 0` while `[E]` is high)
- Ppromoter Strength per Micron - ratio of `k_synth` to `Δ`, minimized at optimal design
 
Trace interpretation:
 
- `[E]` at plateau, ATP slow decline - Healthy expression, motor near steady state
- `[E]` fluctuating near 0–3 mol - Weak promoter, stochastic force dropout
- ATP → 0, `[E]` sustained - Metabolic exhaustion, increase `atp_init` or reduce `k_cat`
- `[E]` saturates fast, ATP drops sharply - High metabolic cost, evaluate efficiency ratio

 
## Parameters
 
| Parameter | Type | Default | Description |
|:----------|:----:|:-------:|:------------|
| `cells` | `list[dict]` | — | Cell specifications (schema below) |
| `steps` | `int` | 50 | Kinematic integration steps |
| `noise` | `float` | 0.05 | Biological noise σ (µm/step) |
| `gillespie_t_end` | `float` | 10.0 | Biochemical sim window (msec) |
| `base_motor` | `float` | 2.0 | Max force at `⟨E⟩ = E_ref` (µm/step) |
| `atp_init` | `int` | 500 | Initial ATP molecules per cell |
 
Cell dict schema:
 
```python
{
    "promoter":    str,    # "J23100" | "J23106" | "J23114" | "custom"   (required)
    "direction_x": float,  # motor direction unit vector x               (default 1.0)
    "direction_y": float,  # motor direction unit vector y               (default 0.0)
    "label":       str,    # plot legend label                           (optional)
    "k_synth":     float,  # synthesis rate override for "custom"        (optional)
}
```
 
## Project Structure
 
```
modules/xenobot_project/
├── SKILL.md               # Gemini domain guidance — promoter library, design patterns
├── README.md              # This file
└── tools/
    ├── xenobot_sim.py     # XenobotSim — Gillespie SSA + Euler kinematic integrator
    ├── xenobot_sim.json   # C9 function wrapper — schema, typed I/O, MCP entry points
    ├── prompts.json       # Evaluation prompts with expected_tool and expected_args
    └── test_xenobot.py    # pytest validation suite (no server or API key required)
```
 
## Future Directions
- Inducible circuits - `k_synth` as a function of inducer concentration (e.g., Tet-OFF). oscillatory expression via the Repressilator (Elowitz & Leibler, 2000) for gait-like locomotion.
- Full Michaelis-Menten kinetics - Replace first-order ATP reaction with the elemental MM network (`E + S ⇌ ES → E + P`) for substrate-saturation effects and Kₘ-targeted enzyme engineering.
- Evolutionary design optimization - Use `run()` as a forward model in a Kriegman-style (2020) optimization loop to solve the inverse problem: minimize ATP cost for a target displacement.
- 3D morphology - Extend the kinematic layer to three dimensions; model the xenobot body as a spring graph for mechanical coupling between adjacent cells.
