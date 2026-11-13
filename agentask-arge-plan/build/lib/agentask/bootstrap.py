"""Composition root: Settings + adapterler burada birleştirilir. Başka modül adapter seçmez."""

from __future__ import annotations

from dataclasses import dataclass

from agentask.application.controls import AdapterRegistry
from agentask.application.ports.browser import BrowserContextFactory
from agentask.application.ports.identity import IdentityPort
from agentask.application.ports.llm import LLMPort
from agentask.application.services.assistant import AssistantService
from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits
from agentask.application.services.designer import DesignerService
from agentask.application.services.executor import Executor, ExecutorConfig
from agentask.application.services.impact import ImpactService
from agentask.application.services.observation import ObservationService
from agentask.application.services.publishing import PublishService
from agentask.application.services.runs import RunService
from agentask.config.settings import ApprovedActionSet, AuthMode, CatalogBackend, Settings
from agentask.domain.actions import ActionSet
from agentask.infrastructure.approved_actions.lab import LAB_ACTION_SET
from agentask.infrastructure.browser.playwright_factory import PlaywrightContextFactory
from agentask.infrastructure.drafts.local_file import LocalFileDraftRepository
from agentask.infrastructure.identity.dev import DevIdentity
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


def build_container(settings: Settings) -> Container:
    # Browser süreci burada başlatılmaz; ilk oturum açıldığında başlar.
    factory = PlaywrightContextFactory(settings)
    sessions = BrowserSessionService(
        factory,
        SessionLimits(
            max_sessions=settings.browser_max_sessions,
            max_per_user=settings.browser_max_sessions_per_user,
            idle_seconds=settings.browser_session_idle_seconds,
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
    )
    return Container(
        settings=settings,
        identity=_identity(settings),
        llm=llm,
        browser_factory=factory,
        sessions=sessions,
        observation=observation,
        runs=runs,
        designer=DesignerService(
            drafts, sessions, observation, runs, runs.actions, run_timeout_s=settings.run_max_duration_seconds
        ),
        catalog_store=store,
        publishing=publishing,
        assistant=assistant,
        impact=ImpactService(publishing, observation, drafts, settings.catalog_application_id),
    )


def _runs(settings: Settings, sessions: BrowserSessionService) -> RunService:
    actions = LAB_ACTION_SET if settings.approved_action_set is ApprovedActionSet.LAB else ActionSet()
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
    return UnconfiguredIdentity()


def _llm(settings: Settings) -> LLMPort:
    if not settings.llm_enabled:
        return UnavailableLLM("disabled")
    return HttpxLLM(settings)
