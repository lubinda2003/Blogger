"""Article writer that invokes Gemini with structured output, retries, and Blogger-compatible HTML."""

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.research import ResearchBrief
from src.topic_discovery import TopicItem

logger = logging.getLogger(__name__)


@dataclass
class ArticleDraft:
    """Represents a generated article ready for QA checks and Blogger publication."""
    topic_id: str
    title: str
    meta_description: str
    labels: List[str]
    html_content: str
    summary: str
    sources_used: List[Dict[str, str]]
    primary_intent: str
    word_count: int
    last_checked_date: str
    is_dry_run_fixture: bool = False
    affiliate_disclosure_required: bool = False
    screenshot_needed: bool = False
    screenshot_url: Optional[str] = None
    screenshot_caption: Optional[str] = None
    screenshot_alt_text: Optional[str] = None
    suggested_slug: Optional[str] = None
    featured_image_brief: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "title": self.title,
            "meta_description": self.meta_description,
            "labels": self.labels,
            "html_content": self.html_content,
            "summary": self.summary,
            "sources_used": self.sources_used,
            "primary_intent": self.primary_intent,
            "word_count": self.word_count,
            "last_checked_date": self.last_checked_date,
            "is_dry_run_fixture": self.is_dry_run_fixture,
            "affiliate_disclosure_required": self.affiliate_disclosure_required,
            "screenshot_needed": self.screenshot_needed,
            "screenshot_url": self.screenshot_url,
            "screenshot_caption": self.screenshot_caption,
            "screenshot_alt_text": self.screenshot_alt_text,
            "suggested_slug": self.suggested_slug,
            "featured_image_brief": self.featured_image_brief,
        }


