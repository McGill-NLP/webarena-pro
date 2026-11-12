"""Task specification model."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskRequirement:
    """Represents a prerequisite that must exist before a task can run."""
    
    type: str  # "dashboard", "question", "collection", "subscription", "alert"
    name: str  # Name to search for or create
    setup_task_id: str | None = None  # Optional: task ID that can create this prerequisite
    
    @classmethod
    def from_dict(cls, data: dict | str) -> "TaskRequirement":
        """Create from dictionary or simple string format."""
        if isinstance(data, str):
            # Simple format: "dashboard:Sales Overview"
            if ":" in data:
                type_part, name_part = data.split(":", 1)
                return cls(type=type_part.strip(), name=name_part.strip())
            return cls(type="unknown", name=data)
        return cls(
            type=data.get("type", "unknown"),
            name=data.get("name", ""),
            setup_task_id=data.get("setup_task_id"),
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result = {"type": self.type, "name": self.name}
        if self.setup_task_id:
            result["setup_task_id"] = self.setup_task_id
        return result


@dataclass
class TaskSpec:
    """Represents a browser automation task."""

    id: str
    name: str
    instruction: str
    start_url: str
    max_steps: int = 30
    timeout_seconds: int = 600
    success_criteria: list[str | dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    requires: list[TaskRequirement] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result = {
            "id": self.id,
            "name": self.name,
            "instruction": self.instruction,
            "start_url": self.start_url,
            "max_steps": self.max_steps,
            "timeout_seconds": self.timeout_seconds,
            "success_criteria": self.success_criteria,
            "tags": self.tags,
            "notes": self.notes,
        }
        if self.requires:
            result["requires"] = [r.to_dict() for r in self.requires]
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "TaskSpec":
        """Create from dictionary."""
        requires_raw = data.get("requires", [])
        requires = [TaskRequirement.from_dict(r) for r in requires_raw] if requires_raw else []
        
        return cls(
            id=data["id"],
            name=data["name"],
            instruction=data["instruction"],
            start_url=data["start_url"],
            max_steps=data.get("max_steps", 30),
            timeout_seconds=data.get("timeout_seconds", 600),
            success_criteria=data.get("success_criteria", []),
            tags=data.get("tags", []),
            notes=data.get("notes", ""),
            requires=requires,
        )
    
    def has_requirements(self) -> bool:
        """Check if task has any requirements."""
        return len(self.requires) > 0
