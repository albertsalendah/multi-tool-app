# Event Reference

Event names in code use dotted lowercase (`job.started`, not
`JobCreated`) - this doc previously used CamelCase names that don't
match any actual `events.emit(...)` call. Updated to match reality.

## Job Events (`app/job_manager.py`)
- `job.started` - `job_id`
- `job.completed` - `job_id`, `result`
- `job.failed` - `job_id`, `error`
- `job.cancelled` - `job_id`

## Tool Events (`app/kernel.py`)
- `tool.started` - `tool`
- `tool.finished` - `tool`, `result`
- `tool.progress` - `tool`, `progress`, `message` (emitted by
  `ExecutionContext.report_progress()`)

## Workflow Events (`app/workflow_engine.py`)
- `workflow.started` - `workflow`, `execution_id`, `total_steps`,
  `background`
- `workflow.progress` - `workflow`, `execution_id`, `tool`, `status`
  (`succeeded` / `skipped` / `failed_ignored` / `failed`), `completed`,
  `total`, `percent`. Fires once per leaf step, including branches
  inside a `ParallelGroup`.
- `workflow.completed` - `workflow`, `execution_id`, `duration`,
  `result_count`
- `workflow.failed` - `workflow`, `execution_id`, `duration`, `error`

`execution_id` correlates all four events from a single
`WorkflowEngine.execute()` call.

## Planned (not yet implemented)
These are still aspirational - no code emits them today:
- Browser: `browser.acquired`, `browser.released`
- CAPTCHA: `captcha.detected`, `captcha.solved` (the
  `libraries/captcha_manager` library isn't wired into the Event Bus
  yet - see `docs/ARCHITECTURE_CHANGELOG.md`'s technical debt list)
- Output/Storage: `output.ready`, `upload.started`, `upload.completed`
  (Output Manager and Storage Manager don't exist yet)

## Event Guidelines
- Events should be immutable.
- Include timestamps and Job ID where relevant.
- Avoid sensitive information in payloads.