class ArticleWriter:
    """Orchestrates Gemini API requests with exponential backoff and structured parsing.

    Fails closed in live mode: never substitutes a generic fallback article when an API call fails.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        prompt_template_path: str = "templates/article_prompt.md",
        provider: str = "auto",
        groq_api_key: Optional[str] = None,
        groq_model: str = "llama-3.3-70b-versatile",
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.prompt_template_path = Path(prompt_template_path)
        self.provider = (provider or os.getenv("LLM_PROVIDER", "auto")).strip().lower()
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY")
        self.groq_model = groq_model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    def _load_prompt_template(self) -> str:
        """Load markdown prompt template."""
        if self.prompt_template_path.exists():
            return self.prompt_template_path.read_text(encoding="utf-8")
        return (
            "Write a practical, clear tutorial in plain English using <h2>, <h3>, <p>, <ul> elements. "
            "Return valid JSON with title, meta_description, labels, html_content, sources_used."
        )

    def _render_prompt(self, topic: TopicItem, brief: ResearchBrief) -> str:
        """Fill template placeholders."""
        template = self._load_prompt_template()
        prompt = template.replace("{{TOPIC_TITLE}}", topic.topic)
        prompt = prompt.replace("{{CATEGORY}}", topic.category)
        prompt = prompt.replace("{{TARGET_AUDIENCE}}", topic.target_audience)
        prompt = prompt.replace("{{PRIMARY_INTENT}}", topic.primary_intent)
        prompt = prompt.replace("{{TARGET_URL}}", topic.target_url)
        prompt = prompt.replace("{{REQUIRES_SCREENSHOT}}", str(topic.requires_screenshot))
        prompt = prompt.replace("{{RESEARCH_BRIEF}}", brief.format_for_prompt())
        return prompt

    def _call_gemini_rest(self, prompt: str) -> str:
        """Call Gemini REST API directly with exponential backoff."""
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured in environment or GitHub Secrets.")

        clean_model = self.model_name.replace("models/", "").strip()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={self.api_key}"

        gen_config: Dict[str, Any] = {
            "maxOutputTokens": self.max_tokens,
            "responseMimeType": "application/json",
        }
        if self.temperature is not None and not (clean_model.startswith("gemini-3") or clean_model.startswith("gemini-4")):
            gen_config["temperature"] = self.temperature

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_config,
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        max_retries = 3
        backoff = 2.0
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Calling Gemini ({self.model_name}), attempt {attempt}/{max_retries}...")
                with urllib.request.urlopen(req, timeout=90) as response:
                    res_body = response.read().decode("utf-8")
                    parsed = json.loads(res_body)
                    candidates = parsed.get("candidates", [])
                    if not candidates:
                        prompt_feedback = parsed.get("promptFeedback", {})
                        raise ValueError(f"Gemini returned empty candidate list. PromptFeedback: {prompt_feedback}")

                    candidate_content = candidates[0].get("content", {})
                    parts = candidate_content.get("parts", [])
                    if not parts:
                        finish_reason = candidates[0].get("finishReason", "UNKNOWN")
                        raise ValueError(f"Gemini candidate has no parts (finishReason: {finish_reason}).")

                    # In Gemini 2.0 / 3.x models, thinking parts have "thought": true
                    # The actual answer is in non-thought parts:
                    non_thought_parts = [
                        p.get("text", "")
                        for p in parts
                        if not p.get("thought", False) and "text" in p
                    ]
                    if non_thought_parts:
                        raw_text = "\n".join(non_thought_parts)
                    else:
                        raw_text = "\n".join(p.get("text", "") for p in parts if "text" in p)

                    return raw_text
            except urllib.error.HTTPError as e:
                last_error = e
                status = e.code
                err_text = e.read().decode("utf-8", errors="ignore")
                # Redact API key if it inadvertently appears in error text
                safe_err = re.sub(r"key=[A-Za-z0-9_-]+", "key=[REDACTED]", err_text[:1000])
                logger.warning(f"Gemini API HTTP {status}: {safe_err}")

                if status in (429, 500, 503, 504) and attempt < max_retries:
                    sleep_time = backoff * (2 ** (attempt - 1))
                    logger.info(f"Retrying Gemini call in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)
                else:
                    raise RuntimeError(f"Gemini API request failed with status {status}: {safe_err}") from e
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    time.sleep(backoff * attempt)
                else:
                    raise RuntimeError(f"Gemini connection error: {e}") from e

        raise RuntimeError(f"Gemini failed after {max_retries} attempts: {last_error}")

    def _call_groq_rest(self, prompt: str) -> str:
        """Call Groq REST API directly with Llama 3.3 70B or configured Groq model."""
        if not self.groq_api_key:
            raise ValueError("GROQ_API_KEY is not configured in environment or GitHub Secrets.")

        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": self.groq_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert technical editor and content writer. Return ONLY valid JSON adhering strictly to the requested schema.",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.groq_api_key}",
            },
            method="POST",
        )

        max_retries = 3
        backoff = 2.0
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Calling Groq API ({self.groq_model}), attempt {attempt}/{max_retries}...")
                with urllib.request.urlopen(req, timeout=90) as response:
                    res_body = response.read().decode("utf-8")
                    parsed = json.loads(res_body)
                    choices = parsed.get("choices", [])
                    if not choices:
                        raise ValueError("Groq API returned empty choices list.")
                    raw_text = choices[0]["message"]["content"]
                    return raw_text
            except urllib.error.HTTPError as e:
                last_error = e
                status = e.code
                err_text = e.read().decode("utf-8", errors="ignore")
                safe_err = err_text[:1000]
                logger.warning(f"Groq API HTTP {status}: {safe_err}")

                if status in (429, 500, 503, 504) and attempt < max_retries:
                    sleep_time = backoff * (2 ** (attempt - 1))
                    logger.info(f"Retrying Groq call in {sleep_time:.1f}s...")
                    time.sleep(sleep_time)
                else:
                    raise RuntimeError(f"Groq API request failed with status {status}: {safe_err}") from e
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    time.sleep(backoff * attempt)
                else:
                    raise RuntimeError(f"Groq connection error: {e}") from e

        raise RuntimeError(f"Groq failed after {max_retries} attempts: {last_error}")

    def _validate_schema(self, data: Dict[str, Any]) -> List[str]:
        """Validate Gemini output against required fields and structure."""
        errors = []
        for req_field in ("title", "meta_description", "html_content", "labels", "sources_used"):
            if req_field not in data or not data[req_field]:
                errors.append(f"Missing or empty required field: '{req_field}'")

        if "html_content" in data and len(str(data["html_content"]).strip()) < 200:
            errors.append("Article HTML content is too short (under 200 characters).")

        return errors

    def _generate_dry_run_fixture(self, topic: TopicItem, brief: ResearchBrief) -> Dict[str, Any]:
        """Produce a plain-English, realistic article fixture strictly for dry-run testing.

        Written in natural, human language without AI cliches, false earnings, or generic filler.
        """
        current_month = datetime.now(timezone.utc).strftime("%B %Y")

        if "upwork" in topic.topic.lower() or "zambia" in topic.topic.lower():
            title = "How to Set Up Upwork and Withdraw Earnings to Zambian Banks"
            meta_desc = "A clear guide for Zambian freelancers: how to register on Upwork, verify your NRC, link FNB or Stanbic, and avoid high withdrawal fees."
            labels = ["Freelancing", "Online Work", "Zambia Digital Skills", "Upwork"]
            html_content = f"""<div class="article-body">
