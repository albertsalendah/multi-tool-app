# ADR-0002: Job-Based Architecture

Status: Accepted

## Context
Every user request follows a similar lifecycle regardless of the tool.

## Decision
Represent every execution as a Job.

Typical lifecycle:
1. Validate request
2. Create Job
3. Allocate resources
4. Execute Tool
5. Produce Output Bundle
6. Deliver output
7. Cleanup resources

## Consequences
- Unified progress reporting
- Easier retries and cancellation
- Consistent logging and auditing
