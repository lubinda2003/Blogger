# The Digital Toolkit — Content Automation Engine

[![Publication](https://img.shields.io/badge/Publication-The_Digital_Toolkit-0284c7?logo=blogger&logoColor=white)](https://digitaltoolkitguide.blogspot.com/)
[![Automation](https://img.shields.io/badge/Automation-GitHub_Actions-2088FF?logo=github-actions&logoColor=white)](.github/workflows/content-pipeline.yml)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)](https://python.org)
[![Publishing](https://img.shields.io/badge/Publishing-Draft_First-success)](https://www.blogger.com/)

An automated research, writing, visual-production, quality-checking, and Blogger draft pipeline for **The Digital Toolkit**.

**Tagline:** *Discover smarter tools. Work better. Do more.*

Website: https://digitaltoolkitguide.blogspot.com/

The pipeline runs through GitHub Actions. It handles topic selection, research, article generation, quality checks, run reports, and Blogger draft creation through the Blogger API.

## Publication scope

The Digital Toolkit is an international English-language publication about practical digital skills, software, AI, productivity, freelancing and digital business. Its readers include students, freelancers, entrepreneurs, creators, remote workers and everyday internet users.

The approved editorial categories are:

1. AI and AI Tools
2. Office Software and Everyday Productivity
3. Spreadsheets, Data and Reporting
4. Graphic Design, Video and Content Creation
5. Freelancing and Remote Work
6. Digital Business, Marketing and E-commerce
7. Digital Learning, Research and Study Skills
8. Digital Foundations, Online Safety and Troubleshooting

The machine-readable category and topic-cluster reference is `config/editorial_taxonomy.json`. The prepared article queue is `data/topics.csv`. Category-specific writing guidance is included in `templates/voice_guide.md`, and the full editorial policy is in `config/editorial_policy.md`.

Articles use plain English, practical instructions, original examples, and honest descriptions of free plans, trials, limitations, permissions, regional availability and pricing. Research is used to understand the subject and check changing details; there is no minimum source count or sentence-by-sentence source matching. The pipeline must not invent testimonials, testing, earnings or product claims.

## How the pipeline works

1. **Configuration and safety checks** — load settings and validate required credentials.
2. **Topic selection** — use the prepared evergreen queue first. When no eligible queued topic remains, autonomous Tavily discovery searches all eight approved editorial categories.
3. **Duplicate reconciliation** — in live mode, check Blogger for an existing post before generating another.
4. **Research** — use focused research as background context and check changing details when needed.
5. **Article generation** — write original explanations, instructions and examples using the configured language-model provider.
6. **Visual assets** — render branded featured covers and supporting illustrations locally, capture genuine product screenshots with Playwright, render Mermaid diagrams, optimize raster images with Sharp, and run an axe-core accessibility scan.
7. **Quality checks** — validate article usefulness, structure, style, safety, optional reference links and duplication.
8. **Blogger action** — create a draft only; public publishing is disabled in configuration validation and the Blogger client.
9. **State and reports** — persist topic outcomes and upload run artifacts and reports.

The normal output is a Blogger draft for manual review. Public publishing is not enabled.

## Category-specific editorial expectations

- **AI:** distinguish model capabilities from app features and plan limits; explain fact-checking and privacy.
- **Office software:** name the application and platform; do not assume Microsoft and Google features are identical.
- **Spreadsheets:** include sample data, exact cell references, formulas, expected calculated outputs and an independent calculation check. Distinguish Excel-specific and Google Sheets features.
- **Design and video:** distinguish genuine screenshots from illustrations; check aspect ratios, export formats and asset licensing.
- **Freelancing:** label hypothetical examples and keep scope, deliverables, timeline and figures consistent; verify payment availability before making country-specific claims.
- **Digital business:** explain platform limits, fees, affiliate disclosures and country-specific payout conditions; avoid income guarantees.
- **Learning and research:** do not invent citations; teach source evaluation and responsible AI use.
- **Digital foundations:** use safe, reversible troubleshooting steps and never ask readers to expose passwords or recovery codes.

Article structure must match the reader's intent. The pipeline should distinguish beginner guides, tutorials, practical projects, formula tutorials, troubleshooting guides, comparisons, reviews, explainers and complete checklists or templates.

## Visual generation and image-cost safety

The visual system is local-first and does not need a paid image-generation API:

- Featured covers are generated from local HTML/CSS/SVG and rendered with Playwright Chromium.
- Supporting illustrations are original SVG artwork, not fake product screenshots.
- Genuine screenshots are captured from real public product or official pages when a tutorial needs them.
- Mermaid diagrams are rendered to SVG.
- Sharp optimizes supported raster images to WebP when the result is smaller.
- axe-core checks article markup; findings are diagnostics, not a claim of full WCAG certification.
- Playwright captures mobile and desktop review previews.

The scheduled workflow sets `IMAGE_PROVIDER=local`, `GEMINI_IMAGE_GENERATION_ENABLED=false`, and `ALLOW_PAID_IMAGE_GENERATION=false`. No paid image-generation fallback is automatic.

## GitHub Actions

Workflow: [Blogger Content Pipeline](.github/workflows/content-pipeline.yml)

- Runs daily and can be started manually.
- Scheduled runs execute live generation, but Blogger delivery remains draft-only.
- Topic queue: `data/topics.csv`; autonomous discovery is used only after the queue is exhausted.
- Runs are serialized to prevent concurrent state collisions.
- Reports and output artifacts are uploaded; the latest scrubbed report is also published to the `run-reports` branch.

Test workflow: [Tests](.github/workflows/tests.yml). Check the Actions tab for the latest result and test count.

## SEO output and Blogger limitations

- Article structured data uses Google's supported `BlogPosting` type.
- Final HTML validation checks that JSON-LD is valid and contains a headline and description.
- SEO title and description lengths are measured and reported as advisories; they do not guarantee rankings or a particular search snippet.
- Blogger API v3 does not expose a per-post Search Description field. The generated description is included in structured data and QA, but the pipeline does not claim it has populated Blogger's separate Search Description setting.
- The live Blogger theme controls page-head metadata and canonical tags. Those must be checked on a public post URL after manual publication.

## Publishing safety

- **Dry run (`dry_run=true`):** runs in test mode and does not create a Blogger post or mutate processed-topic state.
- **Live generation (`dry_run=false`):** performs research and article generation and creates a Blogger **draft**.
- **Public publishing is disabled:** configuration validation rejects `publish_mode=publish`, and the Blogger client refuses any request to create a public post. `CONFIRM_LIVE_PUBLISH` cannot override this protection.

Review each draft in Blogger and publish manually only when you decide it is ready.

## Repository layout

```text
.github/workflows/   GitHub Actions workflows
config/              Example settings, editorial policy and taxonomy
data/                Topic queue and processed-topic state
output/              Generated reports, drafts, logs and visual assets
scripts/             Setup and repository utility scripts
src/                 Pipeline implementation
templates/            Article-generation prompts and voice/layout guides
tests/                Automated tests
```

The active workflow installs dependencies from `config/requirements.txt`.

## Required GitHub Actions secrets

Add secrets under **Repository → Settings → Secrets and variables → Actions**:

| Secret | Purpose |
|---|---|
| `GEMINI_API_KEY` | Gemini article generation |
| `GROQ_API_KEY` | Groq provider/fallback |
| `TAVILY_API_KEY` | Research and autonomous topic discovery |
| `BLOGGER_BLOG_ID` | Target Blogger blog |
| `BLOGGER_CLIENT_ID` | Blogger OAuth client |
| `BLOGGER_CLIENT_SECRET` | Blogger OAuth client secret |
| `BLOGGER_REFRESH_TOKEN` | Blogger API authorization |

Additional Gemini article-generation keys may be configured as separate project credentials. Never place API keys, refresh tokens, passwords or other credentials in source files, commits, issues or workflow logs. Rotate any credential that is accidentally exposed.

## Running the workflow

1. Open the repository's **Actions** tab.
2. Select **Blogger Content Pipeline**.
3. Choose **Run workflow**.
4. Keep **Dry-run mode** enabled for a safe test.
5. Start the run and inspect its job summary and artifacts.

Scheduled runs perform live generation, but Blogger insertion remains draft-only. Public publishing is blocked in application code.

## Local development and tests

Use Python 3.11 or a compatible version supported by the project.

```bash
python -m pip install -r config/requirements.txt
playwright install chromium
python -m src.main --dry-run
python -m unittest discover -s tests -v
```

Some live functions require valid API credentials and network access. Keep tests and dry runs separate from live Blogger draft creation.

## Topic state and run reports

- `data/topics.csv` is the prepared evergreen topic queue.
- `data/processed_topics.json` records processed-topic state and helps prevent duplicate work.
- Live runs can commit updated topic state back to the repository branch.
- Workflow artifacts are retained for 14 days.
- The latest report is available on the [run-reports branch](https://github.com/lubinda2003/Blogger/tree/run-reports).

## Security and operational notes

- The content workflow declares `contents: write` because successful live runs persist topic-state changes.
- Workflow concurrency queues runs rather than cancelling an active run.
- Third-party GitHub Actions are pinned to reviewed commit SHAs.
- Blogger lookup failures stop the pipeline to reduce duplicate posts.
- Local screenshot paths must never be embedded in published HTML; only suitable public HTTPS image URLs should be used.
- The Blogger API OAuth permission may be broader than draft creation; application code restricts its own write operation to drafts.

## License

This repository includes an Apache License 2.0 license. See [LICENSE](LICENSE).
