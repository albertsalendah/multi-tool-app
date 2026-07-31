# Target Directory Structure

```
app/
tools/
libraries/
shared/
docs/
static/
tests/
cli/
```

- app: platform core
- tools: user-facing modules
- libraries: reusable packages
- shared: infrastructure helpers
- tests: automated test suite (pytest)
- cli: REST API client (`pip install -e .`, console script `multitool`).
  Talks to a running server over HTTP - does not embed the Kernel.
