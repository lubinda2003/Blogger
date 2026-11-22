"""Lightweight, format-aware article structure checks.

These checks produce actionable editorial warnings rather than brittle publication
blocks. Existing safety, HTML, and spreadsheet validations remain hard gates.
"""
import re
from html.parser import HTMLParser
from typing import Dict, List, Tuple


ALIASES = {
    "tutorial": "Step-by-step tutorial",
    "how-to": "Step-by-step tutorial",
    "how to": "Step-by-step tutorial",
    "step-by-step tutorial": "Step-by-step tutorial",
    "step by step tutorial": "Step-by-step tutorial",
    "guide": "Beginner guide",
    "beginner guide": "Beginner guide",
    "practical project": "Practical project",
    "project": "Practical project",
    "formula or calculation tutorial": "Formula or calculation tutorial",
    "formula tutorial": "Formula or calculation tutorial",
    "troubleshooting": "Troubleshooting guide",
    "troubleshooting guide": "Troubleshooting guide",
    "comparison": "Comparison",
    "review": "Review or evaluation",
    "review or evaluation": "Review or evaluation",
    "evaluation": "Review or evaluation",
    "explainer": "Explainer",
    "explanation": "Explainer",
    "checklist": "Checklist or template",
    "template": "Checklist or template",
    "checklist or template": "Checklist or template",
}


class _StructureParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.list_items = 0
        self.table_rows = 0

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag.lower())
        if tag.lower() == "li":
            self.list_items += 1
        elif tag.lower() == "tr":
            self.table_rows += 1


def normalize_content_type(value: str) -> str:
    """Map existing topic-queue intent labels to the approved editorial formats."""
    key = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return ALIASES.get(key, "")


def analyze_content_type(content_type: str, html_content: str) -> Tuple[List[str], Dict[str, int]]:
    """Return format-specific editorial warnings and transparent structure metrics."""
    kind = normalize_content_type(content_type)
    if not kind:
        return [], {"content_type_list_items": 0, "content_type_table_rows": 0}

    parser = _StructureParser()
    try:
        parser.feed(html_content or "")
        parser.close()
    except Exception:
        pass
    tags = parser.tags
    text = re.sub(r"<[^>]+>", " ", html_content or "")
    text = re.sub(r"\s+", " ", text).lower()
    warnings = []

    has_ordered_steps = "ol" in tags or bool(re.search(r"\bstep\s+1\b|\b1[.)]\s", text))
    has_verification = bool(re.search(
        r"\b(verify|check that|confirm|expected result|you should see|test the result|successfully)\b", text
    ))
    has_safe_guidance = bool(re.search(
        r"\b(backup|reversible|before you change|avoid deleting|do not share|stop and contact|contact support)\b", text
    ))
    has_symptoms = bool(re.search(
        r"\b(symptom|error message|error code|not working|does not work|can't|cannot|problem|issue)\b", text
    ))
    has_comparison_criteria = bool(re.search(
        r"\b(price|pricing|cost|features|limits|limitations|privacy|ease of use|support|compatibility|criteria|use case)\b", text
    ))
    has_tradeoffs = bool(re.search(
        r"\b(however|whereas|while|unlike|trade-off|drawback|downside|limitation|not ideal|best suited)\b", text
    ))

    if kind == "Beginner guide":
        if not re.search(r"\b(basics|beginner|start|first step|prerequisite|means|defined as)\b", text):
            warnings.append("Content format advisory (beginner guide): add a clear starting point or define the key idea for a new reader.")
    elif kind == "Step-by-step tutorial":
        if not has_ordered_steps:
            warnings.append("Content format advisory (tutorial): make the instructions a visible numbered sequence or ordered list.")
        if not has_verification:
            warnings.append("Content format advisory (tutorial): explain the expected result and how readers can confirm the task worked.")
    elif kind == "Practical project":
        if not has_ordered_steps:
            warnings.append("Content format advisory (practical project): show the build process in a clear sequence.")
        if not re.search(r"\b(example|sample|finished|deliverable|completed|result)\b", text):
            warnings.append("Content format advisory (practical project): show what the completed deliverable should look like.")
    elif kind == "Formula or calculation tutorial":
        if not has_verification:
            warnings.append("Content format advisory (formula tutorial): explain how to check the calculated result.")
    elif kind == "Troubleshooting guide":
        if not has_symptoms:
            warnings.append("Content format advisory (troubleshooting): describe the symptom or error a reader is trying to fix.")
        if not has_safe_guidance:
            warnings.append("Content format advisory (troubleshooting): include safe, reversible steps and a clear stop/escalation point.")
        if not has_verification:
            warnings.append("Content format advisory (troubleshooting): explain how to verify that the problem is resolved.")
    elif kind == "Comparison":
        if not has_comparison_criteria:
            warnings.append("Content format advisory (comparison): compare options using consistent, named criteria.")
        if not has_tradeoffs:
            warnings.append("Content format advisory (comparison): explain meaningful differences, limitations, or reader-fit trade-offs.")
        if "table" not in tags and not re.search(r"\b(compared with|in contrast|on the other hand|option one|option two)\b", text):
            warnings.append("Content format advisory (comparison): make the comparison between the named options easy to scan.")
    elif kind == "Review or evaluation":
        if not has_comparison_criteria:
            warnings.append("Content format advisory (review): state the criteria used to evaluate the product or service.")
        if not has_tradeoffs:
            warnings.append("Content format advisory (review): include meaningful limitations and who may not find it suitable.")
    elif kind == "Explainer":
        if not re.search(r"\b(works|working|because|process|means|why|how)\b", text):
            warnings.append("Content format advisory (explainer): explain how or why the subject works.")
    elif kind == "Checklist or template":
        if "ul" not in tags and "ol" not in tags:
            warnings.append("Content format advisory (checklist/template): include the actual checklist or usable template, not just a description.")
        elif parser.list_items < 3:
            warnings.append("Content format advisory (checklist/template): include enough concrete items to make the checklist useful.")
        if re.search(r"\b(copy|use|fill in|template below)\b", text) and not ({"pre", "table", "blockquote"} & set(tags)) and parser.list_items < 3:
            warnings.append("Content format advisory (checklist/template): the promised copy-ready artifact is missing.")

    return warnings, {
        "content_type_list_items": parser.list_items,
        "content_type_table_rows": parser.table_rows,
    }
