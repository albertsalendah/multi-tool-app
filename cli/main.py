from __future__ import annotations

import argparse
import json
import sys

from cli.client import DEFAULT_BASE_URL, ENV_BASE_URL, ApiClient, ApiError


def _print(data) -> None:
    print(json.dumps(data, indent=2, default=str))


def _parse_params(pairs: list[str]) -> dict:
    """Turn ['count=5', 'flag=true', 'name=hello'] into
    {'count': 5, 'flag': True, 'name': 'hello'} - each value is
    JSON-decoded if possible (so numbers/booleans/null/objects come
    through typed), otherwise kept as a plain string."""

    params = {}

    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--param must be KEY=VALUE, got: '{pair}'")

        key, _, raw_value = pair.partition("=")

        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            value = raw_value

        params[key] = value

    return params


def _cmd_health(client: ApiClient, args: argparse.Namespace) -> None:
    _print(client.health())


def _cmd_tools_list(client: ApiClient, args: argparse.Namespace) -> None:
    _print(client.list_tools())


def _cmd_jobs_create(client: ApiClient, args: argparse.Namespace) -> None:
    params = _parse_params(args.param)
    job = client.create_job(args.tool, params)

    if args.wait:
        job = client.wait_for_job(
            job["job_id"], poll_interval=args.poll_interval, timeout=args.timeout
        )

    _print(job)


def _cmd_jobs_get(client: ApiClient, args: argparse.Namespace) -> None:
    _print(client.get_job(args.job_id))


def _cmd_jobs_cancel(client: ApiClient, args: argparse.Namespace) -> None:
    _print(client.cancel_job(args.job_id))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="multitool",
        description="Command-line client for the Multi Tool App REST API.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=f"API base URL (default: ${ENV_BASE_URL} if set, else {DEFAULT_BASE_URL})",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    health_parser = subparsers.add_parser("health", help="Check API/kernel health.")
    health_parser.set_defaults(func=_cmd_health)

    tools_parser = subparsers.add_parser("tools", help="Inspect registered tools.")
    tools_sub = tools_parser.add_subparsers(dest="tools_command", required=True)

    tools_list_parser = tools_sub.add_parser("list", help="List registered tools.")
    tools_list_parser.set_defaults(func=_cmd_tools_list)

    jobs_parser = subparsers.add_parser(
        "jobs", help="Create, inspect, and cancel background jobs."
    )
    jobs_sub = jobs_parser.add_subparsers(dest="jobs_command", required=True)

    jobs_create_parser = jobs_sub.add_parser(
        "create", help="Run a tool as a background job."
    )
    jobs_create_parser.add_argument(
        "--tool", required=True, help="Tool name - see 'multitool tools list'."
    )
    jobs_create_parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Keyword argument for the tool. Repeatable. Value is "
        "JSON-decoded when possible (so 5, true, null, \"str\" work as "
        "expected), otherwise passed through as a plain string.",
    )
    jobs_create_parser.add_argument(
        "--wait",
        action="store_true",
        help="Poll until the job reaches a terminal status before printing it.",
    )
    jobs_create_parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.5,
        help="Seconds between polls when --wait is set (default: 0.5).",
    )
    jobs_create_parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Give up waiting after this many seconds (default: wait forever).",
    )
    jobs_create_parser.set_defaults(func=_cmd_jobs_create)

    jobs_get_parser = jobs_sub.add_parser(
        "get", help="Get a job's current status/result."
    )
    jobs_get_parser.add_argument("job_id")
    jobs_get_parser.set_defaults(func=_cmd_jobs_get)

    jobs_cancel_parser = jobs_sub.add_parser(
        "cancel", help="Request cancellation of a job."
    )
    jobs_cancel_parser.add_argument("job_id")
    jobs_cancel_parser.set_defaults(func=_cmd_jobs_cancel)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    with ApiClient(base_url=args.base_url) as client:
        try:
            args.func(client, args)
        except ApiError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            # e.g. a malformed --param KEY=VALUE
            print(f"error: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
