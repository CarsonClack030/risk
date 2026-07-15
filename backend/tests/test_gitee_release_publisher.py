import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.publish_gitee_release import GiteeClient, release_assets, wait_for_tag


class _TagSequenceClient:
    def __init__(self, states: list[bool]) -> None:
        self.states = iter(states)
        self.calls = 0

    def tag_exists(self, _tag: str) -> bool:
        self.calls += 1
        return next(self.states)


class GiteeReleasePublisherTests(unittest.TestCase):
    @patch("scripts.publish_gitee_release.urlopen")
    def test_pull_mirror_request_keeps_token_out_of_headers(self, mock_open) -> None:
        response = MagicMock()
        response.read.return_value = b"{}"
        mock_open.return_value.__enter__.return_value = response

        GiteeClient("private-token", "CarsonClack030", "risk").trigger_pull_mirror()

        request = mock_open.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertIn("/remote_mirror/pull?access_token=private-token", request.full_url)
        self.assertNotIn("Authorization", request.headers)

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

        wait_for_tag(client, "v1.1.5", timeout_seconds=1, interval_seconds=0)

        self.assertEqual(client.calls, 3)


if __name__ == "__main__":
    unittest.main()
