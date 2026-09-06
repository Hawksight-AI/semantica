"""
Test for the Claude Code plugin manifest (Issue #1350).

Claude Code's plugin schema requires "agents" to be an array of .md file
paths (a bare directory string is rejected with "agents: Invalid input"),
while "skills" may be a directory string. This guards the manifest shape
so the bundled plugin stays installable.
"""
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "plugins" / ".claude-plugin" / "plugin.json"


class TestPluginManifest(unittest.TestCase):
    """Validate plugins/.claude-plugin/plugin.json against Claude Code's schema shape."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.plugin_root = MANIFEST.parent.parent

    def test_agents_is_list_of_md_file_paths(self):
        agents = self.manifest["agents"]
        self.assertIsInstance(
            agents, list,
            'Claude Code rejects "agents" unless it is an array of .md file paths',
        )
        self.assertTrue(agents, "agents list should not be empty")
        for entry in agents:
            self.assertIsInstance(entry, str)
            self.assertTrue(entry.endswith(".md"), f"{entry} is not a .md file path")
            path = self.plugin_root / entry
            self.assertTrue(path.is_file(), f"{entry} does not exist under plugins/")

    def test_agents_list_covers_all_agent_files(self):
        declared = {Path(entry).name for entry in self.manifest["agents"]}
        on_disk = {p.name for p in (self.plugin_root / "agents").glob("*.md")}
        self.assertEqual(declared, on_disk)

    def test_skills_directory_exists(self):
        skills = self.manifest["skills"]
        self.assertIsInstance(skills, str)
        self.assertTrue((self.plugin_root / skills).is_dir())


if __name__ == "__main__":
    unittest.main()
