"""Adapter for AgentLab's GenericAgent.

This module wraps AgentLab's GenericAgent to keep the rest of the codebase
independent from AgentLab internals. It translates between our Observation/AgentAction
types and AgentLab/BrowserGym formats.

AgentLab uses LiteLLM under the hood, which supports multiple providers:
- OpenAI: "gpt-4", "gpt-4o", "gpt-4o-mini"
- Gemini: "gemini/gemini-2.0-flash", "gemini/gemini-1.5-pro"
- Azure: "azure/deployment-name"
- OpenRouter: "openrouter/model-name"

For Gemini, set GEMINI_API_KEY in your environment.
For OpenAI, set OPENAI_API_KEY in your environment.
"""

from __future__ import annotations

import base64
import logging
import os
import re
from typing import TYPE_CHECKING, Any

from metabase_agent.agent.models import AgentAction, Observation

if TYPE_CHECKING:
    from metabase_agent.tasks.models import TaskSpec

logger = logging.getLogger(__name__)


def _get_api_key_for_model(model_name: str) -> str:
    """Get the appropriate API key based on model name."""
    if model_name.startswith("gemini/"):
        return os.environ.get("GEMINI_API_KEY", "")
    elif model_name.startswith("azure/"):
        return os.environ.get("AZURE_OPENAI_API_KEY", "")
    elif model_name.startswith("openrouter/"):
        return os.environ.get("OPENROUTER_API_KEY", "")
    else:
        return os.environ.get("OPENAI_API_KEY", "")


