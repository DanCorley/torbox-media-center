import os
import tempfile
import unittest
from unittest.mock import patch

from functions import appFunctions
from functions import stremFilesystemFunctions as strem
from functions.refreshFunctions import diffRecords
from functions.torboxFunctions import DownloadType


def record(item_id, file_id, filename, root, folder=None, link="u", size=1):
    return {
        "type": "torrents",
        "item_id": item_id,
        "file_id": file_id,
        "metadata_filename": filename,
        "metadata_rootfoldername": root,
        "metadata_foldername": folder,
        "download_link": link,
        "file_size": size,
    }


class DiffRecordsTest(unittest.TestCase):
    def test_added_updated_removed(self):
        old = [
            record(1, 1, "a.mkv", "A"),
            record(2, 2, "b.mkv", "B"),
        ]
        new = [
            record(1, 1, "a-renamed.mkv", "A"),
            record(3, 3, "c.mkv", "C"),
        ]

        result = diffRecords(old, new)

        self.assertEqual(result["added"], 1)
        self.assertEqual(result["removed"], 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["changed"], 3)

    def test_unchanged(self):
        items = [record(1, 1, "a.mkv", "A")]
        self.assertEqual(diffRecords(items, list(items))["changed"], 0)


class RefreshStagingTest(unittest.TestCase):
    def test_failed_type_is_not_replaced(self):
        rows = [record(1, 1, "a.mkv", "A")]
        replaced = []

        def fake_get(download_type):
            if download_type is DownloadType.torrent:
                return None, False, "boom"
            return rows, True, "ok"

        def fake_replace(data, type_value):
            replaced.append(type_value)
            return True, "ok"

        with patch.object(appFunctions, "getUserDownloads", side_effect=fake_get), patch.object(
            appFunctions, "replaceData", side_effect=fake_replace
        ):
            result = appFunctions.getAllUserDownloadsFresh()

        self.assertEqual(result["errors"], {"torrents": "boom"})
        self.assertNotIn("torrents", replaced)
        self.assertEqual(len(result["downloads"]), 2)


class RunStrmTest(unittest.TestCase):
    def download(self):
        return {
            "type": "torrents",
            "metadata_mediatype": "movie",
            "metadata_rootfoldername": "Movie (2024)",
            "metadata_filename": "Movie (2024)",
            "download_link": "http://one",
            "file_size": 1,
        }

    def test_writes_new_and_removes_stale(self):
        with tempfile.TemporaryDirectory() as mount:
            stale = os.path.join(mount, "movies", "Old", "Old.strm")
            os.makedirs(os.path.dirname(stale))
            with open(stale, "w", encoding="utf-8") as file:
                file.write("old")

            with patch.object(strem, "MOUNT_PATH", mount), patch.object(
                strem, "RAW_MODE", False
            ), patch.object(
                strem,
                "getAllUserDownloadsWithStatus",
                return_value=([self.download()], {}),
            ):
                result = strem.runStrm()

            self.assertEqual(result["added"], 1)
            self.assertEqual(result["removed"], 1)
            self.assertFalse(os.path.exists(stale))
            self.assertTrue(
                os.path.exists(
                    os.path.join(mount, "movies", "Movie (2024)", "Movie (2024).strm")
                )
            )

    def test_skips_cleanup_on_db_error(self):
        with tempfile.TemporaryDirectory() as mount:
            stale = os.path.join(mount, "movies", "Old", "Old.strm")
            os.makedirs(os.path.dirname(stale))
            with open(stale, "w", encoding="utf-8") as file:
                file.write("old")

            with patch.object(strem, "MOUNT_PATH", mount), patch.object(
                strem, "RAW_MODE", False
            ), patch.object(
                strem,
                "getAllUserDownloadsWithStatus",
                return_value=([], {"torrents": "boom"}),
            ):
                result = strem.runStrm()

            self.assertEqual(result["removed"], 0)
            self.assertTrue(os.path.exists(stale))


class GenerateStremFileTest(unittest.TestCase):
    def test_added_unchanged_updated(self):
        with tempfile.TemporaryDirectory() as mount:
            with patch.object(strem, "MOUNT_PATH", mount), patch.object(
                strem, "RAW_MODE", False
            ):
                path = os.path.join(mount, "movies", "Movie (2024)", "Movie (2024).strm")

                self.assertEqual(
                    strem.generateStremFile(
                        "Movie (2024)", "http://one", "movie", "Movie (2024)"
                    ),
                    "added",
                )
                with open(path, encoding="utf-8") as file:
                    self.assertEqual(file.read(), "http://one")

                self.assertEqual(
                    strem.generateStremFile(
                        "Movie (2024)", "http://one", "movie", "Movie (2024)"
                    ),
                    "unchanged",
                )
                self.assertEqual(
                    strem.generateStremFile(
                        "Movie (2024)", "http://two", "movie", "Movie (2024)"
                    ),
                    "updated",
                )
                with open(path, encoding="utf-8") as file:
                    self.assertEqual(file.read(), "http://two")


if __name__ == "__main__":
    unittest.main()
