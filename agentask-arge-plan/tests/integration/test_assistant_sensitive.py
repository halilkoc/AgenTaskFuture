"""R1: Asistan hassas veri sınırı — model çağrısına giden gerçek payload test ikamesiyle doğrulanır."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from agentask.application.errors import PlanInvalid
from agentask.application.ports.llm import LLMAvailability
from agentask.application.services.assistant import AssistantService
from agentask.application.services.publishing import PublishService
from agentask.application.services.runs import RunService
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.llm.unavailable import UnavailableLLM
from agentask.infrastructure.runs.local_file import LocalFileRunRepository
from tests.fake_catalog_store import FakeCatalogStore
from tests.unit.test_publishing import ready_draft

SECRET = "Gizli-Parola-77!"
CARD = "4111111111111111"


class RecordingLLM:
    """Kontrollü ikame: çağrıya giden system/user/schema içeriğini kaydeder."""

    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = answer
        self.payloads: list[dict[str, Any]] = []

    def availability(self) -> LLMAvailability:
        return LLMAvailability(True, "test")

    async def complete_json(
        self, system: str, user: str, schema: dict[str, Any], max_output_tokens: int
    ) -> Any:
        self.payloads.append({"system": system, "user": user, "schema": schema})
        return self.answer


async def make(tmp: Path, llm: Any) -> tuple[AssistantService, LocalFileRunRepository, str]:
    drafts = LocalFileDraftRepository(tmp / "drafts")
    publishing = PublishService(FakeCatalogStore(), drafts, LAB_ACTION_SET, "arge")
    d = ready_draft(drafts, "kefil_musteri_no", "Kefil müşteri numarasını gir")
    d.intent_phrases = ["kefil müşteri numarası gir"]
    d.record_fresh_test(run_id="run-fresh0001", passed=True)
    drafts.update(d, d.revision)
    d = publishing.approve("pub", d.draft_id, d.revision)
    release = await publishing.publish("pub", d.draft_id, "r1")
    repo = LocalFileRunRepository(tmp / "runs")
    runs = RunService(repo, None, None, LAB_ACTION_SET, 100)  # type: ignore[arg-type]  # reddedilen yol çalıştırmaz
    return (
        AssistantService(publishing, runs, LAB_ACTION_SET, llm, 2000, 100, 2, "lab"),
        repo,
        release.release_id,
    )


def dump(obj: Any) -> str:
    return json.dumps(asdict(obj), ensure_ascii=False)


async def test_clean_prompt_payload_is_exactly_prompt_and_catalog_slice(tmp_path: Path) -> None:
    llm = RecordingLLM({"operation_id": "kefil_musteri_no", "arguments": {}})
    assistant, _, _ = await make(tmp_path, llm)
    result = await assistant.interpret("ayse", "şunu halledebilir misin", use_model=True)
    assert result.provenance == "model_suggested" and len(llm.payloads) == 1
    user = json.loads(llm.payloads[0]["user"])
    assert set(user) == {"talep", "islemler"}
    assert user["talep"] == "şunu halledebilir misin"
    assert user["islemler"] == [
        {
            "operation_id": "kefil_musteri_no",
            "title": "Kefil müşteri numarasını gir",
            "intent_phrases": ["kefil müşteri numarası gir"],
            "parameters": [{"name": "no", "title": "No"}],
        }
    ]


async def test_secret_in_prompt_never_reaches_model_and_business_param_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    llm = RecordingLLM({"operation_id": "kefil_musteri_no", "arguments": {}})
    assistant, _, _ = await make(tmp_path, llm)
    result = await assistant.interpret(
        "ayse", f"Kefil müşteri numarasını 00123 olarak gir, parolam {SECRET}", use_model=True
    )
    assert llm.payloads == []
    assert result.operation_id == "kefil_musteri_no" and result.arguments == {"no": "00123"}
    assert result.status == "needs_clarification" and result.sensitive == ["secret_keyword"]
    assert SECRET not in dump(result) and SECRET not in caplog.text


async def test_secret_with_unmatched_prompt_asks_instead_of_calling_model(tmp_path: Path) -> None:
    llm = RecordingLLM({"operation_id": "kefil_musteri_no", "arguments": {}})
    assistant, _, _ = await make(tmp_path, llm)
    result = await assistant.interpret("ayse", f"şunu {CARD} kartıyla halledebilir misin", use_model=True)
    assert llm.payloads == [] and result.status == "needs_clarification"
    assert "payment_card" in result.sensitive and "hassas" in result.explanation
    assert CARD not in dump(result)


async def test_sensitive_value_not_bound_as_argument(tmp_path: Path) -> None:
    assistant, _, _ = await make(tmp_path, UnavailableLLM("disabled"))
    result = await assistant.interpret("ayse", f"Kefil müşteri numarasını {CARD} olarak gir")
    assert result.arguments == {} and result.missing == ["no"] and "payment_card" in result.sensitive
    assert CARD not in dump(result)


async def test_model_disabled_path_flags_without_call(tmp_path: Path) -> None:
    assistant, _, _ = await make(tmp_path, UnavailableLLM("disabled"))
    result = await assistant.interpret("ayse", f"parola {SECRET} ile bir şey yap", use_model=True)
    assert result.sensitive == ["secret_keyword"] and SECRET not in dump(result)


async def test_sensitive_argument_rejected_before_persistence(tmp_path: Path) -> None:
    assistant, repo, release_id = await make(tmp_path, UnavailableLLM("disabled"))
    for call in (
        assistant.preview("ayse", release_id, "kefil_musteri_no", {"no": CARD}),
        assistant.execute("ayse", "s1", release_id, "kefil_musteri_no", {"no": CARD}, "req-1"),
    ):
        with pytest.raises(PlanInvalid) as exc:
            await call
        assert exc.value.details["reason"] == "sensitive_argument"
        assert CARD not in json.dumps(exc.value.details)
    assert repo.list_all() == []
    ok = await assistant.preview("ayse", release_id, "kefil_musteri_no", {"no": "00123"})
    assert ok["commands"][0]["op"] == "assert_screen" and ok["commands"][1]["value"] == "00123"


async def test_composite_arguments_and_loop_items_checked(tmp_path: Path) -> None:
    drafts = LocalFileDraftRepository(tmp_path / "drafts")
    publishing = PublishService(FakeCatalogStore(), drafts, LAB_ACTION_SET, "arge")
    d = ready_draft(drafts, "kefil_musteri_no", "Kefil müşteri numarasını gir")
    d = publishing.approve("pub", d.draft_id, d.revision)
    await publishing.publish("pub", d.draft_id, "r1")
    repo = LocalFileRunRepository(tmp_path / "runs")
    runs = RunService(repo, None, None, LAB_ACTION_SET, 100, allow_composition=True)  # type: ignore[arg-type]
    assistant = AssistantService(
        publishing,
        runs,
        LAB_ACTION_SET,
        UnavailableLLM("disabled"),
        2000,
        100,
        2,
        "lab",
        composition_enabled=True,
    )
    direct = {
        "nodes": [{"kind": "call_operation", "operation_id": "kefil_musteri_no", "arguments": {"no": CARD}}]
    }
    loop = {
        "nodes": [
            {
                "kind": "for_each",
                "variable": "x",
                "items": ["001", CARD],
                "body": [
                    {"kind": "call_operation", "operation_id": "kefil_musteri_no", "arguments": {"no": "{x}"}}
                ],
            }
        ]
    }
    for plan in (direct, loop):
        with pytest.raises(PlanInvalid) as exc:
            await assistant.composite_preview("ayse", plan)
        assert exc.value.details["reason"] == "sensitive_argument" and CARD not in json.dumps(
            exc.value.details
        )
    assert repo.list_all() == []
