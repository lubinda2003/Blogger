"""Regression tests for live claim evidence matching."""

import unittest

from src.quality_checks import (
    _evidence_text_for_matching,
    claim_is_represented_in_article,
)


class TestLiveClaimEvidenceMatching(unittest.TestCase):
    def test_compound_statistics_can_be_supported_across_a_short_paragraph(self):
        claim = (
            "A 2021 study by Upwork revealed that 36% of American workers "
            "(70 million people) and 51% of post-graduate workers participate "
            "in freelance work, driven largely by schedule flexibility and "
            "the desire to earn extra income."
        )
        article = (
            "A 2021 study by Upwork showed that 36% of American workers "
            "participate in freelance work. That equals 70 million people. "
            "The study also showed that 51% of post-graduate workers do "
            "freelance work. Many people choose freelancing for flexible "
            "schedules and extra income."
        )
        self.assertTrue(claim_is_represented_in_article(claim, article))

    def test_paraphrased_tool_features_are_matched(self):
        fireflies = (
            "Fireflies.ai automatically joins, records, transcribes, and "
            "summarizes client call discussions."
        )
        article = (
            "Fireflies.ai joins client calls automatically to record, "
            "transcribe, and summarize your meetings."
        )
        self.assertTrue(claim_is_represented_in_article(fireflies, article))

        perplexity = (
            "Perplexity functions as an AI search engine that delivers "
            "detailed answers supported by inline web citations."
        )
        article = (
            "Perplexity is an AI search engine that gives detailed answers "
            "with web links as sources."
        )
        self.assertTrue(claim_is_represented_in_article(perplexity, article))

    def test_trial_claim_is_matched_to_its_nearby_context(self):
        claim = (
            "Iconosquare offers a 14-day free trial for freelancers looking "
            "to evaluate its social management platform before committing "
            "to a paid plan."
        )
        article = (
            "Iconosquare is a social media management platform. It offers "
            "post scheduling and audience analytics. Iconosquare offers a "
            "14-day free trial. Freelancers can test the platform before "
            "spending money on a paid subscription."
        )
        self.assertTrue(claim_is_represented_in_article(claim, article))

    def test_unrelated_number_cannot_support_a_claim(self):
        claim = "The free plan includes 5 project boards."
        article = (
            "The free plan includes project boards. "
            "The paid plan costs 5 dollars each month."
        )
        self.assertFalse(claim_is_represented_in_article(claim, article))

    def test_negation_must_be_preserved_in_the_matching_context(self):
        claim = "The free plan does not include team collaboration."
        self.assertTrue(
            claim_is_represented_in_article(
                claim, "The free plan does not include team collaboration features."
            )
        )
        self.assertFalse(
            claim_is_represented_in_article(
                claim, "The free plan includes team collaboration features."
            )
        )

    def test_markdown_links_and_emphasis_do_not_break_source_quote_matching(self):
        source = (
            "[A 2021 study](https://example.com) by Upwork found that "
            "**36% of American workers** participate in freelance work."
        )
        quote = "A 2021 study by Upwork found that 36% of American workers"
        self.assertIn(
            _evidence_text_for_matching(quote),
            _evidence_text_for_matching(source),
        )

        dochipo = "**Upwork:** Freelance marketplace to find work across various fields."
        self.assertIn(
            _evidence_text_for_matching(
                "Upwork: Freelance marketplace to find work across various fields."
            ),
            _evidence_text_for_matching(dochipo),
        )

        linked = "Check out the [14-day free](https://example.com) trial."
        self.assertIn(
            _evidence_text_for_matching("Check out the 14-day free"),
            _evidence_text_for_matching(linked),
        )


if __name__ == "__main__":
    unittest.main()
