"""Compatibility at the WebArena-Pro/AgentLab boundary.

AgentLab 0.4.2 and BrowserGym 0.14.2 count arbitrary observation text with
tiktoken's control-token rejection enabled. Their loop also treats AgentInfo
as a mutable dict on failure, although AgentInfo is a dataclass. Keep these
adaptations local to prompt accounting and the WebArena-Pro step artifacts.
"""

from dataclasses import fields

import tiktoken
from browsergym.experiments.agent import AgentInfo
from agentlab.llm import llm_utils


def count_prompt_tokens(text, model="openai/gpt-4"):
    """Use AgentLab's tokenizer selection, treating page text as ordinary text."""
    tokenizer = llm_utils.get_tokenizer(model)
    if isinstance(tokenizer, tiktoken.Encoding):
        return len(tokenizer.encode(text, disallowed_special=()))
    # HuggingFace tokenizers do not support tiktoken's keyword argument.
    return len(tokenizer.encode(text))


def count_observation_tokens(text, model="gpt-4"):
    return len(tiktoken.encoding_for_model(model).encode(text, disallowed_special=()))


def count_message_tokens(messages, model="gpt-4"):
    """Match BrowserGym's text-only message accounting, including multimodal lists."""
    total = 0
    for message in messages:
        if hasattr(message, "content"):
            message = message.content
        elif isinstance(message, dict) and "content" in message:
            message = message["content"]
        if isinstance(message, str):
            total += count_observation_tokens(message, model)
        elif isinstance(message, (list, tuple)):
            for part in message:
                if not isinstance(part, dict):
                    raise ValueError("Message content parts must be dictionaries")
                if part["type"] == "text":
                    total += count_observation_tokens(part["text"], model)
        else:
            raise ValueError(f"Unsupported message content: {type(message)}")
    return total


def normalize_agent_info(value):
    """Preserve AgentInfo fields and nested messages as portable data, not reprs."""
    if isinstance(value, AgentInfo):
        value = {field.name: getattr(value, field.name) for field in fields(value)}
    if isinstance(value, llm_utils.Discussion):
        # Read the supported message sequence without mutating it via merge().
        value = list(value)
    if isinstance(value, dict):
        return {key: normalize_agent_info(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [normalize_agent_info(item) for item in value]
    return value
