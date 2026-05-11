#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import signal
import sys

import pexpect


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a remote shell command over SSH with password prompts handled by pexpect."
    )
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password-env", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument(
        "--strict-host-key-checking",
        default="no",
        choices=("no", "accept-new", "yes"),
    )
    parser.add_argument("--connect-timeout", type=int, default=10)
    parser.add_argument("--log-output", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    password = os.getenv(args.password_env, "")
    if not password:
        raise SystemExit(f"Environment variable {args.password_env} is required")

    ssh_command = [
        "ssh",
        "-p",
        str(args.port),
        "-o",
        f"StrictHostKeyChecking={args.strict_host_key_checking}",
        "-o",
        f"ConnectTimeout={args.connect_timeout}",
        f"{args.user}@{args.host}",
        args.command,
    ]

    child = pexpect.spawn(
        ssh_command[0],
        ssh_command[1:],
        encoding="utf-8",
        timeout=max(args.connect_timeout, 10),
    )
    if args.log_output:
        child.logfile_read = sys.stdout

    interrupted = {"value": False}

    def _handle_signal(signum: int, _frame: object) -> None:
        interrupted["value"] = True
        try:
            child.kill(signal.SIGINT)
        except Exception:
            pass
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    while True:
        try:
            index = child.expect(
                [
                    r"(?i)are you sure you want to continue connecting",
                    r"(?i)password:",
                    pexpect.EOF,
                    pexpect.TIMEOUT,
                ]
            )
        except pexpect.exceptions.ExceptionPexpect as exc:
            raise SystemExit(f"ssh spawn failed: {exc}") from exc

        if index == 0:
            child.sendline("yes")
            continue
        if index == 1:
            child.sendline(password)
            continue
        if index == 2:
            break
        if index == 3:
            raise SystemExit(
                "ssh command timed out while waiting for host key, password, or process exit: "
                + " ".join(shlex.quote(part) for part in ssh_command)
            )

    if interrupted["value"]:
        return 130

    child.close()
    if child.exitstatus is not None:
        return int(child.exitstatus)
    if child.signalstatus is not None:
        return 128 + int(child.signalstatus)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
