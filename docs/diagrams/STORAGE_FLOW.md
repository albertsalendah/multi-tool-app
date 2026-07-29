# Storage Flow

```mermaid
flowchart TD
    OutputBundle --> StorageManager
    StorageManager --> DirectDownload
    StorageManager --> GoogleDrive
    StorageManager --> Dropbox
    StorageManager --> MEGA
    GoogleDrive --> Cleanup
    Dropbox --> Cleanup
    MEGA --> Cleanup
    DirectDownload --> Cleanup
```
