# Error Codes

**Status: planned, not yet implemented.** Nothing in the codebase
currently raises or checks these codes - all error handling today uses
plain exception messages (e.g. `RuntimeError("Missing required
capability: browser")`), not structured codes. This is the intended
shape for when/if structured error codes are added.

## Platform
PLT-001 Initialization Failed
PLT-002 Configuration Error

## Job
JOB-001 Validation Failed
JOB-002 Execution Failed
JOB-003 Cancelled

## Browser
BRW-001 Launch Failed
BRW-002 Navigation Failed

## Storage
STG-001 Upload Failed
STG-002 Authentication Failed