<h2>Setting Up Upwork in Zambia: What You Need to Know First</h2>
<p>You can earn money on Upwork from Zambia as a writer, designer, developer, or virtual assistant. Getting started is straightforward, but two steps often cause confusion: verifying your identity and getting your money into a local bank account without losing too much to fees.</p>
<p>This guide explains how to set up your profile, which identity documents work, and how to connect your bank account so you get paid on time.</p>

<div class="callout" style="background:#f8fafc; border-left:4px solid #0284c7; padding:16px; margin:20px 0;">
<p><strong>Quick Summary:</strong></p>
<ul>
<li>You need a clean photo of your Zambian National Registration Card (NRC) or passport to pass identity verification.</li>
<li>Upwork pays directly to local Zambian banks (such as FNB, Stanbic, and Absa), usually taking 2 to 4 business days.</li>
<li>Payoneer is also supported and can save money on exchange rates if you handle several contracts in USD.</li>
<li>Freelance income is taxable under Zambia Revenue Authority (ZRA) rules, so keep your payment receipts.</li>
</ul>
</div>

<h2>Step 1: Create Your Account and Verify Your Identity</h2>
<p>Upwork uses automated identity checks. To avoid delays, make sure your details match your official documents:</p>
<ol>
<li>Go to Upwork.com and select <strong>"I'm a freelancer looking for work"</strong>. Use an email address you check every day.</li>
<li>Type your full legal name exactly as it appears on your NRC or passport. Do not use a nickname.</li>
<li>When prompted for identity verification, upload a clear photo of your NRC (both front and back). Make sure all four corners of the card are visible, the lighting is even, and there is no camera flash reflecting off the laminate.</li>
<li>Complete the camera check on your phone. Position your face in normal daylight against a plain wall.</li>
</ol>
<p>Most verifications finish within a few hours. When approved, a blue verification badge appears on your profile.</p>

<h2>Step 2: Add Your Zambian Bank Account</h2>
<p>After your account is verified, go to <strong>Settings &gt; Get Paid &gt; Add Method</strong> to connect your bank.</p>
<p>Choose <strong>Direct to Local Bank (LXT)</strong>. Have these details ready:</p>
<ul>
<li><strong>Bank SWIFT Code:</strong> Every commercial bank has a specific SWIFT code (for example, FIRNZMLX for FNB Zambia or SBICZMLX for Stanbic Bank Zambia). Ask your branch or check their official website to be certain.</li>
<li><strong>Account Number:</strong> Enter your full local account number without spaces or hyphens. The name on the bank account must match your verified name on Upwork.</li>
<li><strong>Physical Address:</strong> Enter your physical home or neighborhood address. Avoid using only a Post Office box number.</li>
</ul>
<p>Upwork places a security hold for three days on newly added bank details. Once that period ends, you can withdraw your funds on a weekly schedule or on demand.</p>

