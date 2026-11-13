"""Composition root: Settings + adapterler burada birleştirilir. Başka modül adapter seçmez."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentask.application.controls import AdapterRegistry
from agentask.application.ports.artifacts import ArtifactIndex, ObjectStore
from agentask.application.ports.browser import BrowserContextFactory
from agentask.application.ports.identity import IdentityPort
from agentask.application.ports.llm import LLMPort
from agentask.application.services.artifacts import ArtifactService
from agentask.application.services.assistant import AssistantService
from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits
from agentask.application.services.designer import DesignerService
from agentask.application.services.executor import Executor, ExecutorConfig
from agentask.application.services.impact import ImpactService
from agentask.application.services.observation import ObservationService
from agentask.application.services.publishing import PublishService
from agentask.application.services.runs import RunService
from agentask.config.settings import (
    ApprovedActionSet,
    ArtifactBackend,
    ArtifactIndexBackend,
    AuthMode,
    CatalogBackend,
    Settings,
)
from agentask.domain.actions import ActionSet
from agentask.domain.applications import ApplicationRegistry
from agentask.infrastructure.approved_actions.file import load_action_set
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.artifacts.local_file import LocalArtifactIndex, LocalObjectStore
from agentask.infrastructure.artifacts.mongo_index import MongoArtifactIndex
from agentask.infrastructure.artifacts.s3 import S3ObjectStore
from agentask.infrastructure.browser.evidence import capture_masked
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.identity.dev import DevIdentity
from agentask.infrastructure.identity.local_admin import LocalAdminIdentity
from agentask.infrastructure.identity.unconfigured import UnconfiguredIdentity
from agentask.infrastructure.llm.httpx_llm import HttpxLLM
from agentask.infrastructure.llm.unavailable import UnavailableLLM
from agentask.infrastructure.mongo.catalog_store import MongoCatalogStore
from agentask.infrastructure.runs.local_file import LocalFileRunRepository


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    identity: IdentityPort
    llm: LLMPort
    browser_factory: BrowserContextFactory
    sessions: BrowserSessionService
    observation: ObservationService
    runs: RunService
    designer: DesignerService
    catalog_store: MongoCatalogStore | None
    publishing: PublishService | None
    assistant: AssistantService
    impact: ImpactService
    applications: ApplicationRegistry
    artifacts: ArtifactService
    admin_auth: LocalAdminIdentity | None = None


def object_store_for(settings: Settings) -> ObjectStore:
    if settings.artifact_backend is ArtifactBackend.S3:
        assert settings.s3_endpoint_url and settings.s3_bucket and settings.s3_region  # Settings doğruladı
        assert settings.s3_access_key_id and settings.s3_secret_access_key
        return S3ObjectStore(
            endpoint=str(settings.s3_endpoint_url),
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            access_key=settings.s3_access_key_id.get_secret_value(),
            secret_key=settings.s3_secret_access_key.get_secret_value(),
            prefix=settings.s3_prefix,
            addressing=settings.s3_addressing_style.value,
            ca_bundle=settings.s3_ca_bundle,
            timeout_s=settings.s3_timeout_ms / 1000,
        )
    return LocalObjectStore(settings.artifact_directory)


def _evidence_recorder(artifacts: ArtifactService) -> Any:
    async def record(run: Any, handle: Any) -> str | None:
        page = getattr(handle, "page", None)
        if page is None:
            return None
        capture = await capture_masked(page)
        if not capture.verified:
            return None  # maskelemesi doğrulanmayan görüntü saklanmaz
        ref = await artifacts.store(
            run.owner_id, "evidence", "image/png", capture.png, run_id=run.run_id, masking_verified=True
        )
        return ref.artifact_id

    return record


def _artifact_index(settings: Settings) -> ArtifactIndex:
    if settings.artifact_index_backend is ArtifactIndexBackend.MONGO:
        return MongoArtifactIndex(
            settings.mongo_uri.get_secret_value(),
            settings.mongo_database,
            settings.mongo_server_selection_timeout_ms,
            settings.mongo_tls_ca_file,
        )
    return LocalArtifactIndex(settings.artifact_directory)


def build_container(settings: Settings) -> Container:
    # Browser süreci burada başlatılmaz; ilk oturum açıldığında başlar.
    factory = PlaywrightContextFactory(settings)
    sessions = BrowserSessionService(
        factory,
        SessionLimits(
            max_sessions=settings.browser_max_sessions,
            max_per_user=settings.browser_max_sessions_per_user,
            idle_seconds=settings.browser_session_idle_seconds,
            max_verification_per_user=settings.browser_max_verification_sessions_per_user,
        ),
    )
    observation = ObservationService(sessions, picker_wait_max_ms=settings.picker_wait_max_ms)
    runs = _runs(settings, sessions)
    drafts = LocalFileDraftRepository(settings.draft_directory)
    store = None
    if settings.catalog_backend is CatalogBackend.MONGO:
        store = MongoCatalogStore(
            settings.mongo_uri.get_secret_value(),
            settings.mongo_database,
            settings.mongo_server_selection_timeout_ms,
            settings.mongo_tls_ca_file,
        )
    publishing = PublishService(store, drafts, runs.actions, settings.catalog_environment) if store else None
    llm = _llm(settings)
    applications = ApplicationRegistry(settings.automation_applications_json)
    assistant = AssistantService(
        publishing,
        runs,
        runs.actions,
        llm,
        settings.llm_max_input_tokens,
        settings.llm_max_output_tokens,
        settings.llm_max_calls_per_run,
        settings.catalog_application_id,
        composition_enabled=settings.composition_enabled,
        composition_max_depth=settings.composition_max_depth,
        composition_max_items=settings.composition_max_items,
        max_steps=settings.run_max_steps,
        applications=applications,
    )
    artifacts = ArtifactService(
        object_store_for(settings),
        _artifact_index(settings),
        settings.artifact_max_bytes,
        settings.evidence_retention_days,
    )
    runs.attach_file_reader(artifacts.read_upload)
    if settings.evidence_screenshots_enabled:
        runs.evidence = _evidence_recorder(artifacts)
    identity = _identity(settings)
    return Container(
        settings=settings,
        identity=identity,
        admin_auth=identity if isinstance(identity, LocalAdminIdentity) else None,
        llm=llm,
        browser_factory=factory,
        sessions=sessions,
        observation=observation,
        runs=runs,
        designer=DesignerService(
            drafts,
            sessions,
            observation,
            runs,
            runs.actions,
            run_timeout_s=settings.run_max_duration_seconds,
            publishing=publishing,
            fresh_login_timeout_s=settings.fresh_test_login_timeout_seconds,
        ),
        catalog_store=store,
        publishing=publishing,
        assistant=assistant,
        impact=ImpactService(publishing, observation, drafts, settings.catalog_application_id),
        applications=applications,
        # Dosya/kanıt (ADR 0016/0018): ARTIFACT_BACKEND=local|s3, ARTIFACT_INDEX_BACKEND=local|mongo.
        # Kurum S3 bağlantı kabulü BLOCKED; adaptör sahte S3 sözleşme testleriyle doğrulandı.
        artifacts=artifacts,
    )


def _runs(settings: Settings, sessions: BrowserSessionService) -> RunService:
    actions = ActionSet()
    if settings.approved_action_set is ApprovedActionSet.LAB:
        actions = LAB_ACTION_SET
    elif settings.approved_action_set is ApprovedActionSet.FILE:
        assert settings.approved_actions_file is not None  # Settings doğruladı
        actions = load_action_set(
            settings.approved_actions_file,
            frozenset(a.id for a in settings.automation_applications_json),
        )
    repository = LocalFileRunRepository(settings.run_directory)
    executor = Executor(
        repository, actions, AdapterRegistry.default(), ExecutorConfig.from_settings(settings)
    )
    return RunService(
        repository,
        sessions,
        executor,
        actions,
        max_steps=settings.run_max_steps,
        allow_composition=settings.composition_enabled,
    )


def _identity(settings: Settings) -> IdentityPort:
    if settings.auth_mode is AuthMode.DEV:
        # Settings, dev modunu development + açık izin + loopback dışında zaten reddeder.
        return DevIdentity()
    if settings.auth_mode is AuthMode.LOCAL_ADMIN:
        assert settings.admin_username and settings.admin_password_hash  # Settings doğruladı
        return LocalAdminIdentity(
            settings.admin_username,
            settings.admin_password_hash.get_secret_value(),
            settings.admin_session_ttl_seconds,
            settings.admin_login_max_attempts,
            settings.admin_login_lockout_seconds,
        )
    return UnconfiguredIdentity()


def _llm(settings: Settings) -> LLMPort:
    if not settings.llm_enabled:
        return UnavailableLLM("disabled")
    return HttpxLLM(settings)
