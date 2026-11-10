"""Run with `python -m unittest test_sdk_compatibility.py` from this plugin."""

import unittest
from unittest.mock import patch

import dropbox
from dropbox.exceptions import ApiError

from dropbox_utils import DropboxUtils


class DropboxSdkTest(unittest.TestCase):
    def test_search_options_and_metadata_union(self):
        folder = dropbox.files.FolderMetadata(name="Docs", id="id:folder", path_display="/Docs")
        response = dropbox.files.SearchV2Result(matches=[
            dropbox.files.SearchMatchV2(metadata=dropbox.files.MetadataV2.metadata(folder)),
            dropbox.files.SearchMatchV2(metadata=dropbox.files.MetadataV2.other),
        ], has_more=False)
        client = dropbox.Dropbox("test")
        with patch.object(client, "request", return_value=response) as request:
            result = DropboxUtils.search_files(client, "Docs", 5)
        self.assertEqual(result, [{"name": "Docs", "path": "/Docs", "id": "id:folder", "type": "folder"}])
        argument = request.call_args.args[2]
        self.assertEqual(argument.query, "Docs")
        self.assertEqual(argument.options.max_results, 5)

    def test_api_errors_retain_sdk_details(self):
        client = dropbox.Dropbox("test")
        error = ApiError("request-id", "test failure", "User message", "en")
        operations = [
            (DropboxUtils.list_folder, ("",)),
            (DropboxUtils.search_files, ("Docs",)),
            (DropboxUtils.upload_file, ("/test.txt", b"test")),
            (DropboxUtils.download_file, ("/test.txt",)),
            (DropboxUtils.create_folder, ("/Docs",)),
            (DropboxUtils.delete_file, ("/test.txt",)),
        ]
        with patch.object(client, "request", side_effect=error):
            for operation, args in operations:
                with self.subTest(operation=operation.__name__):
                    with self.assertRaises(ApiError) as raised:
                        operation(client, *args)
                    self.assertIs(raised.exception, error)


if __name__ == "__main__":
    unittest.main()
