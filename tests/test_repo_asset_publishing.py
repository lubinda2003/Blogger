"""Regression tests for isolated repository image publishing."""

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.screenshot_capture import ScreenshotCapture


class TestRepositoryAssetPublishing(unittest.TestCase):
    def test_asset_push_uses_clean_worktree_not_dirty_pipeline_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "cover.png"
            image.write_bytes(b"test-image")
            calls = []

            def fake_run(command, **kwargs):
                calls.append((command, kwargs))
                if "worktree" in command and "add" in command:
                    checkout = Path(command[command.index("--detach") + 1])
                    checkout.mkdir(parents=True, exist_ok=True)
                if "status" in command:
                    return SimpleNamespace(stdout="A assets/screenshots/cover-deadbeef1234.png\n", stderr="")
                return SimpleNamespace(stdout="", stderr="")

            capture = ScreenshotCapture(repo_assets_dir="assets/screenshots")
            with patch.dict(os.environ, {
                "GITHUB_ACTIONS": "true",
                "GITHUB_REPOSITORY": "owner/repository",
                "GITHUB_REF_NAME": "main",
            }), patch("src.visual_tools.optimize_image", return_value=image), \
                 patch("src.screenshot_capture.subprocess.run", side_effect=fake_run):
                url = capture.publish_to_repo_assets(image, "cover", "deadbeef1234567890")

            self.assertEqual(
                url,
                "https://cdn.jsdelivr.net/gh/owner/repository@main/assets/screenshots/cover-deadbeef12.png",
            )
            commands = [call[0] for call in calls]
            self.assertTrue(any("fetch" in command for command in commands))
            self.assertTrue(any("worktree" in command and "add" in command for command in commands))
            self.assertTrue(any("push" in command for command in commands))
            self.assertTrue(any("worktree" in command and "remove" in command for command in commands))
            self.assertFalse(any("pull" in command or "rebase" in command for command in commands))
            # Asset staging and commit happen in the temporary worktree, not the pipeline checkout.
            for command, kwargs in calls:
                if "worktree" not in command and any(part in command for part in ("add", "commit", "push")):
                    self.assertIsNotNone(kwargs.get("cwd"))


if __name__ == "__main__":
    unittest.main()
