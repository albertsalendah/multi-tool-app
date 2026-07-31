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

`POST /tools/{name}/run` executes a tool synchronously and returns its
result directly in the response - no job/poll cycle. Refused (400) for
any tool declaring the `browser` capability, since those can run for a
long time (e.g. manual CAPTCHA solving); use `POST /jobs` for those.

## Authentication
Guest access supported for public tools.
Authenticated users gain cloud integration and history.
