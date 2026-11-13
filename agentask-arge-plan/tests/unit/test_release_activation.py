"""Etkin yayını geri/ileri alma (K3): gerekçe, uyum, CAS, değişmezlik."""

from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path
from typing import Any

import pytest

from agentask.application.errors import PlanInvalid, PublishConflict
from agentask.application.services.publishing import PublishService
from agentask.domain.actions import ActionSet
from agentask.domain.catalog import StepStatus
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from tests.fake_catalog_store import FakeCatalogStore
from tests.unit.test_component_publishing import component_draft, publish
from tests.wizard import CUSTOMER_SCREEN

REASON = "Yeni sürümde hata bulundu"


@dataclasses.dataclass
class Env:
    pub: PublishService
    repo: LocalFileDraftRepository
    store: FakeCatalogStore
    first: str
    second: str


@pytest.fixture
async def env(tmp_path: Path) -> Env:
    store, repo = FakeCatalogStore(), LocalFileDraftRepository(tmp_path / "d")
    pub = PublishService(store, repo, LAB_ACTION_SET, environment="arge")
    first = await publish(pub, repo, component_draft("Birinci"), "req-1")
    second = await publish(pub, repo, component_draft("İkinci"), "req-2")
    return Env(pub, repo, store, first, second)


async def active(env: Env) -> str:
    pointer = await env.store.get_active("lab", "arge")
    assert pointer is not None
    return pointer.release_id


async def test_rollback_and_forward_keep_every_release(env: Env) -> None:
    before = dict(env.store.revisions)
    await env.pub.activate_release("yayinci", env.first, env.second, REASON)
    assert await active(env) == env.first
    await env.pub.activate_release("yayinci", env.second, env.first, "Düzeltme doğrulandı, ileri alındı")
    assert await active(env) == env.second
    assert env.store.revisions == before and {r.release_id for r in await env.pub.releases("lab")} >= {
        env.first,
        env.second,
    }
    history = await env.pub.activations("lab")
    assert [h.to_release_id for h in history] == [env.second, env.first] and history[1].reason == REASON
    assert history[1].by == "yayinci" and history[1].from_release_id == env.second


@pytest.mark.parametrize("reason", ["", "kisa", "         uzak      "])
async def test_reason_is_required(env: Env, reason: str) -> None:
    with pytest.raises(PlanInvalid):
        await env.pub.activate_release("y", env.first, env.second, reason)
    assert await active(env) == env.second


async def test_stale_expected_and_already_active_are_refused(env: Env) -> None:
    with pytest.raises(PublishConflict, match="değişti"):
        await env.pub.activate_release("y", env.first, env.first, REASON)
    with pytest.raises(PublishConflict, match="zaten etkin"):
        await env.pub.activate_release("y", env.second, env.second, REASON)


async def test_concurrent_activation_has_one_winner(env: Env) -> None:
    env.store.cas_delay = 0.01
    results = await asyncio.gather(
        env.pub.activate_release("a", env.first, env.second, REASON),
        env.pub.activate_release("b", env.first, env.second, REASON),
        return_exceptions=True,
    )
    assert sum(isinstance(r, PublishConflict) for r in results) == 1
    assert len(await env.pub.activations("lab")) == 1


ACTION: dict[str, Any] = {
    "action_id": "kurum.kaydet",
    "title": "Kaydet",
    "application_id": "lab",
    "target": {"kind": "button", "labels": ["Kaydet"]},
    "effect": "non_mutating",
    "retry_safe": False,
    "params": [],
    "outcome": {"evidence": {"kind": "status_text"}, "success": {"mode": "contains", "text": "Tamam"}},
}


async def test_release_with_changed_action_cannot_be_activated(tmp_path: Path) -> None:
    actions = ActionSet.model_validate({"actions": {"kurum.kaydet": ACTION}})
    store, repo = FakeCatalogStore(), LocalFileDraftRepository(tmp_path / "d")
    pub = PublishService(store, repo, actions, environment="arge")
    draft = component_draft("Aksiyonlu")
    step = draft.add_step("kaydet")
    step.op, step.action_id = "invoke_approved_action", "kurum.kaydet"
    step.action_hash = actions.fingerprint("kurum.kaydet")
    step.status = StepStatus.INTENT_ENTERED
    assert draft.screen == CUSTOMER_SCREEN
    old = await publish(pub, repo, draft, "req-a")
    new = await publish(pub, repo, component_draft("Aksiyonsuz"), "req-b")
    changed = ActionSet.model_validate({"actions": {"kurum.kaydet": {**ACTION, "retry_safe": True}}})
    stricter = PublishService(store, repo, changed, environment="arge")
    with pytest.raises(PublishConflict) as caught:
        await stricter.activate_release("y", old, new, REASON)
    assert caught.value.details["reason"] == "incompatible_actions"
    assert "action_changed" in str(caught.value.details["problems"])
    pointer = await store.get_active("lab", "arge")
    assert pointer is not None and pointer.release_id == new
