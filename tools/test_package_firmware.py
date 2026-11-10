"""Exercise rejection of corrupt and mismatched release HEX files."""

import unittest

from package_firmware import verify_hex


def record(kind, offset, data=b""):
    fields = bytes([len(data)]) + offset.to_bytes(2, "big") + bytes([kind]) + data
    return b":" + (fields + bytes([-sum(fields) % 256])).hex().encode("ascii")


class FirmwareHexTests(unittest.TestCase):
    vector = bytes.fromhex("0000012011000008") + b"MBM1\0"
    valid = [record(4, 0, b"\x08\x00"), record(0, 0, vector), record(0, 16, b"\0\0"), record(1, 0)]

    def test_accepts_valid_image(self):
        self.assertEqual(verify_hex(b"\n".join(self.valid), "MBM1"), len(self.vector) + 2)

    def test_rejects_bad_checksum_and_wrong_board(self):
        corrupt = self.valid.copy()
        corrupt[1] = corrupt[1][:-2] + b"00"
        with self.assertRaisesRegex(ValueError, "checksum"):
            verify_hex(b"\n".join(corrupt), "MBM1")
        with self.assertRaisesRegex(ValueError, "identifier"):
            verify_hex(b"\n".join(self.valid), "MBM2")

    def test_rejects_overlap_and_reserved_flash(self):
        for extra in ([record(0, 2, b"\0")], [record(4, 0, b"\x08\x02"), record(0, 0, b"\0")]):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                verify_hex(b"\n".join(self.valid[:-1] + extra + self.valid[-1:]), "MBM1")

    def test_requires_eof(self):
        with self.assertRaisesRegex(ValueError, "EOF"):
            verify_hex(b"\n".join(self.valid[:-1]), "MBM1")
