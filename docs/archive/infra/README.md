# Archived · Prophet & LightGBM forecast scripts

These scripts were **removed from production in Sprint F5** because Prophet and LightGBM
models do not outperform the naive baseline (documented in F4-FIX1 audit).

## Files

- `run_forecast_prophet.py` — Databricks job submission for Prophet model
- `run_forecast_lightgbm.py` — Databricks job submission for LightGBM model

## History

- **F4-B**: Both scripts created and deployed alongside the evaluation pipeline.
- **F4-FIX1**: Audit determined Prophet and LightGBM predictions were not
  superior to the simple baseline (previous value carry-forward).
- **F5**: Both scripts moved here. `create_gold_workflow.py` no longer
  includes forecast tasks. The notebooks `20_forecast_prophet.py` and
  `21_forecast_lightgbm.py` were archived to `docs/archive/gold/`.

## Restoration

If a future evaluation proves Prophet or LightGBM useful, restore by:

1. Moving both `.py` files back to `infra/`
2. Adding forecast tasks back to `infra/create_gold_workflow.py`
3. Running `python infra/create_gold_workflow.py` to update Databricks jobs
