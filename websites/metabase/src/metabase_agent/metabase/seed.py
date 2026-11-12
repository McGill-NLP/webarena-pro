"""Utilities for seeding Metabase with test data.

This module provides functions to set up test data, dashboards, and
questions in Metabase for reproducible agent testing.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metabase_agent.metabase.api import MetabaseClient

logger = logging.getLogger(__name__)


def seed_sample_data(client: "MetabaseClient") -> bool:
    """Seed Metabase with sample data for testing.

    This creates:
    - Sample database connection
    - Basic questions/queries
    - A dashboard with visualizations

    Args:
        client: Authenticated Metabase API client.

    Returns:
        True if seeding was successful.
    """
    logger.warning("Seed function not yet implemented")
    return False


def create_test_dashboard(
    client: "MetabaseClient",
    name: str = "Sales Dashboard",
    description: str = "Test dashboard for agent automation",
) -> int | None:
    """Create a test dashboard.

    Args:
        client: Authenticated Metabase API client.
        name: Dashboard name.
        description: Dashboard description.

    Returns:
        Dashboard ID if created, None otherwise.
    """
    logger.warning("Dashboard creation not yet implemented")
    return None


def create_test_question(
    client: "MetabaseClient",
    name: str = "Sales by Region",
    database_id: int = 1,
) -> int | None:
    """Create a test question/query.

    Args:
        client: Authenticated Metabase API client.
        name: Question name.
        database_id: Database to query.

    Returns:
        Question ID if created, None otherwise.
    """
    logger.warning("Question creation not yet implemented")
    return None


def reset_test_environment(client: "MetabaseClient") -> bool:
    """Reset the test environment to a clean state.

    This removes test artifacts created by previous runs
    to ensure reproducible testing.

    Args:
        client: Authenticated Metabase API client.

    Returns:
        True if reset was successful.
    """
    logger.warning("Environment reset not yet implemented")
    return False
