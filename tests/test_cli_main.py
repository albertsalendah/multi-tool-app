import io
import json
from contextlib import redirect_stderr, redirect_stdout

from cli.main import (
    _cmd_health,
    _cmd_jobs_create,
    _cmd_jobs_get,
    _cmd_jobs_cancel,
    _cmd_schedules_create,
    _cmd_schedules_get,
    _cmd_schedules_cancel,
    _cmd_tools_list,
    build_parser,
    main,
)


class FakeClient:
    """Records every call and returns canned responses - lets us test
    argument parsing and command dispatch without any real or
    in-process HTTP (see tests/test_cli_client.py for that layer)."""

    def __init__(self):
        self.calls = []
        self.health_response = {"status": "ok", "initialized": True}
        self.tools_response = [{"name": "echo", "version": "1.0.0", "description": ""}]
        self.create_job_response = {"job_id": "job-1"}
        self.get_job_response = {
            "job_id": "job-1",
            "status": "completed",
            "progress": 100,
            "result": 42,
            "error": None,
        }
        self.cancel_job_response = {"job_id": "job-1", "cancelled": True}
        self.create_schedule_response = {"schedule_id": "sched-1"}
        self.get_schedule_response = {
            "schedule_id": "sched-1",
            "status": "scheduled",
            "run_at": "2026-01-01T00:00:00+00:00",
            "job_id": None,
        }
        self.cancel_schedule_response = {"schedule_id": "sched-1", "cancelled": True}

    def health(self):
        self.calls.append(("health",))
        return self.health_response

    def list_tools(self):
        self.calls.append(("list_tools",))
        return self.tools_response

    def create_job(self, tool, params=None):
        self.calls.append(("create_job", tool, params))
        return self.create_job_response

    def get_job(self, job_id):
        self.calls.append(("get_job", job_id))
        return self.get_job_response

    def cancel_job(self, job_id):
        self.calls.append(("cancel_job", job_id))
        return self.cancel_job_response

    def wait_for_job(self, job_id, poll_interval=0.5, timeout=None):
        self.calls.append(("wait_for_job", job_id, poll_interval, timeout))
        return self.get_job_response

    def create_schedule(self, delay_seconds, tool, params=None):
        self.calls.append(("create_schedule", delay_seconds, tool, params))
        return self.create_schedule_response

    def get_schedule(self, schedule_id):
        self.calls.append(("get_schedule", schedule_id))
        return self.get_schedule_response

    def cancel_schedule(self, schedule_id):
        self.calls.append(("cancel_schedule", schedule_id))
        return self.cancel_schedule_response


def _run(func, client, args) -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        func(client, args)
    return json.loads(buf.getvalue())


# --------------------------------------------------------------------------
# Parser structure
# --------------------------------------------------------------------------


def test_parser_builds_expected_command_tree():
    parser = build_parser()

    args = parser.parse_args(["health"])
    assert args.func is _cmd_health

    args = parser.parse_args(["tools", "list"])
    assert args.func is _cmd_tools_list

    args = parser.parse_args(["jobs", "get", "abc"])
    assert args.func is _cmd_jobs_get
    assert args.job_id == "abc"

    args = parser.parse_args(["jobs", "cancel", "abc"])
    assert args.func is _cmd_jobs_cancel
    assert args.job_id == "abc"

    args = parser.parse_args(["jobs", "create", "--tool", "echo"])
    assert args.func is _cmd_jobs_create
    assert args.tool == "echo"
    assert args.param == []
    assert args.wait is False
    assert args.poll_interval == 0.5
    assert args.timeout is None

    args = parser.parse_args(["schedules", "get", "abc"])
    assert args.func is _cmd_schedules_get
    assert args.schedule_id == "abc"

    args = parser.parse_args(["schedules", "cancel", "abc"])
    assert args.func is _cmd_schedules_cancel
    assert args.schedule_id == "abc"

    args = parser.parse_args(
        ["schedules", "create", "--tool", "echo", "--delay-seconds", "5"]
    )
    assert args.func is _cmd_schedules_create
    assert args.tool == "echo"
    assert args.delay_seconds == 5.0
    assert args.param == []


