import http.client
import json
import threading
import unittest
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path
from tempfile import TemporaryDirectory

import server


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.video_dir = self.root / "videos"
        self.video_dir.mkdir()
        self.video = self.video_dir / "MeitanteiConan_Ep_1_SUB_ITA.mp4"
        self.video.write_bytes(b"abcdef")
        self.saved = {
            name: getattr(server, name)
            for name in (
                "LIBRARIES", "VIDEO_DIRS", "LIBRARY_META", "REFERENCE", "TITLE_CARDS",
                "REGISTRY_PATH", "CUSTOM_TITLES_PATH", "MISSING_TITLES_PATH",
                "TITLE_OVERRIDES_PATH", "WATCHED_PATH", "PROGRESS_PATH", "TITLE_CARDS_PATH",
                "LOG_PATH",
            )
        }
        library = {"key": "episodes", "label": "Episodi", "kind": "episodes", "path": str(self.video_dir)}
        server.LIBRARIES = [library]
        server.VIDEO_DIRS = {"episodes": self.video_dir}
        server.LIBRARY_META = {"episodes": library}
        server.REFERENCE = {1: {"num_jap": 1, "name_ita": "Titolo", "name_eng": "Title", "name_jap": "題"}}
        server.TITLE_CARDS = {"1": {"file": "shared.png", "title_observed": "Scheda"}}
        for name, filename in (
            ("REGISTRY_PATH", "registry.json"),
            ("CUSTOM_TITLES_PATH", "custom.json"),
            ("MISSING_TITLES_PATH", "missing.json"),
            ("TITLE_OVERRIDES_PATH", "overrides.json"),
            ("WATCHED_PATH", "watched.json"),
            ("PROGRESS_PATH", "progress.json"),
            ("TITLE_CARDS_PATH", "title_cards.json"),
            ("LOG_PATH", "rename_log.jsonl"),
        ):
            setattr(server, name, self.root / filename)

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(server, name, value)
        self.temp_dir.cleanup()

    def test_progress_requires_the_current_file_identity(self):
        payload = {"folder_key": "episodes", "relative_path": self.video.name, "number": 1, "position": 4, "duration": 60}
        result = server.set_progress(payload)
        self.assertEqual(result["playback"]["position"], 4.0)
        with self.assertRaises(ValueError):
            server.set_progress({**payload, "number": 2})

    def test_movies_with_same_number_keep_independent_watched_state(self):
        library = {"key": "episodes", "label": "Film", "kind": "movies", "path": str(self.video_dir)}
        server.LIBRARY_META["episodes"] = library
        first = self.video_dir / "Film 01 a.mp4"
        second = self.video_dir / "Film 01 b.mp4"
        first.write_bytes(b"a")
        second.write_bytes(b"b")
        server.set_watched({"folder_key": "episodes", "relative_path": first.name, "number": 1, "watched": True})
        self.assertTrue(server.parse_file(first, "episodes")["watched"])
        self.assertFalse(server.parse_file(second, "episodes")["watched"])
        server.set_progress({"folder_key": "episodes", "relative_path": second.name, "number": 1, "position": 55, "duration": 60})
        self.assertTrue(server.parse_file(second, "episodes")["watched"])
        server.set_watched({"folder_key": "episodes", "relative_path": first.name, "number": 1, "watched": False})
        self.assertFalse(server.parse_file(first, "episodes")["watched"])
        self.assertTrue(server.parse_file(second, "episodes")["watched"])

    def test_movie_progress_uses_path_after_fallback_index_changes(self):
        server.LIBRARY_META["episodes"]["kind"] = "movies"
        movie = self.video_dir / "Zeta.mp4"
        movie.write_bytes(b"video")
        original_number = server.parse_existing_file(movie, "episodes")["number"]
        (self.video_dir / "Alfa.mp4").write_bytes(b"video")
        result = server.set_progress({"folder_key": "episodes", "relative_path": movie.name, "number": original_number, "position": 10, "duration": 60})
        self.assertEqual(result["playback"]["position"], 10)

    def test_empty_library_list_survives_restart(self):
        original = server.SETTINGS_PATH
        try:
            server.SETTINGS_PATH = self.root / "settings.json"
            server.SETTINGS_PATH.write_text('{"libraries": []}', encoding="utf-8")
            self.assertEqual(server.load_libraries(), [])
        finally:
            server.SETTINGS_PATH = original

    def test_short_video_does_not_complete_at_start(self):
        result = server.set_progress({"folder_key": "episodes", "relative_path": self.video.name, "number": 1, "position": 0, "duration": 10})
        self.assertFalse(result["playback"]["completed"])

    def test_rename_rejects_mismatched_name_and_path(self):
        with self.assertRaises(ValueError):
            server.rename_file({
                "confirm": True,
                "folder_key": "episodes",
                "current_name": "different.mp4",
                "relative_path": self.video.name,
                "new_name": "renamed.mp4",
            })
        self.assertTrue(self.video.exists())

    def test_changing_one_library_file_number_keeps_shared_title_cards(self):
        result = server.change_episode_number({
            "folder_key": "episodes",
            "current_name": self.video.name,
            "relative_path": self.video.name,
            "old_number": 1,
            "new_number": 2,
        })
        self.assertEqual(result["record"]["number"], 2)
        self.assertEqual(server.TITLE_CARDS, {"1": {"file": "shared.png", "title_observed": "Scheda"}})


class HandlerTestCase(unittest.TestCase):
    def setUp(self):
        ServerTestCase.setUp(self)
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.thread.join()
        self.httpd.server_close()
        ServerTestCase.tearDown(self)

    def request(self, path, *, headers=None, data=None):
        request = urllib.request.Request(self.base_url + path, headers=headers or {}, data=data)
        return urllib.request.urlopen(request, timeout=3)

    def test_static_allowlist_and_dns_rebinding_defense(self):
        with self.request("/index.html") as response:
            self.assertEqual(response.status, 200)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/server.py")
        self.assertEqual(error.exception.code, 404)

        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=3)
        connection.putrequest("GET", "/index.html", skip_host=True)
        connection.putheader("Host", "attacker.example")
        connection.endheaders()
        response = connection.getresponse()
        self.assertEqual(response.status, 421)
        response.read()
        connection.close()

    def test_rejects_cross_origin_and_non_json_posts(self):
        for headers, expected in (({"Content-Type": "application/json", "Origin": "https://example.org"}, 403), ({"Content-Type": "text/plain"}, 415)):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request("/api/title", headers=headers, data=b"{}")
            self.assertEqual(error.exception.code, expected)

    def test_media_range_and_invalid_json_requests(self):
        media_path = "/api/media?folder_key=episodes&path=" + urllib.parse.quote(self.video.name)
        with self.request(media_path, headers={"Range": "bytes=1-3"}) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), b"bcd")
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request(media_path, headers={"Range": "bytes=-"})
        self.assertEqual(error.exception.code, 416)

        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/title", headers={"Content-Type": "application/json"}, data=json.dumps([]).encode())
        self.assertEqual(error.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
