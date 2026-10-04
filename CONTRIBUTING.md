# Contributing to API-WRAPPER

Start with a reproducible bug or a concrete user need. Search existing issues and pull requests before opening another report. Keep each change focused enough to review independently.

## Development checks

Use Python 3.12 and a virtual environment. Run these commands from the repository root:

```sh
python -m pip install -e ".[dev]"
ruff format --check .
ruff check .
mypy app
pytest -q
```

CI is the source of truth for additional platform checks. BridgeSync and AgentBench also exercise PostgreSQL and browser workflows; AgentBench runs the Docker sandbox. See `.github/workflows` for the exact setup. Never execute untrusted agent code through the trusted local runner.

## Bug reports and changes

Include reproduction steps, expected and actual behavior, environment versions and sanitized logs. Write a regression test for a behavioral fix and demonstrate that it fails before the fix and passes afterward. Link the issue from the pull request, explain the tradeoff and report the checks actually run. State skipped checks explicitly.

Do not commit credentials, private documents, customer data or generated runtime databases. Use synthetic fixtures and environment variables. For a security vulnerability, avoid publishing exploit details in a public issue; use GitHub private vulnerability reporting if enabled.

## Review

A reviewer should check correctness, edge cases, authorization boundaries, failure handling and test coverage. Respond to review comments with a change or a reasoned explanation. Obtain genuine independent review when available; passing CI does not establish that someone reviewed the code.
