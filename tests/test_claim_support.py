"""Claim support must accept real roundup articles and still reject unrelated or error pages."""

import unittest

from src.research import ResearchCollector

CLAIM = "Official capabilities and workflow instructions for Best Free Invoicing and Payment Tools for International Freelancers"
SENTENCE = (
    "{} is a free invoicing tool for freelancers. It lets you send invoices, accept payment from international "
    "clients, and track late payment. The free plan covers basic invoicing."
)


def roundup(extra_head="", extra_body=""):
    items = "".join(f"<p>{SENTENCE.format(n)}</p>" for n in ("Wave", "Zoho Invoice", "Invoice Ninja", "PayPal", "Wise", "Square", "Payoneer", "Stripe", "Helcim", "Bonsai"))  # about 2,000 characters, like a real article
    return f"<html><head>{extra_head}</head><body><main><h1>Best free invoicing software for freelancers</h1>{items}{extra_body}</main></body></html>"


class TestClaimSupport(unittest.TestCase):
    def setUp(self):
        self.rc = ResearchCollector()

    def test_a_real_roundup_article_supports_a_long_title_claim(self):
        self.assertIsNotNone(self.rc.find_supporting_excerpt(CLAIM, roundup()))

    def test_an_unrelated_article_does_not(self):
        garden = "<main>" + "".join("<p>Water your tomatoes in the morning and add mulch to keep the soil cool and moist.</p>" for _ in range(12)) + "</main>"
        self.assertIsNone(self.rc.find_supporting_excerpt(CLAIM, garden))

    def test_keywords_scattered_across_the_whole_page_do_not_count(self):
        filler = "<p>" + "Unrelated filler text about something else entirely. " * 6 + "</p>"
        spread = "<main>" + "<p>Best invoicing notes.</p>" + filler * 10 + "<p>Free payment tips.</p>" + filler * 10 + "<p>International freelancers.</p></main>"
        self.assertIsNone(self.rc.find_supporting_excerpt(CLAIM, spread))

    def test_not_found_text_inside_script_code_does_not_reject_a_valid_page(self):
        script = '<script id="__NEXT_DATA__">{"page":"/404","title":"Page not found","statusCode":404}</script>'
        self.assertIsNotNone(self.rc.find_supporting_excerpt(CLAIM, roundup(extra_head=script)))

    def test_a_passing_mention_deep_in_a_long_article_does_not_reject_it(self):
        self.assertIsNotNone(self.rc.find_supporting_excerpt(CLAIM, roundup(extra_body="<p>If you see access denied, check your login.</p>")))

    def test_a_real_error_page_is_still_rejected(self):
        page = "<html><head><title>404 Not Found</title></head><body><main><h1>Page not found</h1><p>Best free invoicing tools for international freelancers and payment.</p></main></body></html>"
        self.assertIsNone(self.rc.find_supporting_excerpt(CLAIM, page))

    def test_a_short_blocked_page_is_still_rejected(self):
        page = "<html><body><p>Access denied. Please verify you are human to see invoicing payment tools.</p></body></html>"
        self.assertIsNone(self.rc.find_supporting_excerpt(CLAIM, page))

    def test_a_direct_phrase_match_still_works(self):
        self.assertIsNotNone(self.rc.find_supporting_excerpt("free invoicing tool", roundup()))


if __name__ == "__main__":
    unittest.main()