<h2>Step 3: Comparing Direct Bank Wires and Payoneer</h2>
<p>Both methods work well in Zambia, but they handle fees and currency conversion differently:</p>
<ul>
<li><strong>Direct to Local Bank:</strong> Upwork charges a fixed fee per withdrawal (around $0.99) and converts your dollars to Zambian Kwacha (ZMW) using their partner bank's exchange rate. This is convenient if you want Kwacha deposited directly into your daily account.</li>
<li><strong>Payoneer:</strong> Upwork charges a $2.00 fee to send funds to your Payoneer account. In Payoneer, your money stays in USD until you choose to withdraw it to your bank. If the exchange rate is fluctuating, holding funds in USD gives you more control.</li>
</ul>

<h2>Step 4: Writing Proposals That Get Answers</h2>
<p>When applying for jobs on Upwork, keep your proposals direct and helpful:</p>
<ol>
<li>Read the client's job post carefully. In your first two sentences, address their main problem and explain how you will solve it.</li>
<li>Share one or two links to relevant work you have done previously.</li>
<li>Ask a sensible question about the project. This shows you are thinking about the actual work, not just pasting a template.</li>
<li>Mention that Zambia is on Central Africa Time (CAT / UTC+2). This time zone overlaps well with clients in Europe and the UK, and overlaps partially with US business hours.</li>
</ol>

<h2>Common Questions</h2>
<h3>Can I withdraw my money directly to Airtel Money or MTN Mobile Money?</h3>
<p>Upwork does not send money directly to mobile wallets. The easiest solution is to send your earnings to your bank account, and then transfer from your bank app to your Airtel Money or MTN MoMo wallet.</p>

<h3>How long does a withdrawal take?</h3>
<p>Withdrawals initiated on Wednesday morning usually arrive in Zambian bank accounts by Friday afternoon. Bank holidays can add one extra business day.</p>

<h3>Do I need to pay taxes on freelance money in Zambia?</h3>
<p>Yes. If you live in Zambia, you must declare your freelance earnings to the Zambia Revenue Authority (ZRA). Download your monthly earnings summary from Upwork under the Reports tab so you have a clear record for your tax return.</p>

<hr/>
<p><small><em>Information verified against official Upwork documentation as of {current_month}.</em></small></p>
</div>"""
        else:
            title = f"{topic.topic}: Practical Step-by-Step Guide"
            meta_desc = f"Learn how to use {topic.topic} with this clear, step-by-step tutorial. Includes practical instructions, real examples, and common pitfalls to avoid."
            labels = ["Digital Skills", "Tutorial", "Productivity"]
            html_content = f"""<div class="article-body">
<h2>Getting Started with {topic.topic}</h2>
<p>Using new digital tools should not feel confusing. Many online guides use complicated jargon and skip the practical setup steps that beginners actually need. This guide explains how {topic.topic} works, what you need before you start, and how to use it step by step in your daily work.</p>
<p>Whether you are working as an independent editor, running a small business, or organizing content for a team, having a clear and repeatable process saves time and prevents embarrassing mistakes.</p>

<div class="callout" style="background:#f8fafc; border-left:4px solid #0284c7; padding:16px; margin:20px 0;">
<p><strong>What You Will Learn:</strong></p>
<ul>
<li>How to set up the tool correctly from the start.</li>
<li>A step-by-step walkthrough you can follow at your own pace.</li>
<li>A practical editing prompt template you can copy and adapt.</li>
<li>Realistic advice about costs, limitations, and common mistakes.</li>
<li>Where to find verified help and official documentation.</li>
</ul>
</div>

