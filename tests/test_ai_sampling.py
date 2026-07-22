import time
import unittest

from image_matcher import ImageMatcherMixin


class SlowInferenceHarness(ImageMatcherMixin):
    def __init__(self):
        self.is_running = True
        self.config = {
            "ai_assist": True,
            "ai_prefer": True,
            "ai_only": True,
            "ai_auto_capture": False,
        }
        self.regions = {"全界面": (0, 0, 1600, 900)}
        self.calls = 0

    def find_new_consumable_car_with_ai(self, region=None, save_miss=False):
        self.calls += 1
        time.sleep(0.03)
        self.ai_car_last_analysis = {
            "valid": True,
            "target_low": False,
            "target_region": True,
            "new_badge_pair_count": 0,
            "max_conf": {"new": 0.0, "b600": 0.90, "car": 0.0},
        }
        return None

    def log(self, *_args, **_kwargs):
        return None


class AISamplingTests(unittest.TestCase):
    def test_confirmation_collects_two_samples_after_deadline(self):
        harness = SlowInferenceHarness()
        result = harness.wait_for_new_consumable_car(
            timeout=0.01,
            interval=0.01,
            min_ai_samples=2,
        )
        self.assertIsNone(result)
        self.assertGreaterEqual(harness.calls, 2)
        self.assertGreaterEqual(harness.ai_car_page_analysis["samples"], 2)
        self.assertTrue(harness.ai_car_page_target_region_exhausted)


if __name__ == "__main__":
    unittest.main()
