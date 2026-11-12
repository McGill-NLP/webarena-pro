"""Task runner that orchestrates browser environment, agent, and evaluation."""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from metabase_agent.agent.generic_agent_adapter import AgentController
from metabase_agent.agent.models import AgentAction
from metabase_agent.config import AppConfig
from metabase_agent.env.playwright_env import PlaywrightEnv
from metabase_agent.evaluation.rules import RuleBasedEvaluator
from metabase_agent.logging.artifacts import ArtifactLogger
from metabase_agent.logging.traces import StepTrace
from metabase_agent.tasks.prerequisites import check_prerequisites, PrerequisiteChecker
from metabase_agent.metabase.api import MetabaseClient

if TYPE_CHECKING:
    from metabase_agent.tasks.models import TaskSpec


@dataclass
class RunResult:
    """Result of a task run."""

    success: bool
    summary: str
    error: str | None = None
    artifacts_dir: Path | None = None
    total_steps: int = 0
    elapsed_seconds: float = 0.0
    traces: list[StepTrace] = field(default_factory=list)
    agent_answer: str | None = None  # The agent's final answer/report when calling done()
    prerequisites_satisfied: bool = True  # Whether task prerequisites were met
    missing_prerequisites: list[str] = field(default_factory=list)


class TaskRunner:
    """Orchestrates running a task through the browser agent loop."""

    def __init__(self, config: AppConfig, skip_prerequisites: bool = False) -> None:
        self.config = config
        self.skip_prerequisites = skip_prerequisites
        self.logger = logging.getLogger(__name__)

    def run(self, task: "TaskSpec") -> RunResult:
        """Execute a task and return the result."""
        start_time = time.time()

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        artifacts_dir = self.config.artifacts_dir / f"{task.id}_{run_id}"
        artifact_logger = ArtifactLogger(artifacts_dir)
        artifact_logger.save_task_spec(task)

        # Check prerequisites before running
        if task.has_requirements() and not self.skip_prerequisites:
            self.logger.info("Checking task prerequisites...")
            prereq_result = check_prerequisites(
                task=task,
                metabase_url=self.config.metabase.url,
                username=self.config.metabase.username,
                password=self.config.metabase.password,
            )
            
            if not prereq_result.satisfied:
                self.logger.error(f"Prerequisites not satisfied: {prereq_result.missing}")
                return RunResult(
                    success=False,
                    summary=f"Prerequisites not satisfied: {', '.join(prereq_result.missing)}",
                    error="Missing prerequisites",
                    artifacts_dir=artifacts_dir,
                    total_steps=0,
                    elapsed_seconds=time.time() - start_time,
                    traces=[],
                    agent_answer=None,
                    prerequisites_satisfied=False,
                    missing_prerequisites=prereq_result.missing,
                )
            self.logger.info("All prerequisites satisfied")

        env = PlaywrightEnv(
            headless=self.config.headless,
            metabase_url=self.config.metabase.url,
            username=self.config.metabase.username,
            password=self.config.metabase.password,
        )

        agent = AgentController(
            model_name=self.config.model.name,
            api_key=self.config.model.api_key,
            base_url=self.config.model.base_url,
        )

        evaluator = RuleBasedEvaluator()

        traces: list[StepTrace] = []
        step = 0
        done = False
        error: str | None = None
        last_action_str: str = ""
        last_action_error: str = ""

        try:
            self.logger.info("Initializing browser environment")
            obs = env.reset(task)
            agent.reset(task)

            while step < task.max_steps and not done:
                step += 1
                step_start = time.time()
                self.logger.info(f"Step {step}/{task.max_steps}")

                # Inject error feedback from previous step into observation
                obs.last_action = last_action_str
                obs.last_action_error = last_action_error

                action = agent.act(obs)
                action_desc = action.describe()
                self.logger.info(f"Agent action: {action_desc}")
                if action.reasoning:
                    self.logger.debug(f"Reasoning: {action.reasoning[:200]}")

                screenshot_path = artifact_logger.save_screenshot(
                    obs.screenshot_bytes or env.get_screenshot(),
                    step,
                    prefix="before",
                )

                if action.action_type in ("done", "answer"):
                    if action.action_type == "answer":
                        self.logger.info(f"Agent reported answer: {action.value}")
                    else:
                        self.logger.info("Agent signaled task complete")
                    done = True
                    trace = StepTrace(
                        step=step,
                        action=action,
                        observation_summary=obs.summary(),
                        url=obs.url,
                        screenshot_path=screenshot_path,
                        reward=1.0,
                        done=True,
                        elapsed_ms=int((time.time() - step_start) * 1000),
                        error=None,
                    )
                    traces.append(trace)
                    artifact_logger.save_trace(trace)
                    break

                obs, reward, done, info = env.step(action)

                # Store action and error for next iteration's feedback
                last_action_str = action_desc
                last_action_error = info.get("error", "")

                if last_action_error:
                    self.logger.warning(f"Action failed: {last_action_error[:200]}")

                trace = StepTrace(
                    step=step,
                    action=action,
                    observation_summary=obs.summary(),
                    url=obs.url,
                    screenshot_path=screenshot_path,
                    reward=reward,
                    done=done,
                    elapsed_ms=int((time.time() - step_start) * 1000),
                    error=info.get("error"),
                )
                traces.append(trace)
                artifact_logger.save_trace(trace)

                if done:
                    self.logger.info("Environment signaled done")
                    break

                evaluation = evaluator.evaluate(task, traces, obs)
                if evaluation.success:
                    self.logger.info(f"Task succeeded: {evaluation.reason}")
                    done = True
                    break

                if time.time() - start_time > task.timeout_seconds:
                    error = "Task timed out"
                    self.logger.warning(error)
                    break

        except Exception as e:
            error = str(e)
            self.logger.exception("Task failed with exception")

        finally:
            env.close()

        final_screenshot = artifact_logger.save_screenshot(
            env.get_screenshot() if hasattr(env, "_page") and env._page else None,
            step,
            prefix="final",
        )

        elapsed = time.time() - start_time

        # Evaluate task success based on criteria, not just completion
        final_evaluation = evaluator.evaluate(task, traces, obs) if "obs" in locals() else None
        
        # Success requires:
        # 1. Agent completed (called done() or evaluation passed mid-run)
        # 2. No runtime errors occurred
        # 3. All success criteria passed (most important!)
        criteria_passed = final_evaluation.success if final_evaluation else False
        success = done and error is None and criteria_passed
        
        # Build summary message
        if error:
            summary = f"Runtime error: {error}"
        elif not done:
            summary = "Task did not complete (max steps or timeout reached)"
        elif not criteria_passed:
            summary = final_evaluation.reason if final_evaluation else "Evaluation criteria not met"
        else:
            summary = final_evaluation.reason if final_evaluation else "Task completed successfully"

        # Extract agent's answer from the answer() action value or done() reasoning
        agent_answer = None
        if traces:
            last_trace = traces[-1]
            if last_trace.action.action_type == "answer" and last_trace.action.value:
                agent_answer = last_trace.action.value
            elif last_trace.action.action_type == "done" and last_trace.action.reasoning:
                agent_answer = last_trace.action.reasoning

        result = RunResult(
            success=success,
            summary=summary,
            error=error,
            artifacts_dir=artifacts_dir,
            total_steps=step,
            elapsed_seconds=elapsed,
            traces=traces,
            agent_answer=agent_answer,
        )

        artifact_logger.save_summary(result)

        return result
