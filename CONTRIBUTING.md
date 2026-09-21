# Contributing to NoCaptcha

Thanks!

1. Fork + `git checkout -b feat/my-solver`
2. `pip install -e ".[all,dev]"`
3. Add your solver in `src/nocaptcha/solvers/` by subclassing `BaseSolver`, register it in `REGISTRY`.
4. Add a test in `tests/`.
5. `pytest` + `ruff check src` must pass.
6. PR with example + docs.

Rules: 100% local by default, human gestures in the browser, models < 100 MB preferred (ONNX).
Only automate sites you own or that explicitly allow it.
