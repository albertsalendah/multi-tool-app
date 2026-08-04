from threading import Thread

from app.events import EventBus


def test_a_raising_listener_does_not_stop_other_listeners():
    events = EventBus()
    seen = []

    def bad_listener(**_):
        raise ValueError("boom")

    def good_listener(value):
        seen.append(value)

    events.subscribe("thing", bad_listener)
    events.subscribe("thing", good_listener)

    # Must not raise - one bad subscriber shouldn't propagate back into
    # whatever code path emitted the event.
    events.emit("thing", value=42)

    assert seen == [42]


def test_a_raising_listener_does_not_prevent_earlier_ones_from_finishing():
    events = EventBus()
    seen = []

    def good_listener(value):
        seen.append(value)

    def bad_listener(**_):
        raise ValueError("boom")

    events.subscribe("thing", good_listener)
    events.subscribe("thing", bad_listener)

    events.emit("thing", value=1)

    assert seen == [1]


def test_unsubscribe_stops_further_calls():
    events = EventBus()
    seen = []

    def listener(value):
        seen.append(value)

    events.subscribe("thing", listener)
    events.emit("thing", value=1)
    events.unsubscribe("thing", listener)
    events.emit("thing", value=2)

    assert seen == [1]


def test_concurrent_subscribe_and_emit_does_not_crash():
    """Not a proof of correctness, but real threads hammering
    subscribe()/emit() concurrently used to be able to raise
    'dict changed size during iteration' or similar before locking."""
    events = EventBus()
    errors = []

    def subscriber_thread():
        for _ in range(200):
            events.subscribe("thing", lambda **_: None)

    def emitter_thread():
        for _ in range(200):
            try:
                events.emit("thing", value=1)
            except Exception as exc:
                errors.append(exc)

    threads = [Thread(target=subscriber_thread) for _ in range(4)] + [
        Thread(target=emitter_thread) for _ in range(4)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert errors == []
