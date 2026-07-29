# Plugin Discovery Flow

```mermaid
flowchart TD
    Startup --> ScanPlugins
    ScanPlugins --> ValidateManifest
    ValidateManifest --> RegisterTool
    RegisterTool --> RegisterCapabilities
    RegisterCapabilities --> Ready
```
