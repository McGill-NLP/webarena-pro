"""Agent observation and action models."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Observation:
    """Represents what the agent observes from the browser.

    This captures the current state of the page for the agent to make decisions.
    """

    url: str
    title: str
    text_content: str
    html_snapshot: str
    screenshot_path: str | None = None
    screenshot_bytes: bytes | None = None
    axtree: str = ""
    last_action: str = ""
    last_action_error: str = ""
    metadata: dict = field(default_factory=dict)

    def summary(self) -> str:
        """Return a brief summary of the observation."""
        return f"URL: {self.url}, Title: {self.title}, Content length: {len(self.text_content)}"

    def has_screenshot(self) -> bool:
        """Check if screenshot is available."""
        return self.screenshot_bytes is not None or self.screenshot_path is not None

    def has_error(self) -> bool:
        """Check if last action resulted in an error."""
        return bool(self.last_action_error)


ActionType = Literal["click", "type", "press", "navigate", "scroll", "select", "wait", "done", "answer"]


@dataclass
class AgentAction:
    """Represents an action the agent wants to execute.

    Different action types use different fields:
    - click: element_index (preferred) OR selector OR coordinates
    - type: element_index (preferred) OR selector (optional) + text
    - press: key
    - navigate: url
    - scroll: direction + amount
    - select: element_index OR selector + value
    - wait: timeout
    - done: signals task completion
    """

    action_type: ActionType
    element_index: int | None = None
    selector: str | None = None
    text: str | None = None
    key: str | None = None
    url: str | None = None
    coordinates: tuple[int, int] | None = None
    direction: Literal["up", "down", "left", "right"] | None = None
    amount: int | None = None
    value: str | None = None
    timeout: int | None = None
    reasoning: str = ""

    @classmethod
    def click(cls, selector: str, reasoning: str = "") -> "AgentAction":
        """Create a click action with a CSS selector."""
        return cls(action_type="click", selector=selector, reasoning=reasoning)

    @classmethod
    def click_index(cls, index: int, reasoning: str = "") -> "AgentAction":
        """Create a click action using element index from axtree."""
        return cls(action_type="click", element_index=index, reasoning=reasoning)

    @classmethod
    def type_text(cls, text: str, selector: str | None = None, reasoning: str = "") -> "AgentAction":
        """Create a type action with optional CSS selector."""
        return cls(action_type="type", selector=selector, text=text, reasoning=reasoning)

    @classmethod
    def type_index(cls, index: int, text: str, reasoning: str = "") -> "AgentAction":
        """Create a type action using element index from axtree."""
        return cls(action_type="type", element_index=index, text=text, reasoning=reasoning)

    @classmethod
    def press_key(cls, key: str, reasoning: str = "") -> "AgentAction":
        """Create a key press action."""
        return cls(action_type="press", key=key, reasoning=reasoning)

    @classmethod
    def navigate_to(cls, url: str, reasoning: str = "") -> "AgentAction":
        """Create a navigation action."""
        return cls(action_type="navigate", url=url, reasoning=reasoning)

    @classmethod
    def scroll(
        cls,
        direction: Literal["up", "down"] = "down",
        amount: int = 300,
        reasoning: str = "",
    ) -> "AgentAction":
        """Create a scroll action."""
        return cls(action_type="scroll", direction=direction, amount=amount, reasoning=reasoning)

    @classmethod
    def select_option(cls, selector: str, value: str, reasoning: str = "") -> "AgentAction":
        """Create a select action with CSS selector."""
        return cls(action_type="select", selector=selector, value=value, reasoning=reasoning)

    @classmethod
    def select_index(cls, index: int, value: str, reasoning: str = "") -> "AgentAction":
        """Create a select action using element index from axtree."""
        return cls(action_type="select", element_index=index, value=value, reasoning=reasoning)

    @classmethod
    def wait(cls, timeout: int = 1000, reasoning: str = "") -> "AgentAction":
        """Create a wait action."""
        return cls(action_type="wait", timeout=timeout, reasoning=reasoning)

    @classmethod
    def done(cls, reasoning: str = "") -> "AgentAction":
        """Signal that the task is complete."""
        return cls(action_type="done", reasoning=reasoning)

    @classmethod
    def answer(cls, value: str, reasoning: str = "") -> "AgentAction":
        """Report an answer/value for the task."""
        return cls(action_type="answer", value=value, reasoning=reasoning)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "action_type": self.action_type,
            "element_index": self.element_index,
            "selector": self.selector,
            "text": self.text,
            "key": self.key,
            "url": self.url,
            "coordinates": self.coordinates,
            "direction": self.direction,
            "amount": self.amount,
            "value": self.value,
            "timeout": self.timeout,
            "reasoning": self.reasoning,
        }

    def describe(self) -> str:
        """Return human-readable description of the action."""
        if self.action_type == "click":
            target = f"[{self.element_index}]" if self.element_index is not None else self.selector
            return f"click({target})"
        elif self.action_type == "type":
            target = f"[{self.element_index}]" if self.element_index is not None else self.selector
            return f"type({target}, \"{self.text}\")"
        elif self.action_type == "press":
            return f"press(\"{self.key}\")"
        elif self.action_type == "navigate":
            return f"goto(\"{self.url}\")"
        elif self.action_type == "scroll":
            return f"scroll(\"{self.direction}\")"
        elif self.action_type == "select":
            target = f"[{self.element_index}]" if self.element_index is not None else self.selector
            return f"select({target}, \"{self.value}\")"
        elif self.action_type == "wait":
            return f"wait({self.timeout})"
        elif self.action_type == "done":
            return "done()"
        elif self.action_type == "answer":
            return f"answer(\"{self.value}\")"
        return f"{self.action_type}(...)"
