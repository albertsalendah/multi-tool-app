# Coding Standards

## General
- Prefer readability over cleverness.
- Keep functions focused on one responsibility.
- Use descriptive names.
- Avoid duplicated logic.

## Architecture
- Business logic belongs in Tools.
- Shared infrastructure belongs in Platform Services.
- Reusable utilities belong in Shared Libraries.
- Do not introduce circular dependencies.

## Logging
- Log meaningful events.
- Never log secrets or credentials.

## Error Handling
- Fail gracefully.
- Return actionable error messages.
