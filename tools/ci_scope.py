#!/usr/bin/env python3
"""Choose full firmware validation only when build inputs or driver tests change."""
import os
import subprocess
import sys


def needs_firmware(paths):
    exact = {"build.sh", "board-support.patch", "release-line.json",
             "tools/package_firmware.py", "tools/release_line.py"}
    return any(path in exact or path.startswith("target/") or
               path.startswith(("tools/check_", "tools/test_")) for path in paths)


def main():
    before = os.environ.get("BASE_COMMIT") or os.environ.get("BEFORE_COMMIT")
    event = os.environ.get("EVENT_NAME", "")
    full = event not in ("push", "pull_request") or not before or set(before) == {"0"}
    if not full:
        paths = subprocess.check_output(["git", "diff", "--name-only", before, "HEAD"], text=True).splitlines()
        full = needs_firmware(paths)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write("build=" + str(full).lower() + "\n")


if __name__ == "__main__":
    main()
