# WeatherCal — Project Rules

## Testing

- Every code change MUST include corresponding tests
- Unit tests for new/modified functions
- Integration tests when component boundaries change
- Snapshot update when ICS output format changes (`UPDATE_SNAPSHOTS=1 python -m pytest -m snapshot`)
- Tests must pass locally (pre-commit) AND in CI
- If source changes lack test changes, warn the user
- Test command: `python -m pytest src/tests/ -q --tb=short`
- Run integration tests: `python -m pytest src/tests/ -m integration`
- Run snapshot tests: `python -m pytest src/tests/ -m snapshot`
- Coverage: `python -m pytest src/tests/ --cov=src --cov-report=term-missing`

## Code Style

- No SQLAlchemy — raw sqlite3 + dataclasses only
- No heavy dependencies (no Playwright, no Crawl4AI)
- Keep it simple — no over-engineering
