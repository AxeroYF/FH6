import unittest

import numpy as np

from flow_cj import (
    advance_yolo_target_region_state,
    analyze_yolo_target_region,
    choose_yolo_candidate_visual_order,
    find_yolo_car_candidate,
    is_yolo_target_signal_low,
    yolo_box_distance,
)


def make_box(name, x1, y1, x2, y2, conf):
    return {
        "name": name,
        "conf": conf,
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "w": x2 - x1,
        "h": y2 - y1,
        "cx": (x1 + x2) / 2,
        "cy": (y1 + y2) / 2,
    }


class CandidateHarness:
    yolo_box_distance = yolo_box_distance

    @staticmethod
    def yolo_yellow_tag_ratio(_img, _tag):
        return 1.0


class YoloSelectionTests(unittest.TestCase):
    def test_pre_target_empty_pages_never_end_scan(self):
        seen, low_pages, finished = False, 0, False
        for _ in range(4):
            seen, low_pages, finished = advance_yolo_target_region_state(
                seen, low_pages, stable_target_region=False, target_low_page=True
            )
        self.assertFalse(seen)
        self.assertEqual(low_pages, 0)
        self.assertFalse(finished)

    def test_empty_first_target_page_does_not_end_multi_page_block(self):
        seen, low_pages, finished = advance_yolo_target_region_state(
            False, 0, stable_target_region=True, target_low_page=False
        )
        self.assertTrue(seen)
        self.assertEqual(low_pages, 0)
        self.assertFalse(finished)

        seen, low_pages, finished = advance_yolo_target_region_state(
            seen, low_pages, stable_target_region=True, target_low_page=False
        )
        self.assertTrue(seen)
        self.assertEqual(low_pages, 0)
        self.assertFalse(finished)

    def test_scan_ends_after_two_low_pages_beyond_target_block(self):
        seen, low_pages, finished = advance_yolo_target_region_state(
            True, 0, stable_target_region=False, target_low_page=True
        )
        self.assertEqual(low_pages, 1)
        self.assertFalse(finished)
        seen, low_pages, finished = advance_yolo_target_region_state(
            seen, low_pages, stable_target_region=False, target_low_page=True
        )
        self.assertEqual(low_pages, 2)
        self.assertTrue(finished)

    def test_target_page_without_new_badge_pair_is_page_level_evidence(self):
        boxes = [
            make_box("new", 300, 200, 330, 230, 0.95),
            make_box("b600", 700, 220, 750, 250, 0.90),
            make_box("b600", 950, 220, 1000, 250, 0.88),
        ]
        analysis = analyze_yolo_target_region(
            CandidateHarness(),
            np.zeros((900, 1600, 3), dtype=np.uint8),
            boxes,
            b600_threshold=0.58,
            min_tag_yellow_ratio=0.18,
        )
        self.assertTrue(analysis["target_region"])
        self.assertEqual(analysis["new_badge_pair_count"], 0)

    def test_generic_new_signal_does_not_block_target_low(self):
        maxima = {"new": 0.97, "b600": 0.0, "car": 0.0}
        thresholds = {"new": 0.25, "b600": 0.58, "car": 0.60}
        self.assertTrue(is_yolo_target_signal_low(maxima, thresholds))

    def test_weak_false_positives_do_not_trigger_slow_confirmation(self):
        maxima = {"new": 0.96, "b600": 0.35, "car": 0.38}
        thresholds = {"b600": 0.58, "car": 0.60}
        self.assertTrue(is_yolo_target_signal_low(maxima, thresholds))

    def test_strong_target_badge_triggers_stable_confirmation(self):
        maxima = {"new": 0.0, "b600": 0.92, "car": 0.0}
        thresholds = {"b600": 0.58, "car": 0.60}
        self.assertFalse(is_yolo_target_signal_low(maxima, thresholds))

    def test_multiple_candidates_choose_visual_top_left_not_highest_score(self):
        boxes = [
            make_box("car", 100, 100, 300, 250, 0.70),
            make_box("new", 240, 190, 260, 210, 0.70),
            make_box("b600", 225, 195, 245, 215, 0.70),
            make_box("car", 400, 100, 600, 250, 0.99),
            make_box("new", 540, 190, 560, 210, 0.99),
            make_box("b600", 525, 195, 545, 215, 0.99),
        ]
        candidate, _ = find_yolo_car_candidate(
            CandidateHarness(),
            np.zeros((500, 1000, 3), dtype=np.uint8),
            boxes,
        )
        self.assertEqual(candidate["car"]["x1"], 100)
        self.assertLess(candidate["score"], 0.99)

    def test_same_visual_row_ignores_small_vertical_box_jitter(self):
        left = {
            "tag": make_box("new", 240, 194, 260, 214, 0.70),
            "car": make_box("car", 100, 100, 300, 250, 0.70),
            "score": 0.70,
        }
        right = {
            "tag": make_box("new", 540, 190, 560, 210, 0.99),
            "car": make_box("car", 400, 100, 600, 250, 0.99),
            "score": 0.99,
        }
        selected, row_count = choose_yolo_candidate_visual_order([right, left])
        self.assertIs(selected, left)
        self.assertEqual(row_count, 2)


if __name__ == "__main__":
    unittest.main()
