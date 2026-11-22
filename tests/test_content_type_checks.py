"""Tests for format-aware editorial structure checks."""
import unittest

from src.content_type_checks import analyze_content_type, normalize_content_type


class TestContentTypeNormalization(unittest.TestCase):
    def test_legacy_queue_labels_map_to_approved_formats(self):
        self.assertEqual(normalize_content_type("Tutorial"), "Step-by-step tutorial")
        self.assertEqual(normalize_content_type("How-to"), "Step-by-step tutorial")
        self.assertEqual(normalize_content_type("Guide"), "Beginner guide")
        self.assertEqual(normalize_content_type("Practical project"), "Practical project")
        self.assertEqual(normalize_content_type("Comparison"), "Comparison")
        self.assertEqual(normalize_content_type("unknown"), "")


class TestContentTypeChecks(unittest.TestCase):
    def test_tutorial_warns_when_steps_and_success_check_are_missing(self):
        warnings, metrics = analyze_content_type("Tutorial", "<p>Learn about the feature.</p>")
        self.assertEqual(len(warnings), 2)
        self.assertEqual(metrics["content_type_list_items"], 0)

    def test_complete_tutorial_has_no_format_warnings(self):
        html = "<ol><li>Open settings.</li><li>Choose the option.</li></ol><p>Verify the result. You should see the change.</p>"
        warnings, _ = analyze_content_type("How-to", html)
        self.assertEqual(warnings, [])

    def test_troubleshooting_checks_symptoms_safe_steps_and_verification(self):
        html = "<p>If you see an error message, make a backup first.</p><ol><li>Check the connection.</li></ol><p>Verify the result; if it fails, stop and contact support.</p>"
        warnings, _ = analyze_content_type("Troubleshooting", html)
        self.assertEqual(warnings, [])

    def test_comparison_requires_criteria_and_tradeoffs(self):
        warnings, _ = analyze_content_type("Comparison", "<p>Option one costs less. Option two has more features.</p>")
        self.assertTrue(any("consistent, named criteria" in item for item in warnings))
        self.assertTrue(any("limitations" in item for item in warnings))

    def test_review_flags_missing_limitations(self):
        warnings, _ = analyze_content_type("Review", "<p>Compare features and pricing.</p>")
        self.assertTrue(any("meaningful limitations" in item for item in warnings))

    def test_checklist_requires_actual_items(self):
        warnings, _ = analyze_content_type("Checklist", "<p>Here is a checklist of things to consider.</p>")
        self.assertTrue(any("actual checklist" in item for item in warnings))

    def test_formula_tutorial_remains_supported_by_dedicated_checker(self):
        warnings, _ = analyze_content_type("Formula or calculation tutorial", "<p>Enter =SUM(A1:A3). Verify the result.</p>")
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
