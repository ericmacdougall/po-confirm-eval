# Historical reproduction snapshot

`experiment-08f8afc.zip` is an immutable full Git snapshot of
08f8afc92e2b39b987511e5d24302666bf34df7f, before the final parse-accounting
review finding. Its SHA is pinned in `accounting/original.py`.

The source under root `src/` and `tests/` is the same frozen historical source.
Its parse-failure gate has a known defect. Use `python3 rerun.py` from the root
for original replay plus the separate corrected accounting. Future extraction
code and final parse/schema status live under `accounting/`. No original
preregistration, prediction, output or error was retroactively replaced.
