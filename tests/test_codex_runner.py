from __future__ import annotations

import os
import unittest
from pathlib import Path

from main_service.codex_runner import _base_codex_command


class CodexCommandTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows sandbox configuration only")
    def test_restores_unelevated_sandbox_when_user_config_is_ignored(self):
        command = _base_codex_command(Path("workspace"), Path("output.json"))

        self.assertIn("--ignore-user-config", command)
        config_index = command.index("--config")
        self.assertEqual(command[config_index + 1], 'windows.sandbox="unelevated"')


if __name__ == "__main__":
    unittest.main()
