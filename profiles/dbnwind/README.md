# DBnwind Profile

This profile is generated from `data/input/Schema.sql` and hardened for runtime use.

## Included files

- `profile.yaml` / `schema.generated.yaml` / `relationships.yaml`
- `tables/*.yaml`
- `examples.yaml` (training/retrieval examples)
- `eval_questions.yaml` (evaluation only; never seeded to memory)
- `security_policy.yaml`
- `sql_style.yaml`
- `business_rules.yaml`
- `glossary.yaml`
- `metrics.yaml`

## Security defaults

- `SELECT` only
- blocked schemas: `sys`, `INFORMATION_SCHEMA`
- explicit `allowed_tables` list for DBnwind tables
- blocked SQL features list (e.g. `PIVOT`, `OPENJSON`, `FOR XML`, `FOR JSON`)
- group-based row filters for `finance` users
- masking rules are policy metadata; runtime masking is not yet enforced server-side

## Regeneration

```powershell
python scripts/generate_examples.py --profile dbnwind --overwrite
python scripts/benchmark_questions.py --profile dbnwind
```
