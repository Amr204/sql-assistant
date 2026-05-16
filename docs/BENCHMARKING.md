# Benchmarking

## Inputs

- `profiles/<profile>/examples.yaml`
- `profiles/<profile>/eval_questions.yaml`

`eval_questions.yaml` is evaluation-only and is not seeded into memory.

## Run

```powershell
python scripts/benchmark_questions.py --profile dbnwind
```

## Outputs

- `reports/benchmark_results.json`
- `reports/benchmark_report.md`
- `reports/eval/benchmark_results.json`
- `reports/eval/benchmark_report.md`

## Current Static Checks

- `BN001` SQL parses as T-SQL
- `BN002` referenced tables exist
- `BN003` referenced columns exist (with alias resolution)
- `BN004` SQL policy outcome is correct
- `BN005` PII policy allows query (non-rejected items)
- `BN006` SQL overlaps `required_tables`
- `BN007` multi-table items include join-like structure
- `BN008` Arabic and English question presence
- `BN009` SQL not empty
- `BN010` eval `expected_tables` exist
- `BN011` `must_reject` eval items without reference SQL are explicitly marked

## Phase 10 Target

For `dbnwind` examples, benchmark now passes `150/150`.
