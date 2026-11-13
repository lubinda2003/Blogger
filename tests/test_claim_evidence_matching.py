"""Regression tests for local claim/evidence matching."""

import unittest

from src.quality_checks import claim_is_represented_in_article


class TestClaimEvidenceMatching(unittest.TestCase):
    def test_unrelated_article_negation_does_not_reject_positive_claim(self):
        claim = "The platform offers free invoicing tools for freelancers."
        article = (
            "The platform offers free invoicing tools for freelancers. "
            "It does not include payroll management."
        )
        self.assertTrue(claim_is_represented_in_article(claim, article))

    def test_claim_negation_must_be_preserved_in_matching_context(self):
        claim = "The free plan does not include team collaboration."
        matching = "The free plan does not include team collaboration features."
        contradicted = "The free plan includes team collaboration features."
        self.assertTrue(claim_is_represented_in_article(claim, matching))
        self.assertFalse(claim_is_represented_in_article(claim, contradicted))

    def test_unrelated_number_elsewhere_cannot_support_claim(self):
        claim = "The free plan includes 5 project boards."
        article = (
            "The free plan includes project boards. "
            "The paid plan costs 5 dollars each month."
        )
        self.assertFalse(claim_is_represented_in_article(claim, article))

    def test_number_and_key_terms_in_local_context_pass(self):
        claim = "The free plan includes 5 project boards."
        article = "Users on the free plan can create 5 project boards."
        self.assertTrue(claim_is_represented_in_article(claim, article))


if __name__ == "__main__":
    unittest.main()
