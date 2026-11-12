"""Command-line interface for running Metabase browser agent tasks."""

import logging
import os
from pathlib import Path

import click

from metabase_agent.config import AppConfig
from metabase_agent.runner import TaskRunner
from metabase_agent.tasks.loader import load_task


def setup_logging(level: str) -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


@click.group()
@click.version_option()
def main() -> None:
    """Metabase Browser Agent - Automate Metabase tasks."""
    pass


@main.command()
@click.option(
    "--task",
    "-t",
    required=True,
    help="Task ID or path to task YAML file.",
)
@click.option(
    "--demo",
    is_flag=True,
    default=False,
    help="Run in demo mode with visible browser.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output directory for artifacts (overrides config).",
)
@click.option(
    "--model",
    "-m",
    help="Model name to use (e.g., gemini/gemini-2.0-flash, gpt-4o).",
)
@click.option(
    "--max-steps",
    type=int,
    help="Maximum number of steps (overrides task config).",
)
@click.option(
    "--skip-prerequisites",
    is_flag=True,
    default=False,
    help="Skip prerequisite checks (useful for testing).",
)
def run(
    task: str,
    demo: bool,
    output: Path | None,
    model: str | None,
    max_steps: int | None,
    skip_prerequisites: bool,
) -> None:
    """Run a browser automation task against Metabase."""
    config = AppConfig.load()

    if demo:
        config.headless = False

    if output:
        config.artifacts_dir = output

    if model:
        config.model.name = model

    setup_logging(config.log_level)
    logger = logging.getLogger(__name__)

    logger.info(f"Loading task: {task}")
    task_spec = load_task(task)

    if max_steps:
        task_spec.max_steps = max_steps

    logger.info(f"Running task: {task_spec.name}")
    logger.info(f"Using model: {config.model.name}")
    runner = TaskRunner(config, skip_prerequisites=skip_prerequisites)

    result = runner.run(task_spec)

    if result.success:
        logger.info(f"Task completed successfully: {result.summary}")
        click.echo(f"Success: {result.summary}")
        click.echo(f"Steps taken: {result.total_steps}")
        click.echo(f"Time elapsed: {result.elapsed_seconds:.1f}s")
        if result.agent_answer:
            click.echo(f"\n--- Agent Answer ---")
            click.echo(result.agent_answer)
            click.echo(f"--------------------")
        click.echo(f"Artifacts saved to: {result.artifacts_dir}")
    else:
        logger.error(f"Task failed: {result.summary}")
        click.echo(f"Failed: {result.summary}", err=True)
        
        # Show prerequisite-specific info
        if not result.prerequisites_satisfied:
            click.echo("\nMissing prerequisites:", err=True)
            for prereq in result.missing_prerequisites:
                click.echo(f"  - {prereq}", err=True)
            click.echo("\nHint: Run the required setup task first, or use --skip-prerequisites to bypass.", err=True)
        
        click.echo(f"Steps taken: {result.total_steps}")
        if result.agent_answer:
            click.echo(f"\n--- Agent Answer ---")
            click.echo(result.agent_answer)
            click.echo(f"--------------------")
        if result.artifacts_dir:
            click.echo(f"Artifacts saved to: {result.artifacts_dir}")
        raise SystemExit(1)


@main.command()
def list_tasks() -> None:
    """List available example tasks."""
    from metabase_agent.tasks.loader import list_example_tasks

    tasks = list_example_tasks()
    if not tasks:
        click.echo("No example tasks found.")
        return

    click.echo("Available tasks:")
    for task_id in tasks:
        click.echo(f"  - {task_id}")


@main.command()
@click.option(
    "--task",
    "-t",
    required=True,
    help="Task ID or path to task YAML file.",
)
def check_prerequisites(task: str) -> None:
    """Check if task prerequisites are satisfied."""
    from metabase_agent.tasks.prerequisites import check_prerequisites as check_prereqs, PrerequisiteChecker
    
    config = AppConfig.load()
    setup_logging(config.log_level)
    
    task_spec = load_task(task)
    
    if not task_spec.has_requirements():
        click.echo(f"Task '{task_spec.name}' has no prerequisites.")
        return
    
    click.echo(f"Checking prerequisites for: {task_spec.name}")
    click.echo(f"Requirements: {len(task_spec.requires)}")
    
    result = check_prereqs(
        task=task_spec,
        metabase_url=config.metabase.url,
        username=config.metabase.username,
        password=config.metabase.password,
    )
    
    click.echo("")
    for key, satisfied in result.details.items():
        status = "OK" if satisfied else "MISSING"
        icon = "+" if satisfied else "-"
        click.echo(f"  [{icon}] {key}: {status}")
    
    click.echo("")
    if result.satisfied:
        click.echo("All prerequisites satisfied. Task can run.")
    else:
        click.echo(f"Missing {len(result.missing)} prerequisite(s).", err=True)
        for req in task_spec.requires:
            if f"{req.type}:{req.name}" in result.missing and req.setup_task_id:
                click.echo(f"\nHint: Run 'metabase-agent run -t {req.setup_task_id}' to create the missing {req.type}.", err=True)
        raise SystemExit(1)


@main.command()
def check() -> None:
    """Check environment setup and dependencies."""
    click.echo("Checking Metabase Agent setup...\n")

    config = AppConfig.load()

    click.echo(f"Model: {config.model.name}")

    api_key_var = None
    if config.model.name.startswith("gemini/"):
        api_key_var = "GEMINI_API_KEY"
    elif config.model.name.startswith("azure/"):
        api_key_var = "AZURE_OPENAI_API_KEY"
    elif config.model.name.startswith("openrouter/"):
        api_key_var = "OPENROUTER_API_KEY"
    else:
        api_key_var = "OPENAI_API_KEY"

    api_key = os.environ.get(api_key_var, "")
    if api_key:
        click.echo(f"API Key ({api_key_var}): Set (***{api_key[-4:]})")
    else:
        click.echo(f"API Key ({api_key_var}): NOT SET", err=True)

    click.echo(f"\nMetabase URL: {config.metabase.url}")
    click.echo(f"Metabase User: {config.metabase.username}")
    click.echo(f"Headless: {config.headless}")
    click.echo(f"Artifacts Dir: {config.artifacts_dir}")

    click.echo("\nChecking dependencies...")
    from importlib.metadata import version

    try:
        import playwright
        click.echo(f"  playwright: OK ({version('playwright')})")
    except ImportError:
        click.echo("  playwright: NOT INSTALLED", err=True)

    try:
        import agentlab
        click.echo(f"  agentlab: OK ({version('agentlab')})")
    except ImportError:
        click.echo("  agentlab: NOT INSTALLED (will use LiteLLM fallback)")

    try:
        import litellm
        click.echo(f"  litellm: OK ({version('litellm')})")
    except ImportError:
        click.echo("  litellm: NOT INSTALLED", err=True)

    click.echo("\nSetup check complete.")


if __name__ == "__main__":
    main()
