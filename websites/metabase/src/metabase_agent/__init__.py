"""Metabase Browser Agent - Automate Metabase tasks using Playwright and AgentLab."""

__version__ = "0.1.0"

from metabase_agent.config import AppConfig
from metabase_agent.runner import TaskRunner

__all__ = ["AppConfig", "TaskRunner", "__version__"]
