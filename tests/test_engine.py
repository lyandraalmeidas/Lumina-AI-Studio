import tempfile
import threading
import unittest
from pathlib import Path

import cv2
import numpy as np

import engine
from engine import Settings


class EngineTests(unittest.TestCase):
    def test_output_dimensions_preserve_aspect_and_even_sizes(self):
        self.assertEqual(engine.out_size(1920, 1080, 2160), (3840, 2160))
        width, height = engine.out_size(1921, 1081, 1440)
        self.assertEqual(width % 2, 0)
        self.assertEqual(height % 2, 0)
        self.assertGreaterEqual(height, 1440)

    def test_classic_image_processing_still_reads_and_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            target = Path(directory) / "result.png"
            image = np.zeros((48, 64, 3), dtype=np.uint8)
            image[8:40, 12:52] = (40, 120, 220)
            self.assertTrue(cv2.imwrite(str(source), image))
            settings = Settings(
                denoise=0, color=False, face=False, upscale=False,
                use_ai=False, sharpen=0,
            )
            engine.process_image(str(source), str(target), settings)
            result = engine.read_image(str(target))
            self.assertEqual(result.shape, image.shape)
            self.assertTrue(np.array_equal(result, image))

    def test_unsupported_media_is_reported(self):
        with self.assertRaisesRegex(ValueError, "Formato não suportado"):
            engine.read_first_frame("unknown.xyz")


if __name__ == "__main__":
    unittest.main()
