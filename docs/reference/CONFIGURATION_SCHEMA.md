# Configuration Schema

## Sections (implemented)
- app
- browser
- jobs
- logging

## Sections (planned, not yet implemented)
- server
- authentication
- storage
- resources
- tools

## Rules
- Environment overrides supported (`Config.get()`: `key.upper().replace(".", "_")`,
  e.g. `browser.headless` -> `BROWSER_HEADLESS`)
- No secrets committed to source control
- A missing or malformed config file is logged as a warning and falls
  back to defaults, rather than crashing - see `app/config.py`
