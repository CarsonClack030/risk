import tempfile
import unittest
from pathlib import Path

from scripts.publish_gitee_release import release_assets, wait_for_tag


class _TagSequenceClient:
    def __init__(self, states: list[bool]) -> None:
        self.states = iter(states)
        self.calls = 0

    def tag_exists(self, _tag: str) -> bool:
        self.calls += 1
        return next(self.states)


class GiteeReleasePublisherTests(unittest.TestCase):
    def test_release_assets_only_returns_required_installers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Risk.Studio.dmg").write_bytes(b"dmg")
            (root / "Risk.Studio.exe").write_bytes(b"exe")
            (root / "checksums.txt").write_text("ignored", encoding="utf-8")

            self.assertEqual(
                [path.name for path in release_assets(root)],
                ["Risk.Studio.dmg", "Risk.Studio.exe"],
            )

    def test_release_assets_rejects_an_incomplete_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Risk.Studio.exe").write_bytes(b"exe")

            with self.assertRaisesRegex(RuntimeError, r"\.dmg"):
                release_assets(root)

    def test_wait_for_tag_retries_until_pull_mirror_finishes(self) -> None:
        client = _TagSequenceClient([False, False, True])

        wait_for_tag(client, "v1.1.4", timeout_seconds=1, interval_seconds=0)

        self.assertEqual(client.calls, 3)


if __name__ == "__main__":
    unittest.main()
