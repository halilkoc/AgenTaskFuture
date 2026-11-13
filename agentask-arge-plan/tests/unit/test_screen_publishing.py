"""R3 yayın/çalıştırma kuralları (sahte depo): ekran revizyonları, manifest kapsamı, eski yayın reddi, geçiş
akışı, önizlemede bağlı değerler. Gerçek MongoDB roundtrip'i integration/mongo/test_mongo_screens.py'dedir."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentask.application.errors import DraftNotReady, MigrationRequired, PlanInvalid, StaleApproval
from agentask.application.services.assistant import AssistantService
from agentask.application.services.designer import DesignerService
from agentask.application.services.publishing import PublishService
from agentask.domain.catalog import OperationDraft, ParameterDef
from agentask.domain.release import ReleaseManifest
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.llm.unavailable import UnavailableLLM
from tests.fake_catalog_store import FakeCatalogStore
from tests.legacy_catalog import seed_legacy_release
from tests.screens import PARTIES_SCREEN
from tests.unit.test_publishing import ready_draft


class NoRuns:
    """Run oluşturulursa test başarısız olur: reddedilen planda hiçbir yürütme başlamamalı."""

    def __init__(self) -> None:
        self.created: list[Any] = []

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        self.created.append((args, kwargs))
        raise AssertionError("reddedilmesi gereken plan için run oluşturuldu")


@pytest.fixture
def env(tmp_path: Path):  # type: ignore[no-untyped-def]
    store, repo = FakeCatalogStore(), LocalFileDraftRepository(tmp_path / "drafts")
    pub = PublishService(store, repo, LAB_ACTION_SET, environment="arge")
    runs = NoRuns()
    assistant = AssistantService(
        pub,
        runs,  # type: ignore[arg-type]
        LAB_ACTION_SET,
        UnavailableLLM("kapalı"),
        max_input_tokens=2000,
        max_output_tokens=200,
        max_calls=1,
        application_id="lab",
        composition_enabled=True,
    )
    designer = DesignerService(
        repo,
        None,  # type: ignore[arg-type]  # geçiş akışı tarayıcı kullanmaz
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        LAB_ACTION_SET,
        run_timeout_s=1,
        publishing=pub,
    )
    return pub, store, repo, assistant, designer, runs


async def publish(pub: PublishService, repo: LocalFileDraftRepository, d: OperationDraft, req: str):  # type: ignore[no-untyped-def]
    d = pub.approve("pub", d.draft_id, d.revision)
    return await pub.publish("pub", d.draft_id, req)


async def test_publish_writes_screen_revision_and_manifest_covers_it(env) -> None:  # type: ignore[no-untyped-def]
    pub, store, repo, *_ = env
    d = ready_draft(repo)
    release = await publish(pub, repo, d, "r1")
    screen_rev = store.screens[("lab", "basvuru_taraflar", 1)]
    assert screen_rev.content_hash == PARTIES_SCREEN.content_hash()
    assert screen_rev.definition == PARTIES_SCREEN.model_dump(mode="json")
    op_rev = store.revisions[("lab", "kefil_no", 1)]
    assert op_rev.definition["screen_ref"] == PARTIES_SCREEN.ref()
    assert op_rev.schema_version == "catalog-v2"
    assert [(s.screen_id, s.revision) for s in release.screens] == [("basvuru_taraflar", 1)]
    assert release.manifest_hash == ReleaseManifest.compute_hash(
        "lab", "arge", release.operations, release.screens
    )
    # Onay hash'i ekranı kapsar: ekran değişince onay geçersizdir.
    approval = release.approvals[0]
    assert approval.content_hash == op_rev.content_hash
    d = repo.get(d.draft_id)
    assert d is not None
    d.screen = PARTIES_SCREEN.model_copy(update={"title": "Değişti"})
    repo.update(d, d.revision)
    with pytest.raises(StaleApproval):
        await pub.publish("pub", d.draft_id, "r2")


async def test_shared_screen_reused_and_changed_screen_gets_new_revision(env) -> None:  # type: ignore[no-untyped-def]
    pub, store, repo, *_ = env
    first = await publish(pub, repo, ready_draft(repo, "op_a", "A"), "a")
    second = await publish(pub, repo, ready_draft(repo, "op_b", "B"), "b")
    assert len(store.screens) == 1 and len(second.screens) == 1
    changed = ready_draft(repo, "op_c", "C")
    changed.screen = PARTIES_SCREEN.model_copy(update={"title": "Yeni başlık"})
    changed.record_fresh_test(run_id="run-fresh0002", passed=True)
    repo.update(changed, changed.revision)
    third = await publish(pub, repo, changed, "c")
    assert sorted(s.revision for s in third.screens) == [1, 2]  # op_a/op_b eski, op_c yeni ekranı kullanır
    old = await pub.release(first.release_id)
    assert old is not None and [s.revision for s in old.screens] == [1]  # eski manifest yerinde


async def test_failure_after_screen_write_never_activates(env) -> None:  # type: ignore[no-untyped-def]
    pub, store, repo, *_ = env
    d = pub.approve("pub", ready_draft(repo).draft_id, 1)
    store.fail_after = "put_screen"
    with pytest.raises(RuntimeError):
        await pub.publish("pub", d.draft_id, "r1")
    assert store.active == {} and store.revisions == {}


async def test_screenless_draft_cannot_be_approved(env) -> None:  # type: ignore[no-untyped-def]
    pub, _, repo, *_ = env
    d = ready_draft(repo)
    d.screen = None
    repo.update(d, d.revision)
    with pytest.raises(DraftNotReady) as err:
        pub.approve("pub", d.draft_id, d.revision)
    assert "screen_missing" in err.value.details["issues"]  # type: ignore[operator]


async def test_legacy_operation_rejected_with_migration_required(env) -> None:  # type: ignore[no-untyped-def]
    _, store, repo, assistant, _, runs = env
    legacy = await seed_legacy_release(store, ready_draft(repo, "kefil_musteri_no", "Kefil müşteri no"))
    before = (dict(store.revisions), dict(store.releases), dict(store.active))
    catalog = await assistant.catalog()
    assert [(o.operation_id, o.migration_required) for o in catalog] == [("kefil_musteri_no", True)]
    with pytest.raises(MigrationRequired) as err:
        await assistant.preview("ayse", legacy.release_id, "kefil_musteri_no", {"no": "00456"})
    assert err.value.details == {
        "reason": "migration_required",
        "operation_id": "kefil_musteri_no",
        "revision": 1,
    }
    with pytest.raises(MigrationRequired):
        await assistant.execute("ayse", "sid", legacy.release_id, "kefil_musteri_no", {"no": "1"}, "q1")
    plan = {
        "nodes": [{"kind": "call_operation", "operation_id": "kefil_musteri_no", "arguments": {"no": "1"}}]
    }
    with pytest.raises(MigrationRequired):
        await assistant.composite_preview("ayse", plan)
    with pytest.raises(MigrationRequired):
        await assistant.composite_execute("ayse", "sid", legacy.release_id, plan, "q2")
    assert runs.created == []
    assert (store.revisions, store.releases, store.active) == before  # hiçbir şey yazılmadı


async def test_migration_flow_creates_new_revision_and_keeps_legacy(env) -> None:  # type: ignore[no-untyped-def]
    pub, store, repo, assistant, designer, _ = env
    source = ready_draft(repo, "kefil_musteri_no", "Kefil müşteri no")
    legacy = await seed_legacy_release(store, source)
    legacy_rev = store.revisions[("lab", "kefil_musteri_no", 1)].model_copy(deep=True)
    legacy_release = store.releases[legacy.release_id].model_copy(deep=True)

    candidates = await designer.migration_candidates("lab")
    assert [o["operation_id"] for o in candidates["operations"]] == ["kefil_musteri_no"]
    draft = await designer.start_migration("ayse", "lab", "kefil_musteri_no")
    assert draft.migrated_from is not None and draft.migrated_from.revision == 1
    assert draft.screen is None and "screen_missing" in draft.validation_issues(LAB_ACTION_SET)
    assert all(s.intent_text for s in draft.steps)
    with pytest.raises(DraftNotReady):
        pub.approve("pub", draft.draft_id, draft.revision)
    # Geçiş taslağı da yeni oturum testi olmadan onaylanamaz (eski test kanıtı taşınmaz).
    draft.screen = PARTIES_SCREEN
    repo.update(draft, draft.revision)
    draft = repo.get(draft.draft_id)
    assert draft is not None and "fresh_session_test_missing" in draft.validation_issues(LAB_ACTION_SET)
    draft.record_fresh_test(run_id="run-migr0001", passed=True)
    repo.update(draft, draft.revision)
    draft = repo.get(draft.draft_id)
    assert draft is not None
    release = await publish(pub, repo, draft, "migr-1")

    assert [(o.operation_id, o.revision) for o in release.operations] == [("kefil_musteri_no", 2)]
    assert release.base_release_id == legacy.release_id and release.screens
    assert store.revisions[("lab", "kefil_musteri_no", 1)] == legacy_rev  # r1 yerinde, değişmedi
    assert store.releases[legacy.release_id] == legacy_release
    preview = await assistant.preview("ayse", release.release_id, "kefil_musteri_no", {"no": "00456"})
    assert preview["revision"] == 2 and preview["commands"][0]["op"] == "assert_screen"
    with pytest.raises(PlanInvalid) as err:
        await designer.start_migration("ayse", "lab", "kefil_musteri_no")
    assert err.value.details["reason"] == "migration_not_required"


async def test_preview_shows_bound_values_and_masks_sensitive(env) -> None:  # type: ignore[no-untyped-def]
    pub, _, repo, assistant, *_ = env
    d = ready_draft(repo)
    d.steps[0].standard_text = "'Kefil müşteri no' alanına {no} değerini yaz"
    d.parameters.append(
        ParameterDef(
            name="kart",
            title="Kayıtlı ödeme aracı",
            max_length=20,
            source="approved_constant",
            constant="4111111111111111",
        )
    )
    d.steps[0].value_template = "{no}"
    d.record_fresh_test(run_id="run-fresh0003", passed=True)
    repo.update(d, d.revision)
    release = await publish(pub, repo, d, "p1")
    preview = await assistant.preview("ayse", release.release_id, "kefil_no", {"no": "00456"})
    assert preview["steps"] == [
        "Ekranı doğrula: Başvuru — taraf bilgileri",
        "'Kefil müşteri no' alanına 00456 değerini yaz",
    ]
    assert not any("{" in s for s in preview["steps"])
    bindings = {b["name"]: b["value"] for b in preview["bindings"]}
    assert bindings == {"no": "00456", "kart": "••••"}
    assert "4111111111111111" not in str(preview)
    with pytest.raises(PlanInvalid) as err:  # hassas kullanıcı argümanı önizlemeye bile alınmaz
        await assistant.preview("ayse", release.release_id, "kefil_no", {"no": "parola Gizli123"})
    assert err.value.details["reason"] == "sensitive_argument"
