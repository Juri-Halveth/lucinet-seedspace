"""Keep the withdrawn character, its motion clips and its dedicated tools out of releases."""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
RETIRED_BLOBS = {
    b"637d8db01dbc9fbf78b59f2f91463e23dd38a9d3",  # Body
    b"49ab49b9abac1c1195c6b2560102b525f82634ec",  # Motion clip collection
    b"fdb7c2e10b51603eb9401d07c92fd1708e6d3892",  # Character builder
    b"0b072d0d546a9bd308b4622c39e414eb14da4d49",  # Rig adapter
    b"bf21c1dc80776d860c88fce07b5d6367a8aa3c32",  # Motion controller
}


class CharacterRetirementTest(unittest.TestCase):
    def test_retired_lab_is_absent(self):
        self.assertFalse((ROOT / "nova/labs/accepted-motion").exists())
        self.assertFalse((ROOT / ".github/workflows/accepted-motion.yml").exists())

    @unittest.skipUnless((ROOT / ".git").exists() and shutil.which("git"), "requires a Git checkout")
    def test_index_has_no_renamed_copy(self):
        index = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=ROOT)
        for record in index.split(b"\0"):
            if record:
                mode_hash_stage, path = record.split(b"\t", 1)
                self.assertNotIn(mode_hash_stage.split()[1], RETIRED_BLOBS, path)
