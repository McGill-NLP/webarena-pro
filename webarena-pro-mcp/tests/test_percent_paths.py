from urllib.parse import quote

import pytest

from webarena_pro_mcp.tool_policy import PolicyError, URLPolicy, canonical_path


GOAL = "Achieve CPU yields of 80% per wafer"
GOAL_PATH = "/app/quality-goal/" + quote(GOAL, safe="")


@pytest.mark.parametrize("path,expected", [
    (GOAL_PATH, "/app/quality-goal/" + GOAL),
    ("/documents/80%25", "/documents/80%"),
    ("/documents/80%2525", "/documents/80%"),
    ("/documents/%25GG", "/documents/%GG"),
    ("/documents/%25%20complete", "/documents/% complete"),
    ("/documents/%E2%82%AC%20and%20%25", "/documents/€ and %"),
    ("/documents/folder%2Fname", "/documents/folder/name"),
])
def test_percent_encoded_identifiers_are_allowed(path, expected):
    assert canonical_path(path) == expected
    URLPolicy(["http://erp-next:8000"]).check("http://erp-next:8000" + path, navigation=True)


@pytest.mark.parametrize("path", [
    "/documents/%", "/documents/%2", "/documents/%GG", "/documents/%0g",
    "/documents/valid%25-and-invalid%", "/documents/%FF", "/documents/%C0%AF",
    "/documents/%25FF", "/documents/%25C0%25AF",
    "/documents/%255creset", "/documents/%2500reset", "/documents/%0Areset",
])
def test_malformed_escapes_and_unsafe_decoding_remain_blocked(path):
    with pytest.raises(PolicyError, match="Ambiguous URL path"):
        URLPolicy(["http://erp-next:8000"]).check("http://erp-next:8000" + path)


@pytest.mark.parametrize("path", [
    "/%2572eset", "/%25%37%32eset", "/public%2F..%2Freset",
    "/public%252F..%252Freset", "/public/%252e%252e/eval_state.php",
    "/public/%2e%2e/api%2feval/state", "/%252fbenchmark",
    "/custom%252dprivate/child", "/reset%253Bignored", "/api%252fusers",
])
def test_nested_escapes_cannot_hide_private_routes_or_api_navigation(path):
    policy = URLPolicy(["http://erp-next:8000"], blocked_paths=["/custom-private"])
    with pytest.raises(PolicyError):
        policy.check("http://erp-next:8000" + path, navigation=True)


def test_percent_literal_does_not_disable_deeper_escape_checks():
    # One harmless percent must not stop decoding later escaped path segments.
    with pytest.raises(PolicyError, match="private"):
        URLPolicy(["http://erp-next:8000"]).check(
            "http://erp-next:8000/80%25%20complete/%2572eset"
        )


def test_nested_encoding_budget_still_fails_closed():
    path = "/reset"
    for _ in range(9):
        path = quote(path, safe="")
    with pytest.raises(PolicyError, match="Ambiguous URL path"):
        canonical_path(path)


def test_percent_identifiers_do_not_allow_other_origins():
    with pytest.raises(PolicyError, match="outside"):
        URLPolicy(["http://erp-next:8000"]).check("http://other.test" + GOAL_PATH)