<h2>What This Tool Does and Who It Helps</h2>
<p>Before spending time learning any new tool, it helps to understand what it is actually good for. {topic.topic} is designed for people who need to handle routine digital tasks faster without sacrificing accuracy.</p>
<p>It helps freelancers, small business owners, and students organize their work, draft clear documents, and avoid repetitive manual steps. However, it does not do everything automatically. You still need to review the results, verify the facts, and make sure the tone fits your audience.</p>

<h2>Step 1: Check Your Prerequisites and Account Setup</h2>
<p>Before following the steps below, make sure you have the basics ready:</p>
<ol>
<li>A stable internet connection on a computer or phone.</li>
<li>An active account on the platform described in the official documentation.</li>
<li>Your login details saved safely in a password manager.</li>
<li>A sample document or text passage of around 300 to 500 words to test your setup.</li>
</ol>

<h2>Step 2: Follow the Step-by-Step Instructions</h2>
<p>Follow these numbered instructions to complete your setup:</p>
<ol>
<li><strong>Open the main workspace:</strong> Sign in to your account and locate the input editor or prompt window. Keep your source material open in a neighboring window.</li>
<li><strong>Set your project instructions:</strong> Specify exactly what kind of editing or processing you need. For example, instruct the tool to focus on sentence clarity and spelling rather than rewriting your original meaning.</li>
<li><strong>Run a small test first:</strong> Process one paragraph before pasting an entire chapter or client document. Check that the output follows your instructions.</li>
<li><strong>Review the output sentence by sentence:</strong> Check that names, dates, technical terms, and numbers are accurate. Never send unverified work to clients or colleagues.</li>
</ol>

<h2>Practical Example: A Reliable Copy Editing Workflow</h2>
<p>Here is a practical three-step routine you can use when editing articles or reports:</p>
<ol>
<li><strong>First Pass (Structure and Clarity):</strong> Ask the tool to identify sentences longer than thirty words or paragraphs that jump between unrelated ideas. Read through the suggestions and shorten long sentences yourself.</li>
<li><strong>Second Pass (Grammar and Punctuation):</strong> Check for punctuation errors, missing commas, and passive phrasing. Keep your voice natural rather than stiff.</li>
<li><strong>Third Pass (Fact Checking):</strong> Check every statistic, date, company name, and link against official documentation. If a claim cannot be confirmed with a primary source, remove it or rephrase it carefully.</li>
</ol>

<h2>Sample Prompts You Can Copy and Adapt</h2>
<p>When working in your prompt editor, use direct, specific instructions rather than vague requests. Here are two sample prompts that produce consistent results:</p>
<pre style="background:#0f172a; color:#f8fafc; padding:16px; border-radius:6px; overflow-x:auto;">
<code># Prompt for Sentence Clarity
"Review the following three paragraphs. Highlight any sentence that exceeds
25 words. Suggest a simpler phrasing using familiar words, but do not change
the underlying meaning or remove technical terms."

# Prompt for Fact Checking
"List every factual claim, product feature, and pricing number mentioned in
the text below. For each item, note whether it needs independent confirmation
against primary documentation."</code>
</pre>
<p>Notice how specifying exact boundaries helps you get concise, actionable feedback without unnecessary conversational filler.</p>

<h2>Common Mistakes and How to Avoid Them</h2>
<p>When working with automated digital tools, people often run into three avoidable problems:</p>
<ul>
<li><strong>Skipping the verification check:</strong> Automated tools can generate convincing mistakes. Always read the output carefully and check quotes or numbers against original sources.</li>
<li><strong>Using overly complicated instructions:</strong> Start with clear, simple prompts. If you ask for ten different adjustments at once, the output is often messy and inconsistent.</li>
<li><strong>Ignoring rate limits or quotas:</strong> Most online services cap how many requests you can make each hour or day. Check your account dashboard so you do not get cut off in the middle of a project.</li>
</ul>

