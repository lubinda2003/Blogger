"""Tests for the constrained spreadsheet example evaluator."""
import unittest

from src.spreadsheet_validation import (
    FormulaValidationError,
    evaluate_formula,
    validate_spreadsheet_examples,
)


class TestSpreadsheetFormulaEvaluation(unittest.TestCase):
    def setUp(self):
        self.cells = {
            "A2": "Food", "A3": "Transport", "A4": "Food", "A5": "Rent",
            "B2": 120, "B3": 50, "B4": 80, "B5": 500,
            "C2": 100, "C3": 60, "C4": 80, "C5": 450,
        }

    def test_sum_range(self):
        self.assertEqual(evaluate_formula("=SUM(B2:B5)", self.cells), 750)

    def test_average_range(self):
        self.assertEqual(evaluate_formula("=AVERAGE(B2:B5)", self.cells), 187.5)

    def test_countif_exact_text(self):
        self.assertEqual(evaluate_formula('=COUNTIF(A2:A5,"Food")', self.cells), 2)

    def test_averageif_criteria_and_average_ranges(self):
        self.assertEqual(evaluate_formula('=AVERAGEIF(A2:A5,"Food",B2:B5)', self.cells), 100)

    def test_if_with_cell_arithmetic_and_text_outputs(self):
        self.assertEqual(evaluate_formula('=IF(B2-C2>0,"Over","Under")', self.cells), "Over")
        self.assertEqual(evaluate_formula('=IF(B3-C3>0,"Over","Under")', self.cells), "Under")

    def test_missing_cell_reference_is_reported(self):
        with self.assertRaisesRegex(FormulaValidationError, "missing cell"):
            evaluate_formula("=SUM(B2:B6)", self.cells)

    def test_unsupported_function_fails_clearly(self):
        with self.assertRaises(FormulaValidationError):
            evaluate_formula("=XLOOKUP(A2,A2:A5,B2:B5)", self.cells)

    def test_incorrect_expected_result_is_rejected(self):
        examples = [{
            "application": "Excel",
            "formula_cell": "D2",
            "formula": "=SUM(B2:B5)",
            "cells": [{"reference": k, "value": v} for k, v in self.cells.items()],
            "expected_result": 700,
        }]
        failures = validate_spreadsheet_examples(examples)
        self.assertTrue(any("incorrect expected result" in item for item in failures))

    def test_correct_expected_result_passes(self):
        examples = [{
            "application": "Google Sheets",
            "formula_cell": "D2",
            "formula": "=SUM(B2:B5)",
            "cells": [{"reference": k, "value": v} for k, v in self.cells.items()],
            "expected_result": 750,
        }]
        self.assertEqual(validate_spreadsheet_examples(examples), [])


if __name__ == "__main__":
    unittest.main()
