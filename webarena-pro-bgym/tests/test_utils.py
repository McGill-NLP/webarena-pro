import pytest

from webarena_pro_bgym.utils import get_completion_kwargs, get_qwen_completion_kwargs


@pytest.mark.parametrize(
    ("enable_thinking", "temperature", "top_p"),
    [
        (True, 0.6, 0.95),
        (False, 0.7, 0.8),
    ],
)
def test_qwen_completion_kwargs_follow_enable_thinking_flag(
    enable_thinking,
    temperature,
    top_p,
):
    kwargs = get_completion_kwargs(
        model="Qwen/Qwen3.5-9B",
        enable_thinking=enable_thinking,
    )

    assert get_qwen_completion_kwargs(enable_thinking) == {
        "temperature": temperature,
        "top_p": top_p,
    }
    assert kwargs["temperature"] == temperature
    assert kwargs["top_p"] == top_p
    assert kwargs["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
