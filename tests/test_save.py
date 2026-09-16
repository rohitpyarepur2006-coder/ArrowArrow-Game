"""存档模块单元测试：默认值、读写往返、容错合并。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import game.save as save_mod


class SaveTest(unittest.TestCase):
    def test_load_defaults_when_file_missing(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(save_mod, "save_path", lambda: Path(d) / "save.json"):
                self.assertEqual(save_mod.load(), save_mod.DEFAULTS)

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "save.json"
            with patch.object(save_mod, "save_path", lambda: path):
                data = dict(save_mod.DEFAULTS)
                data["unlocked"] = 4
                data["stars"] = {"0": 3, "1": 2}
                data["scores"] = {"0": 1260}
                data["endless_best"] = 980
                data["mid_level"] = {"level": 2, "arrows": [[0, 0, "R"]],
                                     "mistakes": 2, "elapsed": 15.5}
                self.assertTrue(save_mod.save(data))
                loaded = save_mod.load()
                self.assertEqual(loaded["unlocked"], 4)
                self.assertEqual(loaded["stars"]["1"], 2)
                self.assertEqual(loaded["endless_best"], 980)
                self.assertEqual(loaded["mid_level"]["level"], 2)

    def test_load_merges_defaults_for_missing_keys(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "save.json"
            path.write_text(json.dumps({"unlocked": 2}), encoding="utf-8")
            with patch.object(save_mod, "save_path", lambda: path):
                data = save_mod.load()
                self.assertEqual(data["unlocked"], 2)
                self.assertEqual(data["endless_best"], 0)
                self.assertIsNone(data["mid_level"])

    def test_load_tolerates_corrupt_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "save.json"
            path.write_text("not a json{{", encoding="utf-8")
            with patch.object(save_mod, "save_path", lambda: path):
                self.assertEqual(save_mod.load()["unlocked"], 1)

    def test_load_ignores_unknown_keys(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "save.json"
            path.write_text(json.dumps({"unlocked": 3, "hacker": "x"}),
                            encoding="utf-8")
            with patch.object(save_mod, "save_path", lambda: path):
                data = save_mod.load()
                self.assertNotIn("hacker", data)
                self.assertEqual(data["unlocked"], 3)


if __name__ == "__main__":
    unittest.main()
