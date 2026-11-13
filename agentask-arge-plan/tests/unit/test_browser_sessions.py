"""Oturum kuralları: sahiplik, tek işlem kilidi, limitler, boşta kalma ve kapanış (T12, T13)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from agentask.application.errors import ServiceShuttingDown, SessionBusy, SessionLimitReached, SessionNotFound
from agentask.application.services.browser_sessions import BrowserSessionService, SessionLimits


class FakeHandle:
    def __init__(self, owner_id: str) -> None:
        self.owner_id = owner_id
        self.is_closed = False
        self.current_url = "about:blank"

    async def navigate(self, url: str) -> None:
        self.current_url = url

    async def close(self) -> None:
        self.is_closed = True


class FakeFactory:
    def __init__(self, delay: float = 0.0, fail: bool = False) -> None:
        self.handles: list[FakeHandle] = []
        self.delay = delay
        self.fail = fail
        self.shut_down = False

    async def create_context(self, owner_id: str) -> FakeHandle:
        await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("browser başlatılamadı")
        handle = FakeHandle(owner_id)
        self.handles.append(handle)
        return handle

    async def shutdown(self) -> None:
        self.shut_down = True


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def make_service(
    factory: FakeFactory | None = None,
    *,
    total: int = 4,
    per_user: int = 2,
    idle: int = 60,
    clock: Clock | None = None,
) -> tuple[BrowserSessionService, FakeFactory]:
    factory = factory or FakeFactory()
    service = BrowserSessionService(
        factory,
        SessionLimits(max_sessions=total, max_per_user=per_user, idle_seconds=idle),
        clock=clock or Clock(),
    )
    return service, factory


async def test_open_and_close_releases_context() -> None:
    service, factory = make_service()
    view = await service.open("ayse")
    assert view.owner_id == "ayse" and view.busy_operation is None
    assert [v.session_id for v in service.list("ayse")] == [view.session_id]
    await service.close("ayse", view.session_id)
    assert factory.handles[0].is_closed
    assert service.list("ayse") == []


async def test_session_ids_are_unguessable_and_unique() -> None:
    service, _ = make_service(per_user=2)
    a, b = await service.open("ayse"), await service.open("ayse")
    assert a.session_id != b.session_id and len(a.session_id) >= 20


async def test_other_user_gets_not_found() -> None:
    service, factory = make_service()
    view = await service.open("ayse")
    with pytest.raises(SessionNotFound):
        await service.close("mehmet", view.session_id)
    with pytest.raises(SessionNotFound):
        async with service.operation("mehmet", view.session_id, "observe"):
            pass
    assert service.list("mehmet") == []
    assert not factory.handles[0].is_closed


async def test_unknown_session_is_not_found() -> None:
    service, _ = make_service()
    with pytest.raises(SessionNotFound):
        async with service.operation("ayse", "nope", "observe"):
            pass


async def test_second_operation_is_rejected_while_first_runs() -> None:
    service, _ = make_service()
    view = await service.open("ayse")
    entered, release = asyncio.Event(), asyncio.Event()

    async def first() -> None:
        async with service.operation("ayse", view.session_id, "trial"):
            entered.set()
            await release.wait()

    task = asyncio.create_task(first())
    await entered.wait()
    assert service.list("ayse")[0].busy_operation == "trial"
    with pytest.raises(SessionBusy):
        async with service.operation("ayse", view.session_id, "observe"):
            pass
    release.set()
    await task
    async with service.operation("ayse", view.session_id, "observe") as handle:
        assert handle.current_url == "about:blank"


async def test_operation_released_after_exception() -> None:
    service, _ = make_service()
    view = await service.open("ayse")
    with pytest.raises(ValueError):
        async with service.operation("ayse", view.session_id, "trial"):
            raise ValueError("boom")
    async with service.operation("ayse", view.session_id, "observe"):
        pass


async def test_close_while_busy_is_rejected() -> None:
    service, factory = make_service()
    view = await service.open("ayse")
    async with service.operation("ayse", view.session_id, "trial"):
        with pytest.raises(SessionBusy):
            await service.close("ayse", view.session_id)
    assert not factory.handles[0].is_closed


async def test_per_user_and_total_limits() -> None:
    service, _ = make_service(total=3, per_user=2)
    await service.open("ayse")
    await service.open("ayse")
    with pytest.raises(SessionLimitReached):
        await service.open("ayse")
    await service.open("mehmet")
    with pytest.raises(SessionLimitReached):
        await service.open("zeynep")


async def test_concurrent_open_respects_limit() -> None:
    service, factory = make_service(FakeFactory(delay=0.05), total=4, per_user=1)
    results = await asyncio.gather(*(service.open("ayse") for _ in range(3)), return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert sum(isinstance(r, SessionLimitReached) for r in results) == 2
    assert len(factory.handles) == 1


async def test_factory_failure_releases_reservation() -> None:
    factory = FakeFactory(fail=True)
    service, _ = make_service(factory, per_user=1)
    with pytest.raises(RuntimeError):
        await service.open("ayse")
    factory.fail = False
    assert (await service.open("ayse")).owner_id == "ayse"


async def test_reap_idle_closes_expired() -> None:
    clock = Clock()
    service, factory = make_service(idle=60, clock=clock)
    old = await service.open("ayse")
    clock.now += timedelta(seconds=30)
    fresh = await service.open("mehmet")
    clock.now += timedelta(seconds=31)
    assert await service.reap_idle() == 1
    assert service.list("ayse") == []
    assert [v.session_id for v in service.list("mehmet")] == [fresh.session_id]
    assert factory.handles[0].is_closed and not factory.handles[1].is_closed
    with pytest.raises(SessionNotFound):
        async with service.operation("ayse", old.session_id, "observe"):
            pass


async def test_operation_refreshes_last_used() -> None:
    clock = Clock()
    service, _ = make_service(idle=60, clock=clock)
    view = await service.open("ayse")
    clock.now += timedelta(seconds=50)
    async with service.operation("ayse", view.session_id, "observe"):
        pass
    clock.now += timedelta(seconds=50)
    assert await service.reap_idle() == 0


async def test_reap_skips_busy_sessions() -> None:
    clock = Clock()
    service, factory = make_service(idle=60, clock=clock)
    view = await service.open("ayse")
    async with service.operation("ayse", view.session_id, "trial"):
        clock.now += timedelta(seconds=600)
        assert await service.reap_idle() == 0
    assert not factory.handles[0].is_closed


async def test_shutdown_closes_all_and_rejects_new() -> None:
    service, factory = make_service()
    await service.open("ayse")
    await service.open("mehmet")
    await service.shutdown()
    assert all(h.is_closed for h in factory.handles)
    assert factory.shut_down
    with pytest.raises(ServiceShuttingDown):
        await service.open("ayse")


async def test_shutdown_closes_even_busy_sessions() -> None:
    service, factory = make_service()
    view = await service.open("ayse")
    async with service.operation("ayse", view.session_id, "trial"):
        await service.shutdown()
    assert factory.handles[0].is_closed and factory.shut_down


# ---- R2: geçici doğrulama oturumu ------------------------------------------------


def make_verifying(
    total: int = 4, per_user: int = 1, verification: int = 1
) -> tuple[BrowserSessionService, FakeFactory]:
    factory = FakeFactory()
    service = BrowserSessionService(
        factory,
        SessionLimits(
            max_sessions=total, max_per_user=per_user, idle_seconds=60, max_verification_per_user=verification
        ),
        clock=Clock(),
    )
    return service, factory


async def test_verification_session_does_not_consume_interactive_quota() -> None:
    service, factory = make_verifying(per_user=1)
    main = await service.open("ayse")
    async with service.verification_session("ayse") as temp:
        assert temp.purpose == "verification" and temp.session_id != main.session_id
        assert {v.purpose for v in service.list("ayse")} == {"interactive", "verification"}
    assert [v.session_id for v in service.list("ayse")] == [main.session_id]
    assert not factory.handles[0].is_closed and factory.handles[1].is_closed


async def test_verification_quota_and_total_capacity_respected_without_closing_others() -> None:
    service, factory = make_verifying(total=2, per_user=1, verification=1)
    await service.open("ayse")
    await service.open("mehmet")
    with pytest.raises(SessionLimitReached):
        async with service.verification_session("ayse"):
            pass
    assert len(service.list("ayse")) == 1 and len(service.list("mehmet")) == 1
    assert not any(h.is_closed for h in factory.handles)
    service2, _ = make_verifying(total=4, verification=1)
    async with service2.verification_session("ayse"):
        with pytest.raises(SessionLimitReached):
            async with service2.verification_session("ayse"):
                pass


async def test_verification_session_closed_on_error_and_even_when_busy() -> None:
    service, factory = make_verifying()
    with pytest.raises(RuntimeError):
        async with service.verification_session("ayse") as temp:
            raise RuntimeError("test başarısız")
    assert service.list("ayse") == [] and factory.handles[0].is_closed
    entered = asyncio.Event()

    async def hold(sid: str) -> None:
        # İç doğrulama akışı (yeni oturum testi run'ı) gibi: geçici oturum yalnız açık bayrakla
        # kullanılabilir.
        async with service.operation("ayse", sid, "run", allow_verification=True):
            entered.set()
            await asyncio.sleep(10)

    async with service.verification_session("ayse") as temp:
        task = asyncio.create_task(hold(temp.session_id))
        await entered.wait()
    assert service.list("ayse") == [] and factory.handles[1].is_closed  # işlemde bile temizlenir
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def test_interactive_close_still_rejects_busy() -> None:
    service, _ = make_verifying()
    main = await service.open("ayse")
    async with service.operation("ayse", main.session_id, "run"):
        with pytest.raises(SessionBusy):
            await service.close("ayse", main.session_id)


# ---- R2B: doğrulama oturumu normal oturum yerine kullanılamaz; durum ve kota görünümü ----


async def test_verification_session_not_usable_as_interactive() -> None:
    service, _ = make_verifying()
    async with service.verification_session("ayse") as temp:
        with pytest.raises(SessionNotFound):
            async with service.operation("ayse", temp.session_id, "observe"):
                pass
        with pytest.raises(SessionNotFound):
            service.peek("ayse", temp.session_id)
        with pytest.raises(SessionNotFound):
            await service.close("ayse", temp.session_id)
        with pytest.raises(SessionNotFound):
            service.status("ayse", temp.session_id)
        async with service.operation("ayse", temp.session_id, "navigate", allow_verification=True):
            pass
    with pytest.raises(ValueError):
        await service.open("ayse", purpose="admin")


async def test_status_and_overview_are_owner_scoped() -> None:
    service, _ = make_verifying(total=3, per_user=1)
    mine = await service.open("ayse")
    await service.open("mehmet")
    view = service.status("ayse", mine.session_id)
    assert view.alive and view.current_url == "about:blank" and view.purpose == "interactive"
    with pytest.raises(SessionNotFound):
        service.status("mehmet", mine.session_id)
    overview = service.overview("ayse")
    assert [s.session_id for s in overview["sessions"]] == [mine.session_id]
    assert overview["quota"] == {
        "interactive_limit": 1,
        "interactive_used": 1,
        "total_capacity": 3,
        "total_used": 2,
        "verification_in_use": 0,
    }
    with pytest.raises(SessionLimitReached) as exc:
        await service.open("ayse")
    assert exc.value.details == {"interactive_limit": 1, "interactive_used": 1}
