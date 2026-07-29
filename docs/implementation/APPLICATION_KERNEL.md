# Application Kernel

## Purpose
Central bootstrap and lifecycle coordinator.

## Responsibilities
- Initialize configuration
- Register services
- Load tools
- Start platform
- Graceful shutdown

## Depends On
Configuration, Event Bus, Tool Registry.

## Exposes
start(), stop(), health()
