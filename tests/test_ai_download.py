import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ai


class FakeResponse:
    def __init__(self, content, expected_length):
        self.content = content
        self.expected_length = expected_length
        self.position = 0
        self.headers = {"Content-Length": str(expected_length)}

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return None

    def read(self, size):
        chunk = self.content[self.position:self.position + size]
        self.position += len(chunk)
        return chunk


class ModelDownloadTests(unittest.TestCase):
    def test_truncated_model_download_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as directory:
            response = FakeResponse(b"abc", 4)
            with (
                patch.object(ai, "MODELS", directory),
                patch.object(ai.urllib.request, "urlopen", return_value=response),
            ):
                with self.assertRaisesRegex(OSError, "Download incompleto"):
                    ai._weight("x4plus", lambda _message: None)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_complete_model_download_is_atomically_promoted(self):
        with tempfile.TemporaryDirectory() as directory:
            response = FakeResponse(b"model", 5)
            progress = []
            with (
                patch.object(ai, "MODELS", directory),
                patch.object(ai.urllib.request, "urlopen", return_value=response),
            ):
                path = Path(ai._weight(
                    "x4plus", lambda _message: None,
                    progress=lambda *values: progress.append(values),
                ))
            self.assertEqual(path.read_bytes(), b"model")
            self.assertEqual(len(progress), 2)
            self.assertEqual(list(Path(directory).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
