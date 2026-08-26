import asyncio
import unittest
from types import SimpleNamespace

from tools.file_inputs import call_sync, file_bytes, file_name, iter_files


class FileInputTests(unittest.TestCase):
    def test_iter_files_wraps_a_single_file(self) -> None:
        file = SimpleNamespace(filename="a.pdf", blob=b"%PDF")
        self.assertEqual(iter_files(file), [file])

    def test_iter_files_rejects_empty_list(self) -> None:
        with self.assertRaisesRegex(ValueError, "File is required"):
            iter_files([])

    def test_file_bytes_coerces_bytearray_and_memoryview(self) -> None:
        payload = b"%PDF-1.4"
        as_bytearray = SimpleNamespace(filename="doc.pdf", blob=bytearray(payload))
        as_memory = SimpleNamespace(filename="doc.pdf", blob=memoryview(payload))
        self.assertEqual(file_bytes(as_bytearray), payload)
        self.assertEqual(file_bytes(as_memory), payload)

    def test_file_bytes_rejects_nested_list_payload(self) -> None:
        file = SimpleNamespace(filename="doc.pdf", blob=[b"%PDF-a", b"%PDF-b"])
        with self.assertRaises(ValueError) as ctx:
            file_bytes(file)
        self.assertIn("missing binary content", str(ctx.exception))

    def test_file_name_requires_extension_bearing_name(self) -> None:
        with self.assertRaises(ValueError):
            file_name(SimpleNamespace(filename=None, name=None, blob=b"x"))

    def test_call_sync_from_running_event_loop(self) -> None:
        def uses_asyncio_run() -> str:
            return asyncio.run(asyncio.sleep(0, result="ok"))

        async def invoke_from_loop() -> str:
            return call_sync(uses_asyncio_run)

        self.assertEqual(asyncio.run(invoke_from_loop()), "ok")


if __name__ == "__main__":
    unittest.main()
