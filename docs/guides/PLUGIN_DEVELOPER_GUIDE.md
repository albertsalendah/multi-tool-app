# Plugin Developer Guide

## Purpose
Guide for creating new tools.

## Steps
1. Create a new tool directory.
2. Implement the required lifecycle.
3. Register metadata.
4. Expose capabilities.
5. Test the tool.
6. Package for plugin discovery.

## Required Lifecycle
- initialize()
- validate()
- execute()
- cleanup()
