import json
from types import SimpleNamespace

import pytest
import tiktoken
from agentlab.agents import dynamic_prompting
from agentlab.llm.llm_utils import Discussion, HumanMessage
from browsergym.experiments.agent import AgentInfo

from webarena_pro_bgym.agentlab_compat import count_prompt_tokens, normalize_agent_info
from webarena_pro_bgym.study import WebArenaProExpArgs, WebArenaProStepInfo


@pytest.mark.parametrize("text", ["ordinary page text", "literal <|endoftext|> and <|fim_prefix|>"])
def test_prompt_and_step_accounting_treat_control_token_strings_as_text(text):
    encoding = tiktoken.encoding_for_model("gpt-4")
    expected = len(encoding.encode(text, disallowed_special=()))
    assert count_prompt_tokens(text, model="gpt-4") == expected
    assert dynamic_prompting.count_tokens(text, model="gpt-4") == expected
    step = WebArenaProStepInfo(
        obs={"axtree_txt": text},
        agent_info=AgentInfo(stats={"cost": 0.25}, chat_messages=Discussion([
            HumanMessage([{"type": "text", "text": text},
                          {"type": "image_url", "image_url": {"url": "data:image/png;base64,test"}}]),
        ])),
    )
    step.make_stats()
    assert step.stats["n_token_axtree_txt"] == expected
    assert step.stats["n_token_agent_messages"] == expected
    assert step.stats["cost"] == 0.25
    assert step.agent_info["chat_messages"][0]["content"][0]["text"] == text
    # The adaptation never changes tiktoken's behavior outside accounting.
    with pytest.raises(ValueError, match="special token"):
        encoding.encode("<|endoftext|>")


def test_non_tiktoken_tokenizer_keeps_its_supported_encode_signature(monkeypatch):
    seen = []
    def encode(text):
        seen.append(text)
        return [11, 12]
    monkeypatch.setattr(
        "webarena_pro_bgym.agentlab_compat.llm_utils.get_tokenizer",
        lambda model: SimpleNamespace(encode=encode),
    )
    assert count_prompt_tokens("literal <|endoftext|>", model="fixture") == 2
    assert seen == ["literal <|endoftext|>"]


@pytest.mark.parametrize("error", [None, "RuntimeError: original episode error"])
def test_summary_accepts_unprocessed_agent_info_and_preserves_nested_data(tmp_path, error):
    nested = AgentInfo(think="recorded", extra_info={"score": 0.25})
    info = AgentInfo(extra_info={"nested": [nested]}, chat_messages=Discussion([
        HumanMessage("retained observation"),
    ]))
    step = WebArenaProStepInfo(step=0, agent_info=info, terminated=error is None)
    exp = WebArenaProExpArgs.__new__(WebArenaProExpArgs)
    exp.env_args = SimpleNamespace(max_steps=100)
    exp.save_summary_info([step], tmp_path, error, "original trace" if error else None)
    summary = json.loads((tmp_path / "summary_info.json").read_text())
    assert summary["err_msg"] == error
    assert summary["stack_trace"] == ("original trace" if error else None)
    assert json.loads(json.dumps(step.agent_info))["extra_info"]["nested"][0] == normalize_agent_info(nested)
    assert step.agent_info["chat_messages"] == [{"role": "user", "content": "retained observation"}]
    assert info.extra_info["nested"][0] is nested  # no mutation of agent-owned data
