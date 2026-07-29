# Tool Execution Flow

```mermaid
flowchart LR
    Start --> Initialize
    Initialize --> Validate
    Validate --> Execute
    Execute --> OutputBundle
    OutputBundle --> Cleanup
    Cleanup --> Finish
```
