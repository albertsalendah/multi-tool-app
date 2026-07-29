from dataclasses import dataclass, field


@dataclass(slots=True)
class PluginManifest:
    id: str
    name: str
    version: str
    description: str
    author: str
    entry: str
    enabled: bool = True
    capabilities: list[str] = field(default_factory=list)
