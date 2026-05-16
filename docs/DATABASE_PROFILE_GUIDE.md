# Database Profile Guide

## Required Files

Mandatory:

- `profile.yaml`
- `schema.generated.yaml`

Common optional/managed files:

- `relationships.yaml`
- `tables/*.yaml`
- `examples.yaml`
- `eval_questions.yaml`
- `security_policy.yaml`
- `sql_style.yaml`
- `business_rules.yaml`
- `glossary.yaml`
- `metrics.yaml`

## Security Policy Notes

`security_policy.yaml` controls runtime SQL gating:

- `allowed_schemas` / `allowed_tables`
- `blocked_schemas` / `blocked_tables`
- `blocked_sql_features`
- `row_filters` (group-scoped predicate requirements)
- `pii_columns`, `sensitive_columns`, `secret_columns`
- `masking_rules` (metadata today; runtime masking not yet enforced)

## Example Files

- `examples.yaml`: training/retrieval examples used by tools/context
- `eval_questions.yaml`: held-out evaluation set for benchmark only

## Validation

```powershell
python scripts/validate_profile.py --profile dbnwind
python scripts/benchmark_questions.py --profile dbnwind
```
