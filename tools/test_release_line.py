"""Prevent branch/upstream mixups before a release is packaged."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import release_line

class ReleaseLineTests(unittest.TestCase):
    def test_expected_branch_and_wrong_major(self):
        line = release_line.load_line()
        release_line.check_ref(line, line["branch"])
        for ref in ("main", "inav-9" if line["inav_major"] == 10 else "inav-10"):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, "Use branch"):
                release_line.check_ref(line, ref)

    def test_exact_pin_required_even_with_matching_version_tag(self):
        line = release_line.load_line()
        commit = line["upstream_commit"]
        with patch("release_line.subprocess.check_output", side_effect=[commit, commit]):
            self.assertEqual(release_line.check_checkout(line, "/unused"), commit)
        for actual, tag_commit in (("0"*40, commit), (commit, "0"*40)):
            with patch("release_line.subprocess.check_output", side_effect=[actual, tag_commit]):
                with self.assertRaisesRegex(ValueError, "Use INAV"):
                    release_line.check_checkout(line, "/unused")

    def test_mixed_major_lock_rejected(self):
        line = release_line.load_line()
        for field, value in (("branch", "inav-11"), ("upstream_tag", "11.0.0")):
            invalid = copy.deepcopy(line)
            invalid[field] = value
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "release-line.json").write_text(json.dumps(invalid))
                with patch.object(release_line, "ROOT", root):
                    with self.assertRaisesRegex(ValueError, "mismatch"):
                        release_line.load_line()

    def test_package_rejects_other_upstream_before_creating_output(self):
        import package_firmware
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "dist"
            with patch("package_firmware.check_checkout", side_effect=ValueError("Use INAV pinned version")):
                with patch("sys.argv", ["package_firmware.py", "--checkout", temp, "--output", str(output)]):
                    with self.assertRaisesRegex(ValueError, "Use INAV"):
                        package_firmware.main()
            self.assertFalse(output.exists())
