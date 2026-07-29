# Event Reference

## Core Events
- JobCreated
- JobStarted
- JobCompleted
- JobFailed
- BrowserAcquired
- BrowserReleased
- CaptchaDetected
- CaptchaSolved
- OutputReady
- UploadStarted
- UploadCompleted

## Event Guidelines
- Events should be immutable.
- Include timestamps and Job ID.
- Avoid sensitive information in payloads.
