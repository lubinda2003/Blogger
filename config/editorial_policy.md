# Editorial and Plain-English Content Quality Policy
# The Digital Toolkit — https://digitaltoolkitguide.blogspot.com/
# Tagline: "Discover smarter tools. Work better. Do more."

This editorial policy governs all articles drafted by the **The Digital Toolkit Content Automation Engine**. It ensures that every article is genuinely useful, verified, clearly written, and strictly compliant with Google Search Central guidance against scaled content abuse.

---

## 1. Publication Mission & Audience

**The Digital Toolkit** is an educational publication covering digital tools, software, artificial intelligence, and practical technology solutions.

- **Primary Audience:** International English-speaking audience (students, freelancers, entrepreneurs, small-business owners, content creators, digital marketers, remote workers).
- **Tone:** Accessible to beginners while remaining practical and useful for experienced technology users.
- **Scope:** Broad international utility. Country-specific context (such as regional payment gateways or currency considerations) may be included when genuinely useful, but must not dominate the publication.

---

## 2. Four Main Content Categories

1. **Artificial Intelligence and AI Tools (~35%):** AI research tools, writing assistants, image/video generators, productivity workflows, AI for business, model comparisons, and hands-on tutorials.
2. **Software and Productivity (~30%):** Project management software, note-taking apps, writing and design tools, collaboration platforms, browser extensions, time management systems.
3. **Digital Business Tools (~20%):** Website builders, e-commerce platforms, email marketing software, social media management, payment processing, remote contracting platforms.
4. **Tutorials and Practical Solutions (~15%):** Numbered walkthroughs, software configuration guides, common troubleshooting solutions, beginner productivity playbooks.

---

## 3. Writing Style: Clear, Natural, Human Language

- **Write like a helpful human:** Use ordinary words, short-to-medium sentences, and a calm, direct voice.
- **Explain one idea at a time:** Give practical examples and step-by-step instructions. If a technical term is necessary, explain it the first time it appears.
- **Banned AI clichés and inflated phrasing:** The automated quality gate rejects articles containing empty transition phrases such as:
  - *"In today's fast-paced digital world..."*
  - *"In the ever-evolving landscape of..."*
  - *"Unlock the power of..."*
  - *"Revolutionize the way you..."*
  - *"Delve into / dive into..."*
  - *"Let's embark on a journey..."*
  - *"Game-changer / groundbreaking / cutting-edge"*
  - *"Whether you're a beginner or an expert..."*
  - *"Look no further..."*
  - *"In conclusion..."*
- **No fabricated experiences or fake reviews:** Never invent client quotes, fake case studies, or unverified earnings claims. If a tool was researched rather than personally tested, describe it accurately as documentation-based research.

---

## 4. Fact-Checking, Pricing & Source Verification

- Every factual article or comparison must cite **at least two verified sources**.
- Official documentation, official pricing pages, and product help centers must be prioritized.
- **Accurate Free Tiers:** When discussing free tools, state what is actually free vs. what requires a paid subscription. Never describe a 14-day free trial as a "permanently free plan".
- All volatile information (fees, pricing, limits) must include an explicit **"Information verified as of [Month Year]"** note.

---

## 5. Featured Image Briefs

Every article output must include a clear, professional **featured image brief** specifying:
- Concept and mood fitting The Digital Toolkit's modern, technology-oriented identity.
- Clean composition suggestions (e.g. software dashboard, organized digital workspace, modern laptop mockup).
- Descriptive accessibility alt text.

---

## 6. Real Screenshots & Image Policy

- Screenshots must be captured directly from live public web pages using Playwright Chromium.
- **Never embed runner-local file paths:** Article HTML must never contain paths like `output/screenshots/...` or `/app/...`.
- If a reliable HTTPS image host is configured, the public HTTPS URL is embedded. If no image host is configured, the screenshot is saved locally for review and omitted from HTML to prevent broken image icons for readers.

---

## 7. Draft-First Safety

- All posts are created as **Blogger Drafts** (`isDraft=true`) by default on `https://digitaltoolkitguide.blogspot.com/`.
- Public posting requires deliberate manual enabling.
- Retries and pipeline restarts are idempotent: existing posts are checked before generation and before insertion to prevent duplicate posts.
