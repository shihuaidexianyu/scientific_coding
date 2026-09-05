"""Regression checks for the initially inclusive threshold."""
import unittest
from analysis import filter_trials, summarize


class AnalysisTests(unittest.TestCase):
    def test_threshold_boundary(self):
        rows = [{"trial_id": "c", "condition": "control", "amplitude_uv": 0.5},
                {"trial_id": "t", "condition": "treatment", "amplitude_uv": 1.0}]
        retained, excluded = filter_trials(rows, 0.5)
        self.assertEqual(retained, rows)
        self.assertEqual(excluded, [])

    def test_contrast_direction(self):
        rows = [{"trial_id": "c", "condition": "control", "amplitude_uv": 1.0},
                {"trial_id": "t", "condition": "treatment", "amplitude_uv": 1.5}]
        self.assertEqual(summarize(rows)["difference_uv"], 0.5)


if __name__ == "__main__":
    unittest.main()
