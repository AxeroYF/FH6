import unittest

import cv2

from flow_race import _verify_challenge_result_with_ocr
from race_result_ocr import ChallengeResultOCR


class ChallengeResultOCRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ocr = ChallengeResultOCR()

    def test_success_reference(self):
        image = cv2.imread("images/1080p/challenge_success_full.png")
        result = self.ocr.recognize(image)
        self.assertEqual(result["status"], "success")
        self.assertIn("完成", result["text"])

    def test_failed_reference(self):
        image = cv2.imread("images/1080p/challenge_failed_full.png")
        result = self.ocr.recognize(image)
        self.assertEqual(result["status"], "failed")
        self.assertIn("失败", result["text"])

    def test_ambiguous_template_requires_two_ocr_frames(self):
        image = cv2.imread("images/1080p/challenge_success_full.png")

        class Harness:
            config = {
                "recognition_profiles": {
                    "race.challenge_success": {"ocr_interval": 0.0}
                }
            }
            regions = {"全界面": (0, 0, image.shape[1], image.shape[0])}
            challenge_result_ocr = self.ocr

            @staticmethod
            def capture_region(_region):
                return image

            @staticmethod
            def log(*_args, **_kwargs):
                return None

        bot = Harness()
        self.assertIsNone(_verify_challenge_result_with_ocr(bot, 0.60, 0.58))
        self.assertEqual(
            _verify_challenge_result_with_ocr(bot, 0.60, 0.58),
            "success",
        )


if __name__ == "__main__":
    unittest.main()
