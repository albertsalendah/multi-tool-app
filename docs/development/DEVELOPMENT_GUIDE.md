# Development Guide

## Development Philosophy
Implement the platform incrementally while keeping the architecture stable.

## Recommended Order
1. Refactor project structure.
2. Implement Application Kernel.
3. Add Tool Registry.
4. Add Plugin Discovery.
5. Implement Job Manager.
6. Implement Browser Manager.
7. Integrate CAPTCHA Manager.
8. Implement Output and Storage Managers.
9. Migrate existing tools.
10. Add new tools.

## Branch Strategy
- main: stable
- develop: integration
- feature/*: individual features
- hotfix/*: production fixes
