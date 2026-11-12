"""Prerequisite checker for task dependencies.

Checks if required artifacts exist in Metabase before running a task.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from metabase_agent.metabase.api import MetabaseClient

if TYPE_CHECKING:
    from metabase_agent.tasks.models import TaskRequirement, TaskSpec


logger = logging.getLogger(__name__)


@dataclass
class PrerequisiteResult:
    """Result of checking prerequisites."""
    
    satisfied: bool
    missing: list[str]
    details: dict[str, bool]
    
    @classmethod
    def all_satisfied(cls, details: dict[str, bool]) -> "PrerequisiteResult":
        """Create result when all prerequisites are satisfied."""
        return cls(satisfied=True, missing=[], details=details)
    
    @classmethod
    def some_missing(cls, missing: list[str], details: dict[str, bool]) -> "PrerequisiteResult":
        """Create result when some prerequisites are missing."""
        return cls(satisfied=False, missing=missing, details=details)


class PrerequisiteChecker:
    """Checks if task prerequisites exist in Metabase."""
    
    def __init__(self, client: MetabaseClient) -> None:
        self.client = client
        self.logger = logging.getLogger(__name__)
    
    def check(self, task: "TaskSpec") -> PrerequisiteResult:
        """Check if all task prerequisites are satisfied.
        
        Args:
            task: Task specification with requirements.
            
        Returns:
            PrerequisiteResult indicating which prerequisites are satisfied/missing.
        """
        if not task.has_requirements():
            return PrerequisiteResult.all_satisfied({})
        
        details: dict[str, bool] = {}
        missing: list[str] = []
        
        for req in task.requires:
            key = f"{req.type}:{req.name}"
            exists = self._check_requirement(req)
            details[key] = exists
            
            if not exists:
                missing.append(key)
                self.logger.warning(f"Missing prerequisite: {key}")
            else:
                self.logger.info(f"Prerequisite satisfied: {key}")
        
        if missing:
            return PrerequisiteResult.some_missing(missing, details)
        return PrerequisiteResult.all_satisfied(details)
    
    def _check_requirement(self, req: "TaskRequirement") -> bool:
        """Check if a single requirement exists.
        
        Args:
            req: The requirement to check.
            
        Returns:
            True if the requirement is satisfied.
        """
        req_type = req.type.lower()
        
        if req_type == "dashboard":
            return self.client.dashboard_exists(req.name)
        
        elif req_type == "question":
            return self.client.question_exists(req.name)
        
        elif req_type == "collection":
            return self.client.collection_exists(req.name)
        
        elif req_type == "alert":
            return self.client.alert_exists(req.name if req.name else None)
        
        elif req_type == "subscription":
            return self.client.subscription_exists(req.name if req.name else None)
        
        else:
            self.logger.warning(f"Unknown requirement type: {req_type}")
            return False
    
    def get_missing_summary(self, result: PrerequisiteResult) -> str:
        """Get a human-readable summary of missing prerequisites.
        
        Args:
            result: The prerequisite check result.
            
        Returns:
            Human-readable summary string.
        """
        if result.satisfied:
            return "All prerequisites satisfied"
        
        missing_items = []
        for key in result.missing:
            req_type, name = key.split(":", 1)
            missing_items.append(f"- {req_type.capitalize()} '{name}' does not exist")
        
        return "Missing prerequisites:\n" + "\n".join(missing_items)


def check_prerequisites(
    task: "TaskSpec",
    metabase_url: str,
    username: str,
    password: str,
) -> PrerequisiteResult:
    """Convenience function to check task prerequisites.
    
    Args:
        task: Task specification with requirements.
        metabase_url: Metabase server URL.
        username: Metabase username.
        password: Metabase password.
        
    Returns:
        PrerequisiteResult indicating which prerequisites are satisfied/missing.
    """
    client = MetabaseClient(metabase_url, username, password)
    try:
        if not client.authenticate():
            logger.error("Failed to authenticate with Metabase for prerequisite check")
            return PrerequisiteResult.some_missing(
                ["authentication_failed"],
                {"authentication": False}
            )
        
        checker = PrerequisiteChecker(client)
        return checker.check(task)
    finally:
        client.close()