<h2>Frequently Asked Questions</h2>
<h3>Is this tool free to use?</h3>
<p>Many platforms offer a free tier with basic features and lower usage limits. If you need higher volume or commercial features, check the official pricing page before entering any payment details.</p>

<h3>Can I use this on a mobile phone?</h3>
<p>Yes, most modern tools have mobile-responsive websites or mobile apps. However, complex editing tasks and document comparisons are usually much easier on a laptop or desktop screen.</p>

<h3>What should I do if a client asks whether AI tools were used?</h3>
<p>Be transparent. Explain that you use automated tools for spelling checks, structural feedback, and initial proofreading passes, but that all final edits, factual checks, and decisions are reviewed by you personally.</p>

<hr/>
<p><small><em>Information verified against official documentation as of {current_month}.</em></small></p>
</div>"""

        return {
            "title": title,
            "meta_description": meta_desc,
            "labels": labels,
            "primary_intent": topic.primary_intent,
            "html_content": html_content,
            "summary": meta_desc,
            "sources_used": [{"title": s.title, "url": s.url} for s in brief.verified_sources()] or [
                {"title": "Official Platform Documentation", "url": topic.target_url or "https://support.google.com"}
            ],
            "screenshot_spec": {
                "needed": topic.requires_screenshot,
                "target_url": topic.target_url,
                "caption": f"Interface view for {topic.topic}",
                "alt_text": f"Screenshot of the user interface for {topic.topic}",
            },
            "suggested_slug": "how-to-set-up-upwork-zambia-withdrawals" if "upwork" in topic.topic.lower() else re.sub(r"[^a-z0-9]+", "-", topic.topic.lower()).strip("-"),
            "featured_image_brief": {
                "description": f"Editorial header illustration depicting {topic.topic} workflow and clean interface.",
                "alt_text": f"Overview of {topic.topic}",
                "aspect_ratio": "16:9",
            },
            "affiliate_disclosure_required": False,
            "last_checked_date": current_month,
        }

    def _call_llm_provider(self, prompt: str) -> str:
        """Route prompt to configured LLM provider (Gemini or Groq) with intelligent failover."""
        prov = self.provider
        if prov == "groq" or (prov == "auto" and not self.api_key and self.groq_api_key):
            logger.info(f"Generating article via Groq LLM provider ({self.groq_model})...")
            return self._call_groq_rest(prompt)
        elif prov == "gemini" or (prov == "auto" and self.api_key):
            logger.info(f"Generating article via Gemini LLM provider ({self.model_name})...")
            try:
                return self._call_gemini_rest(prompt)
            except Exception as e:
                if self.groq_api_key:
                    logger.warning(f"Gemini API call failed ({e}). Falling back to Groq provider ({self.groq_model})...")
                    return self._call_groq_rest(prompt)
                raise
        elif self.groq_api_key:
            logger.info(f"Generating article via Groq LLM provider ({self.groq_model})...")
            return self._call_groq_rest(prompt)
        else:
            raise ValueError("Neither GEMINI_API_KEY nor GROQ_API_KEY is configured in environment or GitHub Secrets.")

    def _extract_json_from_response(self, raw_text: str) -> Dict[str, Any]:
        """Extract and parse JSON object from LLM response reliably.

        Handles direct JSON, markdown code fence blocks (```json ... ```), and embedded JSON objects.
        """
        text = (raw_text or "").strip()
        if not text:
            raise ValueError("Empty response received from LLM.")

        # 1. Direct JSON parse
        try:
            return json.loads(text)
        except Exception:
            pass

        # 2. Extract from markdown code fences
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except Exception:
                pass

        # 3. Extract outermost JSON object {...}
        obj_match = re.search(r"(\{[\s\S]*\})", text)
        if obj_match:
            try:
                return json.loads(obj_match.group(1).strip())
            except Exception:
                pass

        # Final attempt to give descriptive standard JSON error
        return json.loads(text)

    def write_article(self, topic: TopicItem, brief: ResearchBrief, dry_run: bool = False) -> ArticleDraft:
        """Generate structured article draft using Gemini or deterministic dry-run fixture.

        Fails closed in live mode: never substitutes a dry-run fixture during a live run.
        """
        if dry_run:
            logger.info("Using dry-run article generation fixture (clearly marked as test data).")
            parsed = self._generate_dry_run_fixture(topic, brief)
            is_fixture = True
        else:
            # LIVE MODE: Call configured LLM API provider and parse structured JSON
            prompt = self._render_prompt(topic, brief)
            raw_json_str = self._call_llm_provider(prompt)

            try:
                parsed = self._extract_json_from_response(raw_json_str)
            except Exception as e:
                # In live mode, retry with repair prompt once
                logger.warning(f"LLM returned invalid JSON ({e}). Retrying with repair prompt...")
                repair_prompt = f"The following text was supposed to be valid JSON matching the schema, but failed to parse: {raw_json_str[:400]}. Return ONLY valid JSON adhering to the schema."
                repaired_raw = self._call_llm_provider(repair_prompt)
                try:
                    parsed = self._extract_json_from_response(repaired_raw)
                except Exception as e2:
                    raise RuntimeError(f"LLM response could not be parsed as JSON: {e2}") from e2

            # Schema validation
            schema_errors = self._validate_schema(parsed)
            if schema_errors:
                raise RuntimeError(f"LLM output failed schema validation: {'; '.join(schema_errors)}")

            is_fixture = False

        html_body = parsed.get("html_content", "")
        # Compute word count
        words = re.findall(r"\b\w+\b", re.sub(r"<[^>]+>", " ", html_body))
        word_count = len(words)

        screenshot_spec = parsed.get("screenshot_spec", {})
        needed_screenshot = screenshot_spec.get("needed", topic.requires_screenshot)

        # Suggested slug with safe fallback
        raw_slug = parsed.get("suggested_slug")
        if not raw_slug:
            raw_slug = re.sub(r"[^a-z0-9]+", "-", parsed.get("title", topic.topic).lower()).strip("-")
        slug = re.sub(r"[^a-z0-9\-]", "", raw_slug.lower())

        # Featured image brief: specification for editorial asset creation (no fake file claim)
        raw_image_brief = parsed.get("featured_image_brief") or {}
        image_desc = (
            raw_image_brief.get("description")
            or raw_image_brief.get("concept")
            or f"Clean modern editorial header illustration representing {parsed.get('title', topic.topic)} workflow."
        )
        image_alt = raw_image_brief.get("alt_text") or f"Visual guide to {parsed.get('title', topic.topic)}"
        image_brief = {
            "description": image_desc,
            "alt_text": image_alt,
            "aspect_ratio": "16:9",
            "note": "Editorial design specification only; does not claim an image is automatically generated or hosted.",
        }


        return ArticleDraft(
            topic_id=topic.id,
            title=parsed.get("title", topic.topic),
            meta_description=parsed.get("meta_description", ""),
            labels=parsed.get("labels", [topic.category, "Digital Skills"]),
            html_content=html_body,
            summary=parsed.get("summary", ""),
            sources_used=parsed.get("sources_used", []),
            primary_intent=parsed.get("primary_intent", topic.primary_intent),
            word_count=word_count,
            last_checked_date=parsed.get("last_checked_date", datetime.now(timezone.utc).strftime("%B %Y")),
            is_dry_run_fixture=is_fixture,
            affiliate_disclosure_required=parsed.get("affiliate_disclosure_required", False),
            screenshot_needed=needed_screenshot,
            screenshot_url=screenshot_spec.get("target_url", topic.target_url),
            screenshot_caption=screenshot_spec.get("caption", f"Screenshot for {topic.topic}"),
            screenshot_alt_text=screenshot_spec.get("alt_text", f"Official interface for {topic.topic}"),
            suggested_slug=slug,
            featured_image_brief=image_brief,
        )
