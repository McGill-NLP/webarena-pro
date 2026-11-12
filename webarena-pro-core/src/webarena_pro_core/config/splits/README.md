# Dev task configs

The Dev set contains **100 tasks**, stored only in `dev.json`. The individual
website `*.raw.json` files contain the **300 Test tasks**; there is no overlap.
Each task is one record containing its setup, intent, and evaluation DAG under
`eval`. The Dev bundle also retains its sampling provenance.

Run `webarena-pro run --split dev`. Add `--list` to preview the tasks.

`load_task_configs(split="dev")` loads this bundle directly.
`load_raw_tasks("path/to/dev.json")` also reads its embedded evaluations;
no companion file, copying, or renaming is needed.
