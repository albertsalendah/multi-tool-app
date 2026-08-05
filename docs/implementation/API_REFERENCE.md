# API Reference

## Base Path
/api/v1/

## Core Endpoints
GET  /health
GET  /tools
POST /jobs
GET  /jobs/{id}
DELETE /jobs/{id}
POST /tools/{name}/run
POST /schedules
GET  /schedules/{id}
DELETE /schedules/{id}

`POST /tools/{name}/run` executes a tool synchronously and returns its
result directly in the response - no job/poll cycle. Refused (400) for
any tool declaring the `browser` capability, since those can run for a
long time (e.g. manual CAPTCHA solving); use `POST /jobs` for those.

`POST /schedules` runs a tool once, `delay_seconds` from now, via the
platform Scheduler - {`delay_seconds`, `tool`, `params`}, returns a
`schedule_id`. Unknown tool name or missing capability is rejected
immediately (404/400), not deferred until the timer fires. No list
endpoint, same as `/jobs`.

## Authentication
Guest access supported for public tools.
Authenticated users gain cloud integration and history.
