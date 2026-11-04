"""
Project Domain Model representing a campaign grouping profiles and tracking aggregate metrics.
"""

from dataclasses import dataclass


@dataclass
class ProjectDomainModel:
    id: int
    name: str
    description: str | None = None
    color_tag: str = "#2196F3"
    is_default: bool = False
    created_at: str | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Project name cannot be empty")
        self.name = self.name.strip()