class AgentController:
    """Controller that wraps AgentLab's GenericAgent.

    This provides a clean interface for the TaskRunner while isolating
    AgentLab-specific code.
    """

    def __init__(
        self,
        model_name: str = "gemini/gemini-2.0-flash",
        api_key: str = "",
        base_url: str = "",
        use_vision: bool = True,
        use_html: bool = True,
        use_axtree: bool = True,
        max_tokens: int = 4096,
    ) -> None:
        self.model_name = model_name
        self.api_key = api_key or _get_api_key_for_model(model_name)
        self.base_url = base_url
        self.use_vision = use_vision
        self.use_html = use_html
        self.use_axtree = use_axtree
        self.max_tokens = max_tokens

        self._task: TaskSpec | None = None
        self._history: list[tuple[Observation, AgentAction]] = []
        self._step_count: int = 0
        self._consecutive_no_change: int = 0
        self._last_content_hash: str = ""

        self._agent: Any = None
        self._init_agent()

    def _init_agent(self) -> None:
        """Initialize the AgentLab GenericAgent."""
        try:
            from agentlab.agents.generic_agent import GenericAgentArgs
            from agentlab.llm.chat_api import ChatModelArgs

            chat_model_args = ChatModelArgs(
                model_name=self.model_name,
                max_new_tokens=self.max_tokens,
                temperature=0.1,
            )

            agent_args = GenericAgentArgs(
                chat_model_args=chat_model_args,
                flags=self._get_agent_flags(),
            )

            self._agent = agent_args.make_agent()
            logger.info(f"Initialized AgentLab GenericAgent with model: {self.model_name}")

        except ImportError as e:
            logger.warning(f"AgentLab not available, using fallback mode: {e}")
            self._agent = None
        except Exception as e:
            logger.warning(f"Failed to initialize AgentLab agent: {e}")
            self._agent = None

    def _get_agent_flags(self) -> dict[str, Any]:
        """Get agent configuration flags."""
        try:
            from agentlab.agents.generic_agent import GenericAgentArgs

            default_args = GenericAgentArgs()
            default_flags = default_args.flags.copy() if default_args.flags else {}
            default_flags.update(
                {
                    "use_html": self.use_html,
                    "use_axtree": self.use_axtree,
                    "use_screenshot": self.use_vision,
                }
            )
            return default_flags
        except (ImportError, AttributeError):
            return {
                "use_html": self.use_html,
                "use_axtree": self.use_axtree,
                "use_screenshot": self.use_vision,
            }

    def reset(self, task: TaskSpec) -> None:
        """Reset the agent for a new task."""
        self._task = task
        self._history = []
        self._step_count = 0
        self._consecutive_no_change = 0
        self._last_content_hash = ""

        if self._agent is not None:
            try:
                self._agent.reset(goal=task.instruction)
            except Exception as e:
                logger.warning(f"Failed to reset agent: {e}")

        logger.info(f"Agent reset for task: {task.name}")

    def _compute_content_fingerprint(self, observation: Observation) -> str:
        """Compute a fingerprint of the page content to detect state changes.
        
        Uses the axtree (interactive elements) as the primary signal since it
        captures what the user can actually interact with.
        """
        content_parts = []
        
        if observation.axtree:
            content_parts.append(observation.axtree[:5000])
        elif observation.text_content:
            content_parts.append(observation.text_content[:5000])
        
        content_parts.append(observation.title or "")
        
        combined = "".join(content_parts)
        return str(hash(combined))

    def _check_state_change(self, observation: Observation) -> bool:
        """Check if the page state changed since the last observation.
        
        Returns True if the state changed, False if it appears unchanged.
        Updates internal tracking counters.
        """
        current_hash = self._compute_content_fingerprint(observation)
        
        if self._last_content_hash and current_hash == self._last_content_hash:
            self._consecutive_no_change += 1
            logger.debug(f"Page content unchanged for {self._consecutive_no_change} consecutive steps")
            changed = False
        else:
            if self._consecutive_no_change > 0:
                logger.debug("Page content changed after actions")
            self._consecutive_no_change = 0
            changed = True
        
        self._last_content_hash = current_hash
        return changed

    def act(self, observation: Observation) -> AgentAction:
        """Decide the next action based on the current observation."""
        if not self._task:
            raise RuntimeError("Agent not initialized. Call reset() first.")

        self._step_count += 1
        
        self._check_state_change(observation)

        if self._agent is not None:
            action = self._get_action_from_agentlab(observation)
        else:
            action = self._get_action_from_llm(observation)

        self._history.append((observation, action))
        return action

    def _get_action_from_agentlab(self, observation: Observation) -> AgentAction:
        """Get action using AgentLab's GenericAgent."""
        try:
            bgym_obs = self._convert_to_browsergym_obs(observation)

            agent_info = self._agent.get_action(bgym_obs)
            
            # Handle both dict and object with attributes
            if isinstance(agent_info, dict):
                raw_action = agent_info.get("action", "")
                reasoning = agent_info.get("think", "")
            else:
                # AgentLab may return an object with .action and .think attributes
                raw_action = getattr(agent_info, "action", "") or ""
                reasoning = getattr(agent_info, "think", "") or getattr(agent_info, "thoughts", "") or ""

            return self._parse_browsergym_action(raw_action, reasoning)

        except Exception as e:
            logger.warning(f"AgentLab action failed: {e}, falling back to LLM")
            return self._get_action_from_llm(observation)

    def _convert_to_browsergym_obs(self, observation: Observation) -> dict[str, Any]:
        """Convert our Observation to BrowserGym observation format."""
        goal = self._task.instruction if self._task else ""
        
        if self._consecutive_no_change >= 2:
            goal += f"\n\nWARNING: The page content has NOT changed for {self._consecutive_no_change} consecutive actions. Your clicks may not be working. Try a DIFFERENT element or approach."
        
        obs = {
            "goal": goal,
            "url": observation.url,
            "open_pages_urls": [observation.url],
            "active_page_index": 0,
            "last_action": observation.last_action or self._get_last_action_str(),
            "last_action_error": observation.last_action_error,
            "elapsed_time": 0.0,
            "step": self._step_count,
        }

        if self.use_html:
            obs["dom_txt"] = observation.html_snapshot[:50000]

        if self.use_axtree:
            obs["axtree_txt"] = observation.axtree if observation.axtree else self._extract_axtree(
                observation
            )

        if self.use_vision:
            screenshot_b64 = self._get_screenshot_base64(observation)
            if screenshot_b64:
                obs["screenshot"] = screenshot_b64

        return obs

    def _get_screenshot_base64(self, observation: Observation) -> str | None:
        """Get screenshot as base64 from observation."""
        if observation.screenshot_bytes:
            return base64.b64encode(observation.screenshot_bytes).decode("utf-8")

        if observation.screenshot_path:
            try:
                with open(observation.screenshot_path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass

        return None

    def _extract_axtree(self, observation: Observation) -> str:
        """Extract accessibility tree-like representation from the page."""
        text = observation.text_content
        lines = text.split("\n")
        axtree_lines = []
        for i, line in enumerate(lines[:200]):
            stripped = line.strip()
            if stripped:
                axtree_lines.append(f"[{i}] {stripped}")
        return "\n".join(axtree_lines)

    def _get_last_action_str(self) -> str:
        """Get string representation of last action."""
        if not self._history:
            return ""
        _, last_action = self._history[-1]
        return f"{last_action.action_type}({last_action.selector or last_action.text or ''})"

    def _parse_browsergym_action(self, raw_action: str, reasoning: str = "") -> AgentAction:
        """Parse BrowserGym action string into AgentAction.

        Supports index-based actions (preferred):
          - click(5)        -> click element [5] from axtree
          - click([5])      -> click element [5] (bracket notation)
          - type(3, "text") -> type into element [3]
          - select(7, "val") -> select value in element [7]

        Also supports legacy selector-based actions:
          - click("selector")
          - type("selector", "text")
        
        This function searches ANYWHERE in the text for valid actions,
        allowing for reasoning/explanation before the action.
        """
        raw_action = raw_action.strip()

        if not raw_action or raw_action.lower() in ["none", "noop", "done"]:
            return AgentAction.done(reasoning=reasoning)

        # Check for done() action anywhere in text
        if re.search(r'\bdone\s*\(\s*\)', raw_action, re.IGNORECASE):
            return AgentAction.done(reasoning=reasoning)

        # Index-based click: click(5) or click([5]) - search anywhere in text
        # Support both click(5) and click([5]) formats
        index_click_match = re.search(r'click\s*\(\s*\[?\s*(\d+)\s*\]?\s*\)', raw_action, re.IGNORECASE)
        if index_click_match:
            index = int(index_click_match.group(1))
            return AgentAction.click_index(index, reasoning=reasoning)

        # Index-based type: type(5, "text") or fill(5, "text") or type([5], "text")
        index_type_match = re.search(
            r'(?:type|fill)\s*\(\s*\[?\s*(\d+)\s*\]?\s*,\s*["\']([^"\']*)["\']?\s*\)',
            raw_action,
            re.IGNORECASE,
        )
        if index_type_match:
            index = int(index_type_match.group(1))
            text = index_type_match.group(2)
            return AgentAction.type_index(index, text, reasoning=reasoning)

        # Index-based select: select(7, "value") or select([7], "value")
        index_select_match = re.search(
            r'select\s*\(\s*\[?\s*(\d+)\s*\]?\s*,\s*["\']([^"\']*)["\']?\s*\)',
            raw_action,
            re.IGNORECASE,
        )
        if index_select_match:
            index = int(index_select_match.group(1))
            value = index_select_match.group(2)
            return AgentAction.select_index(index, value, reasoning=reasoning)

        # Scroll: scroll("up") or scroll("down") - search anywhere
        scroll_match = re.search(
            r'scroll\s*\(\s*["\']?(up|down)["\']?\s*\)', raw_action, re.IGNORECASE
        )
        if scroll_match:
            direction = scroll_match.group(1).lower()
            return AgentAction.scroll(direction=direction, reasoning=reasoning)  # type: ignore

        # Key press: press("Enter") - search anywhere
        press_match = re.search(r'press\s*\(\s*["\']?([^"\')\s]+)["\']?\s*\)', raw_action, re.IGNORECASE)
        if press_match:
            return AgentAction.press_key(press_match.group(1), reasoning=reasoning)

        # Navigation: goto("url") - search anywhere
        goto_match = re.search(r'goto\s*\(\s*["\']([^"\']+)["\']?\s*\)', raw_action, re.IGNORECASE)
        if goto_match:
            return AgentAction.navigate_to(goto_match.group(1), reasoning=reasoning)

        # Legacy selector-based click: click("selector") - only if no index match
        click_match = re.search(r'click\s*\(\s*"([^"]+)"\s*\)', raw_action, re.IGNORECASE)
        if not click_match:
            click_match = re.search(r"click\s*\(\s*'([^']+)'\s*\)", raw_action, re.IGNORECASE)
        if click_match:
            selector = click_match.group(1)
            logger.warning(f"Using selector-based click (prefer index): {selector}")
            return AgentAction.click(selector, reasoning=reasoning)

        # Legacy selector-based type: fill("selector", "text") or type("selector", "text")
        fill_match = re.search(
            r'(?:fill|type)\s*\(\s*["\']([^"\']+)["\']?\s*,\s*["\']([^"\']*)["\']?\s*\)',
            raw_action,
            re.IGNORECASE,
        )
        if fill_match:
            selector = fill_match.group(1)
            text = fill_match.group(2)
            logger.warning(f"Using selector-based type (prefer index): {selector}")
            return AgentAction.type_text(text, selector, reasoning)

        # wait(ms) action - search anywhere
        wait_match = re.search(r'wait\s*\(\s*(\d+)\s*\)', raw_action, re.IGNORECASE)
        if wait_match:
            timeout = int(wait_match.group(1))
            return AgentAction.wait(timeout=timeout, reasoning=reasoning)

        # answer("value") action - report task result
        answer_match = re.search(r'answer\s*\(\s*["\']([^"\']+)["\']?\s*\)', raw_action, re.IGNORECASE)
        if answer_match:
            return AgentAction.answer(answer_match.group(1), reasoning=reasoning)

        logger.warning(f"Could not parse action: {raw_action[:100]}")
        return AgentAction.wait(timeout=1000, reasoning=f"Unparsed: {raw_action[:200]}")

    def _get_action_from_llm(self, observation: Observation) -> AgentAction:
        """Get action directly from LLM when AgentLab is not available."""
        try:
            import litellm

            prompt = self._build_prompt(observation)

            response = litellm.completion(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.1,
            )

            response_text = response.choices[0].message.content
            return self._parse_llm_response(response_text)

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return self._fallback_action()

    def _build_prompt(self, observation: Observation) -> str:
        """Build prompt for direct LLM call.

        Uses index-based actions with clear documentation of available actions.
        Includes error feedback from the last action to help the agent recover.
        Includes action history to prevent repeating the same actions.
        """
        task_instruction = self._task.instruction if self._task else "Complete the task"

        # Build error feedback section
        error_section = ""
        if observation.last_action_error:
            error_section = f"""
## LAST ACTION FAILED
Your previous action: {observation.last_action}
Error message: {observation.last_action_error}

You must try a DIFFERENT approach. Do NOT repeat the same action.
"""

        # Build state change warning section
        state_warning = ""
        if self._consecutive_no_change >= 2:
            state_warning = f"""
## WARNING: PAGE CONTENT HAS NOT CHANGED ({self._consecutive_no_change} steps)
Your last {self._consecutive_no_change} action(s) did NOT change the page content.
This likely means:
- Your clicks are not hitting the intended elements
- The UI may be loading or waiting - look for loading indicators
- You may need to click a DIFFERENT element than the one you've been trying

IMPORTANT: Try a completely DIFFERENT approach. For example:
- If you've been scrolling, STOP and click on visible elements instead
- If clicking an element doesn't work, try clicking its parent or a nearby element
- Look carefully at the INTERACTIVE ELEMENTS list for what's actually on screen
- If you see the element you need in the list, click it directly by its index
"""
        elif self._consecutive_no_change == 1:
            state_warning = """
## NOTE: Page content unchanged after last action
Your previous action may not have had an effect. Verify you're clicking the right element.
"""

        # Build action history section to prevent repeating actions
        history_section = ""
        if self._history:
            history_lines = []
            for i, (obs, act) in enumerate(self._history[-10:], 1):  # Last 10 actions
                history_lines.append(f"  Step {i}: {act.describe()} (on page: {obs.url})")
            history_section = f"""
## YOUR PREVIOUS ACTIONS (do NOT repeat these if they didn't work)
{chr(10).join(history_lines)}

IMPORTANT: If you've been clicking the same element multiple times without progress,
try a DIFFERENT action or element. The page may have a dropdown or menu that requires
clicking a different element after the first click.
"""

        # Build the prompt with index-based actions
        # Include visible page content so agent can see data values (not just interactive elements)
        page_content = observation.text_content[:3000] if observation.text_content else "(No text content visible)"
        
        prompt = f"""You are a browser automation agent. Complete the task by interacting with page elements.

## YOUR TASK
{task_instruction}

## CURRENT PAGE STATE
- URL: {observation.url}
- Title: {observation.title}
- Step: {self._step_count} of {self._task.max_steps if self._task else 30}
{error_section}{state_warning}{history_section}
## VISIBLE PAGE CONTENT (read this to find data values)
{page_content}

## INTERACTIVE ELEMENTS (use these indices for actions)
{observation.axtree[:4000] if observation.axtree else "No interactive elements found"}

## AVAILABLE ACTIONS
You must respond with exactly ONE action using element indices from the list above:

1. click(index)           - Click element [index] from the list above
                            Example: click(5) clicks element [5]

2. type(index, "text")    - Type text into input element [index]
                            Example: type(3, "search query")

3. select(index, "value") - Select option in dropdown element [index]
                            Example: select(7, "Option A")

4. press("key")           - Press a keyboard key
                            Valid keys: Enter, Tab, Escape, Backspace, ArrowUp, ArrowDown

5. scroll("direction")    - Scroll the page
                            Valid directions: up, down

6. goto("url")            - Navigate to a specific URL
                            Example: goto("http://localhost:3000/dashboard")

7. answer("value")        - Report the answer/result for the task
                            Example: answer("Order ID: 12345")
                            Use when the task asks you to find, identify, or report a value

8. done()                 - Signal that the task is COMPLETE (no answer needed)
                            Only use when the task objective has been achieved and no value needs to be reported

## IMPORTANT RULES
- Use element INDICES (numbers) from the list above, NOT CSS selectors
- If you don't see the element you need, try scroll("down") first
- If an action fails, try a different approach or element
- If you've tried the same action multiple times, TRY SOMETHING DIFFERENT
- CRITICAL: After clicking a button (like "New"), a dropdown/menu may appear with NEW elements.
  Look at the INTERACTIVE ELEMENTS list carefully for these new options and click on them!
- Do NOT click the same button repeatedly - if a menu appeared, click the menu item you want
- Think step by step before choosing your action

## WHEN TO USE answer()
- If the task asks you to "find", "report", "what is", or "identify" a value, you MUST use answer() once you find it
- Look at the page content and interactive elements - if you can see the value you're looking for, call answer() immediately
- Do NOT keep navigating or filtering if you can already see the answer on the current page
- Example: If asked "What is the unit price?" and you see "Unit Price: 42.50" on the page, call answer("42.50")

## YOUR RESPONSE FORMAT
You MUST respond in this exact format:

Reasoning: [1-2 sentences explaining your reasoning]
Action: [exactly one action from the list above]

CRITICAL RULES FOR YOUR ACTION:
- Write ONLY the action function call after "Action:"
- Do NOT write explanations, observations, or JSON after "Action:"
- Do NOT repeat the element list or page content
- Examples of CORRECT responses:
  Reasoning: I need to click the Submit button to proceed.
  Action: click(15)
  
  Reasoning: I should type the search query.
  Action: type(3, "hello world")

- Examples of INCORRECT responses:
  Action: I will click on element 15 which is the submit button  <- WRONG (explanation instead of action)
  Action: JSON object with element and type fields  <- WRONG (JSON instead of action)

Action:"""
        return prompt

    def _parse_llm_response(self, response: str) -> AgentAction:
        """Parse LLM response into an AgentAction.
        
        Handles various response formats:
        1. Clean action on its own line
        2. Action embedded in reasoning text
        3. Action after "Action:" label
        """
        response_stripped = response.strip()
        
        # Check if response looks like garbage (e.g., dumped JSON observation)
        if self._looks_like_garbage(response_stripped):
            logger.warning("Model output appears to be malformed (possible observation dump)")
            return self._fallback_action()
        
        # First, try to find action after an "Action:" label
        action_label_match = re.search(
            r'(?:^|\n)\s*(?:Action|action|ACTION)\s*:\s*(.+?)(?:\n|$)',
            response_stripped,
            re.MULTILINE
        )
        if action_label_match:
            action_text = action_label_match.group(1).strip()
            action = self._parse_browsergym_action(action_text, reasoning=response[:200])
            if action.action_type != "wait":
                return action
        
        # Try to parse the entire response (action might be embedded in text)
        action = self._parse_browsergym_action(response_stripped, reasoning=response[:200])
        if action.action_type != "wait":
            return action
        
        # Try each line separately (from end, since action often comes last)
        lines = response_stripped.split("\n")
        for line in reversed(lines):
            line = line.strip()
            if not line or len(line) < 4:
                continue
            
            # Skip lines that look like JSON or observation data
            if line.startswith('{') or line.startswith('"') or line.startswith('['):
                continue

            action = self._parse_browsergym_action(line, reasoning=response[:200])
            if action.action_type != "wait":
                return action

        return self._fallback_action()
    
    def _looks_like_garbage(self, text: str) -> bool:
        """Check if the response looks like malformed output (e.g., JSON dump)."""
        # Count JSON-like patterns
        json_patterns = [
            r'"[a-z_]+"\s*:',  # JSON keys
            r'"bounding_box"',
            r'"node_id"',
            r'"element"',
            r'"attributes"',
        ]
        
        json_count = sum(1 for pattern in json_patterns if re.search(pattern, text))
        
        # If more than 3 JSON patterns found, likely garbage
        if json_count >= 3:
            return True
        
        # If response is mostly JSON-like lines
        lines = text.split('\n')
        json_lines = sum(1 for line in lines if line.strip().startswith(('{', '}', '"', '[')))
        if len(lines) > 5 and json_lines / len(lines) > 0.5:
            return True
        
        return False

    def _fallback_action(self) -> AgentAction:
        """Return a fallback action when parsing fails."""
        max_steps = self._task.max_steps if self._task else 30
        if self._step_count >= max_steps:
            return AgentAction.done(reasoning="Fallback: max steps reached")
        return AgentAction.wait(timeout=1000, reasoning="Fallback: could not determine action")

    def get_history(self) -> list[tuple[Observation, AgentAction]]:
        """Return the history of observations and actions."""
        return self._history.copy()
