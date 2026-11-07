"""Plain-English measurement for article HTML (stdlib only).

Used by the quality gate and the writer's simplification pass so "clear, easy English" is measured, not hoped for.
"""

import re
from dataclasses import dataclass

_SKIP_BLOCKS = r"<(pre|code|script|style|svg|table|figure)[^>]*>.*?</\1>"
_SOURCES_BLOCK = r'<div[^>]*class="[^"]*article-sources[^"]*"[^>]*>.*?</div>'
_HEADINGS = r"<h[1-6][^>]*>.*?</h[1-6]>"


@dataclass
class Readability:
    words: int
    sentences: int
    avg_sentence_words: float
    fk_grade: float
    long_sentence_pct: float  # share of sentences longer than 25 words

    def is_hard(self, max_grade: float) -> bool:
        return self.fk_grade > max_grade or self.avg_sentence_words > 25


def prose_text(html_str: str) -> str:
    """Article body as plain prose: no code, tables, headings, sources list or markup."""
    text = html_str or ""
    for pattern in (_SOURCES_BLOCK, _SKIP_BLOCKS, _HEADINGS):
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE | re.DOTALL)
    # Paragraphs and list items end a sentence even without a full stop.
    text = re.sub(r"</(p|li|blockquote|div)>", ". ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;|&#\d+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _syllables(word: str) -> int:
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    if len(word) <= 3:
        return 1
    word = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", word)
    word = re.sub(r"^y", "", word)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", word)))


def analyze(html_str: str) -> Readability:
    text = prose_text(html_str)
    raw_sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if re.search(r"[A-Za-z]", s)]
    sentence_words = [len(re.findall(r"[A-Za-z0-9'’\-]+", s)) for s in raw_sentences]
    sentence_words = [n for n in sentence_words if n > 0]
    words = sum(sentence_words)
    sentences = len(sentence_words)
    if not words or not sentences:
        return Readability(0, 0, 0.0, 0.0, 0.0)
    syllables = sum(_syllables(w) for w in re.findall(r"[A-Za-z]+", text))
    grade = 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59
    long_pct = 100.0 * sum(1 for n in sentence_words if n > 25) / sentences
    return Readability(words, sentences, round(words / sentences, 1), round(max(grade, 0.0), 1), round(long_pct, 1))
