"""Capture non-secret CI image-build output with a bounded console tail.

Use only with reviewed build/check commands: do not wrap commands that print
credentials, application environments or private run data. The complete log
is an artifact; exit status and timeout are never turned into success.
"""
from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path
import re
import subprocess
import sys


def capture(name: str, command: list[str], directory: Path, timeout: int = 900) -> int:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", name) or not command or timeout < 1:
        raise ValueError("A safe report name, command and positive timeout are required")
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / (name + ".log")
    receipt = {"name": name, "status": "failed", "exit_code": 127, "timeout": False}
    with log.open("wb") as output:
        try:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
            receipt["exit_code"] = result.returncode if result.returncode >= 0 else 128 - result.returncode
        except subprocess.TimeoutExpired:
            receipt.update(exit_code=124, timeout=True)
        except OSError:
            output.write(b"CI command could not be started\n")
    if receipt["exit_code"] == 0:
        receipt["status"] = "passed"
    (directory / (name + ".json")).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    with log.open(encoding="utf-8", errors="replace") as stream:
        tail = "".join(deque(stream, maxlen=60))
    # Avoid a malicious compiler line being interpreted as an Actions command.
    print(tail.replace("::", ": :"), end="")
    print(f"{name}: {receipt['status']} (exit {receipt['exit_code']}); full log: {log}")
    return int(receipt["exit_code"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--directory", type=Path, default=Path("image-build-reports"))
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    return capture(args.name, command, args.directory, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
