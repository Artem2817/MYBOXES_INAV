#!/usr/bin/env python3
"""Read and enforce the upstream pin for this MYBOX release line."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def load_line():
    line = json.loads((ROOT / "release-line.json").read_text(encoding="utf-8"))
    major = line["inav_major"]
    if type(major) is not int or line["branch"] != f"inav-{major}":
        raise ValueError("Release line branch/major mismatch")
    if not re.fullmatch(rf"{major}\.[0-9]+\.[0-9]+(?:-rc[1-9][0-9]*)?", line["upstream_tag"]):
        raise ValueError("Release line upstream tag/major mismatch")
    if not re.fullmatch(r"[a-f0-9]{40}", line["upstream_commit"]):
        raise ValueError("Invalid pinned upstream commit")
    return line

def check_ref(line, ref):
    if ref != line["branch"]:
        raise ValueError(f"Use branch {line['branch']} for INAV {line['inav_major']}; received {ref}")

def check_checkout(line, checkout):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(checkout), *args], text=True).strip()
    commit = git("rev-parse", "HEAD")
    message = f"Use INAV {line['upstream_tag']} at {line['upstream_commit']}"
    if commit != line["upstream_commit"]:
        raise ValueError(message)
    tag_commit = git("rev-parse", f"refs/tags/{line['upstream_tag']}^{{commit}}")
    if tag_commit != commit:
        raise ValueError(message)
    return commit

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", help="CI source branch, or pull request base branch")
    parser.add_argument("--checkout", type=Path)
    parser.add_argument("--build-config", action="store_true")
    args = parser.parse_args()
    try:
        line = load_line()
        if args.ref:
            check_ref(line, args.ref)
        if args.checkout:
            check_checkout(line, args.checkout)
        if args.build_config:
            print(line["upstream_tag"] + "\t" + line["upstream_commit"])
        else:
            print(f"{line['branch']}: INAV {line['upstream_tag']} / {line['upstream_commit']}")
    except (ValueError, KeyError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))

if __name__ == "__main__":
    main()
