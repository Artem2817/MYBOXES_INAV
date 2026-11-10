#!/usr/bin/env python3
"""Validate and package the three MYBOX H743 Mini INAV images."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess


BOARDS = {
    "mini": ("MYBOXH743MINI", "MBM1", "MyboxH743 Mini"),
    "mini-v2": ("MYBOXH743MINIV2", "MBM2", "MyboxH743 Mini v2"),
    "mini-v2-vib": ("MYBOXH743MINIV2VIB_BENCH", "MBVB", "MyboxH743 Mini v2 Vib"),
}
FLASH_START = 0x08000000
FLASH_END = 0x08200000
CONFIG_START = 0x08020000
CONFIG_END = 0x08040000


def verify_hex(content, identifier):
    upper_address = 0
    records = []
    eof = False
    for line in content.splitlines():
        if eof or not line.startswith(b":"):
            raise ValueError("Unexpected record or data after EOF")
        record = bytes.fromhex(line[1:].decode("ascii"))
        if len(record) < 5 or len(record) != record[0] + 5 or sum(record) % 256:
            raise ValueError("Invalid HEX record length or checksum")
        offset = int.from_bytes(record[1:3], "big")
        kind = record[3]
        data = record[4:-1]
        if kind == 0 and data:
            records.append((upper_address + offset, data))
        elif kind == 1 and offset == 0 and not data:
            eof = True
        elif kind == 4 and offset == 0 and len(data) == 2:
            upper_address = int.from_bytes(data, "big") << 16
        elif kind != 5 or offset != 0 or len(data) != 4:
            raise ValueError(f"Unsupported HEX record {kind}")

    records.sort()
    if not eof or not records or records[0][0] != FLASH_START or len(records[0][1]) < 8:
        raise ValueError("Missing EOF or STM32 vector table")

    end = FLASH_START
    chunks = []
    for address, data in records:
        if address < end or address + len(data) > FLASH_END:
            raise ValueError("Overlapping records or data outside STM32H743 flash")
        if address < CONFIG_END and address + len(data) > CONFIG_START:
            raise ValueError("HEX overlaps the INAV configuration sector")
        chunks.append(data)
        end = address + len(data)

    reset = int.from_bytes(records[0][1][4:8], "little")
    if not reset & 1 or not any(address <= (reset & ~1) < address + len(data) for address, data in records):
        raise ValueError("Invalid STM32 reset vector")
    image = b"".join(chunks)
    if identifier.encode("ascii") + b"\0" not in image:
        raise ValueError(f"Board identifier {identifier} missing from image")
    return len(image)


def git_revision(checkout, *args):
    return subprocess.check_output(["git", "-C", str(checkout), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", type=int, default=1)
    args = parser.parse_args()
    if args.revision < 1:
        parser.error("--revision must be positive")
    version = git_revision(args.checkout, "describe", "--tags", "--exact-match", "HEAD")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        parser.error(f"Invalid upstream version: {version}")
    source_commit = git_revision(args.checkout, "rev-parse", "HEAD")
    project_commit = git_revision(Path(__file__).resolve().parents[1], "rev-parse", "HEAD")

    for board, (target, identifier, board_name) in BOARDS.items():
        tag = f"myboxh743-{board}-{version}-r{args.revision}-dev"
        filename = f"inav_{version}_{target}.hex"
        source = args.checkout / "build-mybox" / filename
        content = source.read_bytes()
        try:
            image_size = verify_hex(content, identifier)
        except ValueError as exc:
            raise ValueError(f"{filename}: {exc}") from exc
        checksum = sha256(content).hexdigest()
        output = args.output / board
        output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output / filename)
        manifest = {
            "schema": 1, "firmware": "inav", "release": tag, "channel": "dev",
            "board": board, "board_name": board_name, "target": target,
            "board_identifier": identifier, "version": version, "revision": args.revision,
            "upstream_commit": source_commit, "git_commit": project_commit,
            "bench_only": True, "image_size": image_size,
            "files": [{"name": filename, "size": len(content), "sha256": checksum}],
        }
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (output / "SHA256SUMS.txt").write_text(f"{checksum}  {filename}\n", encoding="utf-8")
        print(f"Verified {tag}: {filename}, {image_size} flash bytes", flush=True)


if __name__ == "__main__":
    main()
