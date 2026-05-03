# Contributing

## Code Style

This project uses:
- **ruff** for Python linting and formatting
- **prettier** for JavaScript/CSS formatting
- **pre-commit** for automated checks

### Format Your Code

Run formatting before committing:

```bash
ruff check --fix backend/
ruff format backend/
cd frontend && npm run format
```

Or install pre-commit hooks (recommended):

```bash
pre-commit install
pre-commit run --all-files
```

All PRs must pass CI checks (which include formatting validation).
---
