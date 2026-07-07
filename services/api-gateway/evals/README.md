# ClozeHive eval harness

A golden-set evaluation of the **deterministic** parts of the AI pipeline, so
prompt and threshold changes can be *measured* instead of guessed. Runs with no
network, no LLM, and no database — a full run costs nothing.

## Suites

| Suite | Scores | Tunes |
|-------|--------|-------|
| `routing` | `model_router.route()` tier vs. an expected tier | `_ESCALATE_THRESHOLD` and the signal weights in `model_router.py` |
| `grounding` | `validate_chat_response()` + `score_response_quality()` — item removal, empty-outfit drop, hallucination_risk, hard fallback | the validator + the streaming/non-streaming grounding gates |

## Run it

```bash
cd services/api-gateway

python -m evals.runner                    # all suites, human-readable report
python -m evals.runner --suite routing    # one suite
python -m evals.runner --json out.json     # also emit machine-readable results
python -m evals.runner --min-pass 0.9      # exit 1 if any suite < 90% (CI gate)
```

The suites also run under pytest (`tests/evals/test_evals.py`) as a regression
guard: if you tune the router threshold and routing accuracy drops below the
floor, CI fails — update the dataset in the same change if the shift is intended.

## The workflow this enables

1. Change a threshold (e.g. `_ESCALATE_THRESHOLD`) or a prompt.
2. `python -m evals.runner --suite routing` — see accuracy move on labeled cases.
3. Keep the change only if the golden-set numbers improve.

## Datasets

Plain YAML under `datasets/`. Each `cases:` entry is one labeled example.

- **routing.yaml** — the per-turn signals the pipeline computes + `expected_tier`
  (`small` | `large` | `vision`). Grow toward 30–50 cases sampled from real
  `model_route` logs as traffic accumulates.
- **grounding.yaml** — a known `model_output` + `valid_item_ids` + an `expect`
  block (`should_fallback`, `min_outfits`, `max_outfits`, `max_hallucination_risk`,
  `items_removed`).

## Vision golden set (`evals/vision_golden.py`)

Extraction-quality scoring for the garment vision pipeline — the measurement
gate for any vision model/prompt change (e.g. the `vision_*` tiering config).
Unlike the suites above it *can* call the model:

```bash
python -m evals.vision_golden                    # score saved recordings (no network — CI-safe)
python -m evals.vision_golden --live             # call the vision model now
python -m evals.vision_golden --record           # live + snapshot responses for offline scoring
python -m evals.vision_golden --fn analyze_image # score the mini categorization tier
python -m evals.vision_golden --live --min-accuracy 0.8
```

Labeled cases live in `datasets/vision/labels.yaml` + `datasets/vision/images/`
(starter set is synthetic PIL renderings — deterministic, regenerable via
`python -m evals.datasets.vision.generate_starter_images`). Per-field scoring:
category (exact), colour/pattern (any-token family match), fit/material (only
when labeled — `null` on synthetic images since flat renderings can't ground
texture). **Grow it with real garment photos**: drop an image in `images/`, add
a case, and label fit/material — those are exactly the fields the
flagship-vs-mini tiering decision hinges on. `tests/evals/test_vision_golden.py`
guards dataset integrity and scorer logic in CI without network.

## Not covered yet (intentional)

The chat harness scores the deterministic scaffolding. It does **not** call the
LLM, so it can't judge answer *quality* (tone, correctness, styling taste). That
needs an online eval with a labeled prompt→response set and either an LLM-judge
or human grading — a good next step once the `$ai_generation` telemetry (already
emitting tokens/cost/tier per turn) has accumulated real traffic to sample from.
