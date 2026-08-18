# Legacy diagnostics

Three scripts from before the closed-loop rewrite. They scrape the DOM, which nothing
else in this project does any more — `utils/dashboard_state.py` reads the state the
page renders itself from instead.

They are kept for one job: **selector archaeology after a Microsoft redesign.** When
the parser stops finding what it expects, the DOM is what you have to go back to, and
these already know how to walk it.

They must be run as modules from the repository root, because they
`from config import …` and `config.py` lives there:

```bash
uv run python -m legacy.scientific_diagnostics   # points/task states/claim buttons → diagnostics_report.json
uv run python -m legacy.step_by_step_debugger    # interactive walkthrough, pauses and highlights at each step
uv run python -m legacy.debug_task1              # screenshot dashboard, list every Daily set card found
```

Running them as file paths (`uv run python legacy/debug_task1.py`) fails on the
`config` import — `sys.path[0]` becomes `legacy/` rather than the root.

> [!CAUTION]
> All three drive a real browser against the real account, and
> `scientific_diagnostics` writes `diagnostics_report.json`, which contains the point
> balance. It is git-ignored, but it lands on disk. For an everyday "what does today
> look like?", use `uv run python rewards_bot.py --dry-run` — it is read-only and
> costs nothing.
