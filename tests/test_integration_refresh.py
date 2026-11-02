import os
import tempfile
import unittest
from unittest.mock import patch

import httpx

from functions import appFunctions, databaseFunctions, torboxFunctions
from tests.fake_torbox_api import FakeTorBoxApi


class FailedTypeKeepsDatabaseRowsTest(unittest.TestCase):
    """Integration test: a failing TorBox type must not clear its stored rows.

    This goes through the real ``getUserDownloads`` HTTP path and a real TinyDB
    file, unlike the mocked staging test in ``test_refresh.py``.
    """

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

        self.original_cwd = os.getcwd()
        os.chdir(self.tempdir.name)
        self.addCleanup(os.chdir, self.original_cwd)

        databaseFunctions.closeAllDatabases()
        self.addCleanup(databaseFunctions.closeAllDatabases)

        self.torrent_row = {
            "type": "torrents",
            "item_id": 7,
            "file_id": 8,
            "metadata_filename": "Existing (2024).mkv",
            "metadata_rootfoldername": "Existing (2024)",
            "metadata_foldername": None,
            "metadata_mediatype": "movie",
            "download_link": "http://old",
            "file_size": 123,
        }
        databaseFunctions.getDatabase("torrents").insert(self.torrent_row)
        databaseFunctions.getDatabase("usenet").insert(
            {**self.torrent_row, "type": "usenet"}
        )

        # torrents fails; the other two succeed with an empty library.
        self.api = FakeTorBoxApi({"torrents": 500, "usenet": [], "webdl": []}).start()
        self.addCleanup(self.api.stop)

        client = httpx.Client(base_url=self.api.base_url)
        self.addCleanup(client.close)
        patcher = patch.object(torboxFunctions, "api_http_client", client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_failed_type_keeps_existing_rows(self):
        result = appFunctions.getAllUserDownloadsFresh()

        self.assertEqual(
            result["errors"],
            {"torrents": "Error fetching torrents at offset 0. 500"},
        )

        torrents, ok, _ = databaseFunctions.getAllData("torrents")
        self.assertTrue(ok)
        self.assertEqual(torrents, [self.torrent_row])

        usenet, ok, _ = databaseFunctions.getAllData("usenet")
        self.assertTrue(ok)
        self.assertEqual(usenet, [])

        paths = [path for path, _ in self.api.requests]
        self.assertEqual(paths.count("/v1/api/torrents/mylist"), 1)
        self.assertEqual(paths.count("/v1/api/usenet/mylist"), 1)
        self.assertEqual(paths.count("/v1/api/webdl/mylist"), 1)


if __name__ == "__main__":
    unittest.main()
