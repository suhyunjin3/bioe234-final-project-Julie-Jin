# xenobot_project: Gemini Tool Reference

Tool: `simulate_xenobot_kinematics`
Process: Gillespie SSA → Euler integration → Phenotypic + Metabolic Traces

## Promoter Lookup Table

| Key | Strength | `k_synth` | Typical `⟨E⟩` | Motor force |
|:----|:--------:|:---------:|:--------------:|:-----------:|
| `"J23100"` | High | 2.500 | ~9–12 mol | ~0.9–1.2 µm/step |
| `"J23106"` | Medium | 1.175 | ~4–6 mol | ~0.4–0.6 µm/step |
| `"J23114"` | Low | 0.250 | ~1–3 mol | ~0.1–0.3 µm/step |
| `"custom"` | User-defined | set `k_synth` explicitly | — | — |

Direction is a unit vector (use `cos(θ)` / `sin(θ)` for angled motion)

## Design Patterns

- Linear Walk - all cells share the same promoter and direction `(1.0, 0.0)`. Net force is symmetric (displacement scales linearly with cell count and promoter strength).
- Diagonal Drift - set `direction_x = 0.707`, `direction_y = 0.707` for 45 degree motion. Mix promoter strengths to bias the drift angle.
- Asymmetric Curve - anterior cell J23100, posterior cell J23114 (same direction). Unequal forces produce a curved centroid trajectory.
- Metabolic Constraint - use J23114 with high `atp_init` (1000+) for long-duration, low-force locomotion without exhaustion. Use J23100 with low `atp_init` (50–100) to demonstrate metabolic depletion.
- Double Promoter - two cells both set to J23100, same direction. Net motor vector doubles (use to show force superposition).

## Gillespie Logic — What to Tell the User

The biochemical layer is stochastic. Tell the user:

- Noisy trajectories are correct. They reflect real gene expression intermittency at low molecule counts, not simulation errors.
- J23114 trajectories look most irregular because `⟨E⟩ ≈ 2`, so the enzyme count frequently drops to zero (no force produced during those intervals).
- `noise=0.0` removes kinematic noise** but the Gillespie layer remains stochastic — trajectories are still not perfectly straight.
- Metabolic exhaustion looks like ATP trace → 0 while `[E]` trace stays elevated. The cell has enzyme but no fuel. Fix: increase `atp_init` or swap to a weaker promoter.

## Parameter Defaults

| Parameter | Default | When to change |
|:----------|:-------:|:---------------|
| `steps` | 50 | Increase for longer displacement runs |
| `noise` | 0.05 | Set 0.0 for deterministic comparison |
| `gillespie_t_end` | 10.0 | Increase to allow `[E]` to reach steady state |
| `base_motor` | 2.0 | Leave unchanged unless scaling force range |
| `atp_init` | 500 | Lower to demonstrate metabolic exhaustion |

## Sample Prompts (SOP)

1. Single strong motor, rightward:
```json
{"cells": [{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0, "label": "motor"}],
  "steps": 50,
  "noise": 0.05}
```

2. Promoter comparison -> strong vs. weak, zero noise:
```json
{"cells": [{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0, "label": "strong"},
            {"promoter": "J23114", "direction_x": 1.0, "direction_y": 0.0, "label": "weak"}],
  "steps": 50,
  "noise": 0.0}
```

3. Metabolic exhaustion demonstration:
```json
{"cells": [{"promoter": "J23100", "direction_x": 1.0, "direction_y": 0.0, "label": "exhausted"}],
  "steps": 50,
  "noise": 0.05,
  "atp_init": 30}
```

## Do Not Use This Tool For

- DNA sequence analysis → use `seq_basics` tools
- 3D spatial modeling or morphogenesis
- Wet-lab protocol guidance