def test_missing_subcommand_is_a_parse_error():
    parser = build_parser()

    try:
        parser.parse_args([])
    except SystemExit:
        pass
    else:
        raise AssertionError("Expected argparse to reject a missing subcommand.")


# --------------------------------------------------------------------------
# Command dispatch
# --------------------------------------------------------------------------


def test_health_command_prints_client_response():
    client = FakeClient()
    args = build_parser().parse_args(["health"])

    output = _run(args.func, client, args)

    assert output == client.health_response
    assert client.calls == [("health",)]


def test_tools_list_command_prints_client_response():
    client = FakeClient()
    args = build_parser().parse_args(["tools", "list"])

    output = _run(args.func, client, args)

    assert output == client.tools_response


def test_jobs_create_parses_typed_and_string_params():
    client = FakeClient()
    args = build_parser().parse_args(
        [
            "jobs", "create", "--tool", "echo",
            "--param", "count=5",
            "--param", "flag=true",
            "--param", "name=hello",
        ]
    )

    _run(args.func, client, args)

    assert client.calls == [
        ("create_job", "echo", {"count": 5, "flag": True, "name": "hello"})
    ]


def test_jobs_create_without_wait_does_not_poll():
    client = FakeClient()
    args = build_parser().parse_args(["jobs", "create", "--tool", "echo"])

    output = _run(args.func, client, args)

    assert client.calls == [("create_job", "echo", {})]
    assert output == client.create_job_response


def test_jobs_create_with_wait_polls_and_prints_final_job():
    client = FakeClient()
    args = build_parser().parse_args(
        ["jobs", "create", "--tool", "echo", "--wait", "--poll-interval", "0.1"]
    )

    output = _run(args.func, client, args)

    assert ("wait_for_job", "job-1", 0.1, None) in client.calls
    assert output == client.get_job_response


def test_jobs_get_and_cancel_dispatch_with_job_id():
    client = FakeClient()

    args = build_parser().parse_args(["jobs", "get", "job-1"])
    output = _run(args.func, client, args)
    assert ("get_job", "job-1") in client.calls
    assert output == client.get_job_response

    args = build_parser().parse_args(["jobs", "cancel", "job-1"])
    output = _run(args.func, client, args)
    assert ("cancel_job", "job-1") in client.calls
    assert output == client.cancel_job_response


def test_malformed_param_raises_value_error():
    client = FakeClient()
    args = build_parser().parse_args(
        ["jobs", "create", "--tool", "echo", "--param", "not-key-value"]
    )

    try:
        args.func(client, args)
    except ValueError as exc:
        assert "KEY=VALUE" in str(exc)
    else:
        raise AssertionError("Expected ValueError for a malformed --param.")


def test_schedules_create_parses_typed_and_string_params():
    client = FakeClient()
    args = build_parser().parse_args(
        [
            "schedules", "create", "--tool", "echo", "--delay-seconds", "5",
            "--param", "count=5",
            "--param", "flag=true",
        ]
    )

    output = _run(args.func, client, args)

    assert client.calls == [
        ("create_schedule", 5.0, "echo", {"count": 5, "flag": True})
    ]
    assert output == client.create_schedule_response


def test_schedules_get_and_cancel_dispatch_with_schedule_id():
    client = FakeClient()

    args = build_parser().parse_args(["schedules", "get", "sched-1"])
    output = _run(args.func, client, args)
    assert ("get_schedule", "sched-1") in client.calls
    assert output == client.get_schedule_response

    args = build_parser().parse_args(["schedules", "cancel", "sched-1"])
    output = _run(args.func, client, args)
    assert ("cancel_schedule", "sched-1") in client.calls
    assert output == client.cancel_schedule_response


# --------------------------------------------------------------------------
# main() end-to-end (real ApiClient, unreachable server - no fake/mocking)
# --------------------------------------------------------------------------


def test_main_reports_unreachable_server_and_returns_nonzero():
    stderr = io.StringIO()

    with redirect_stderr(stderr):
        with redirect_stdout(io.StringIO()):
            exit_code = main(["--base-url", "http://127.0.0.1:1", "health"])

    assert exit_code == 1
    assert "error:" in stderr.getvalue()
