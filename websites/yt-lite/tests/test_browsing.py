"""Duration filtering regressions."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

from flask import template_rendered

APP_DIR = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("yt_lite_app", APP_DIR / "app.py")
yt_lite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(yt_lite)


class BrowsingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        yt_lite.DB_PATH = str(Path(self.temp.name) / "test.db")
        yt_lite.app.config.update(TESTING=True)
        with yt_lite.app.app_context():
            yt_lite.init_db()
            db = yt_lite.get_db()
            db.execute("DELETE FROM videos")
            for duration in ("0:59", "3:59", "4:00", "4:01", "10:05", "20:00", "20:01", "100:00"):
                yt_lite.insert_video_seed(db, {
                    "id": duration, "title": duration, "duration": duration,
                    "video_path": "videos/test.mp4", "created_at": "2000-01-01",
                })
            db.commit()
        self.client = yt_lite.app.test_client()

    def test_duration_boundaries_and_multiple_digit_minutes(self):
        contexts = []
        def capture(sender, template, context, **kwargs):
            contexts.append(context)
        with template_rendered.connected_to(capture, yt_lite.app):
            for duration, expected in {
                "short": {"0:59", "3:59"},
                "medium": {"4:00", "4:01", "10:05", "20:00"},
                "long": {"20:01", "100:00"},
            }.items():
                with self.subTest(duration=duration):
                    self.assertEqual(self.client.get("/", query_string={"duration": duration}).status_code, 200)
                    self.assertEqual({v["id"] for v in contexts[-1]["videos"]}, expected)
