from threading import Thread

import pytest

from app.container import ServiceContainer


def test_register_get_and_has():
    container = ServiceContainer()
    container.register("marker", "value")

    assert container.has("marker")
    assert container.get("marker") == "value"
    assert "marker" in container.list_services()


def test_get_missing_service_raises_keyerror():
    container = ServiceContainer()

    with pytest.raises(KeyError):
        container.get("missing")


def test_register_duplicate_raises_valueerror():
    container = ServiceContainer()
    container.register("marker", "value")

    with pytest.raises(ValueError):
        container.register("marker", "other")


def test_unregister_is_idempotent():
    container = ServiceContainer()
    container.register("marker", "value")

    container.unregister("marker")
    container.unregister("marker")  # must not raise

    assert not container.has("marker")


def test_concurrent_register_and_get_does_not_crash():
    """Not a proof of correctness, but real threads hammering
    register()/get()/list_services() concurrently used to be able to
    raise 'dict changed size during iteration' or similar before
    locking was added."""
    container = ServiceContainer()
    errors = []

    def registrar_thread(offset):
        for i in range(100):
            try:
                container.register(f"svc-{offset}-{i}", i)
            except Exception as exc:
                errors.append(exc)

    def reader_thread():
        for _ in range(200):
            try:
                container.list_services()
            except Exception as exc:
                errors.append(exc)

    threads = [Thread(target=registrar_thread, args=(n,)) for n in range(4)] + [
        Thread(target=reader_thread) for _ in range(4)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert errors == []
