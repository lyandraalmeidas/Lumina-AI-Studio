import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

import engine
from engine import Settings


class EngineTests(unittest.TestCase):
    def test_creative_filters_preserve_dimensions_and_original(self):
        image = np.zeros((24, 32, 3), dtype=np.uint8)
        image[:, :16] = (20, 80, 220)

        self.assertIs(engine.apply_filter(image, "original"), image)
        for filter_name in engine.FILTERS[1:]:
            with self.subTest(filter_name=filter_name):
                filtered = engine.apply_filter(image, filter_name)
                self.assertEqual(filtered.shape, image.shape)
                self.assertFalse(np.array_equal(filtered, image))
        with self.assertRaisesRegex(ValueError, "Filtro não suportado"):
            engine.apply_filter(image, "unknown")

    def test_warm_and_cool_filters_tint_in_the_expected_direction(self):
        image = np.full((8, 8, 3), (30, 100, 200), dtype=np.uint8)
        warm = engine.apply_filter(image, "warm")
        cool = engine.apply_filter(image, "cool")
        original_red_blue = int(image[:, :, 2].mean() - image[:, :, 0].mean())
        warm_red_blue = int(warm[:, :, 2].mean() - warm[:, :, 0].mean())
        cool_red_blue = int(cool[:, :, 2].mean() - cool[:, :, 0].mean())
        self.assertGreater(warm_red_blue, original_red_blue)
        self.assertLess(cool_red_blue, original_red_blue)

    def test_fast_video_denoising_uses_a_smaller_bilateral_kernel(self):
        image = np.zeros((16, 16, 3), dtype=np.uint8)
        with patch("engine.cv2.bilateralFilter", wraps=cv2.bilateralFilter) as bilateral:
            engine.denoise(image, 50, fast=True)
            self.assertEqual(bilateral.call_args.args[1], 3)
            engine.denoise(image, 50)
            self.assertEqual(bilateral.call_args.args[1], 7)

    def test_noir_filter_is_applied_by_restore(self):
        image = np.zeros((24, 32, 3), dtype=np.uint8)
        image[:, :16] = (20, 80, 220)
        settings = Settings(
            denoise=0, color=False, face=False, upscale=False,
            use_ai=False, sharpen=0, filter_name="noir",
        )
        result = engine.restore(image, settings)
        self.assertTrue(np.array_equal(result[:, :, 0], result[:, :, 1]))
        self.assertTrue(np.array_equal(result[:, :, 1], result[:, :, 2]))

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
