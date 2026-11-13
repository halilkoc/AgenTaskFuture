from __future__ import annotations

import pytest

from agentask.domain.origins import OriginPolicy, normalize_origin


def test_normalize_origin_lowercases_and_strips_slash() -> None:
    assert normalize_origin("HTTP://127.0.0.1:8100/") == "http://127.0.0.1:8100"


@pytest.mark.parametrize("bad", ["ftp://x", "http://", "http://h/path", "http://u:p@h", "http://h?q=1"])
def test_normalize_origin_rejects_non_origins(bad: str) -> None:
    with pytest.raises(ValueError):
        normalize_origin(bad)


@pytest.fixture
def policy() -> OriginPolicy:
    return OriginPolicy(["http://127.0.0.1:8100", "http://127.0.0.1:8101"])


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8100/pages/frames?x=1", "http://127.0.0.1:8101/frames/cross", "about:blank"],
)
def test_policy_allows_listed_origins(policy: OriginPolicy, url: str) -> None:
    assert policy.allows(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8102/",
        "https://127.0.0.1:8100/",
        "http://localhost:8100/",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "data:text/html,hi",
        "http://127.0.0.1:8100@evil.example/",
        "not a url",
    ],
)
def test_policy_rejects_everything_else(policy: OriginPolicy, url: str) -> None:
    assert not policy.allows(url)
