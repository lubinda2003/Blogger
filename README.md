# The Digital Toolkit — Content Automation Engine

[![Publication](https://img.shields.io/badge/Publication-The_Digital_Toolkit-0284c7?logo=blogger&logoColor=white)](https://digitaltoolkitguide.blogspot.com/)
[![Automation](https://img.shields.io/badge/Automation-GitHub_Actions-2088FF?logo=github-actions&logoColor=white)](.github/workflows/content-pipeline.yml)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Publishing](https://img.shields.io/badge/Publishing-Draft_First-success)](https://www.blogger.com/)

An automated research, writing, visual-production, quality-checking, and Blogger draft pipeline for **The Digital Toolkit**.

**Tagline:** *Discover smarter tools. Work better. Do more.*

Website: https://digitaltoolkitguide.blogspot.com/

The entire content pipeline runs through GitHub Actions. GitHub Actions handles research, article generation, quality checks, run reports, and Blogger draft creation through the Blogger API.

## Publication scope

The Digital Toolkit is an international English-language publication about practical digital skills and productivity for students, freelancers, and everyday internet users.

| Editorial category | Target share |
|---|---:|
| Productivity | 25% |
| Student Success | 25% |
| Freelancing | 25% |
| Digital Skills | 25% |

Articles should use plain English, practical examples, accurate sourcing, and honest descriptions of free plans, trials, limitations, and pricing. The pipeline must not invent testimonials, tests, earnings, or unsupported claims.

## How the pipeline works

1. **Configuration and safety checks** — load settings and validate required credentials.
2. **Autonomous topic discovery** — Tavily searches across the four practical digital-skills categories, identifies fresh search-result opportunities, filters previously processed topics, and selects a candidate. The CSV is optional for manual topic selection, not a required queue.
3. **Duplicate reconciliation** — in live mode, check Blogger for an existing post before generating another.
4. **Research** — discover and verify sources; insufficient evidence stops the run.
5. **Article generation** — generate structured article content using the configured language-model provider.
6. **Visual assets** — render branded featured covers and supporting illustrations locally, capture genuine product screenshots with Playwright, render Mermaid diagrams, optimize raster images with Sharp, and run an axe-core accessibility scan.
7. **Quality checks** — validate article length, sources, style, safety, and duplication.
8. **Blogger action** — create a draft only; public publishing is disabled in configuration validation and the Blogger client.
9. **State and reports** — persist topic outcomes and upload run artifacts/reports.

The pipeline is designed to fail closed when important checks fail rather than publish an article that has not passed them. The normal output is a Blogger draft for manual review.

## Visual generation and image-cost safety

The visual system is local-first and does not need a paid image-generation API:

- **Featured covers:** generated from local HTML/CSS/SVG and rendered with the existing Playwright Chromium installation.
- **Supporting illustrations:** generated as original SVG artwork from the article's visual plan. These are explanatory illustrations, not fake product screenshots.
- **Genuine screenshots:** captured from the real public product or official page with Playwright when a tutorial needs them.
- **Diagrams:** authored Mermaid blocks are rendered to SVG.
- **Image optimization:** Sharp converts supported raster images to WebP when the result is smaller.
- **Accessibility:** axe-core checks the final article markup; findings are reported as diagnostics and do not pretend to certify full WCAG compliance.
- **Review previews:** Playwright captures mobile and desktop previews for the run artifact.

**Image generation is free/local by default.** The scheduled workflow sets `IMAGE_PROVIDER=local`, `GEMINI_IMAGE_GENERATION_ENABLED=false`, and `ALLOW_PAID_IMAGE_GENERATION=false`. The pipeline does not send the three article-writing Gemini keys to an image model.

A future paid Gemini image integration would require all three explicit opt-ins (`IMAGE_PROVIDER=gemini`, `GEMINI_IMAGE_GENERATION_ENABLED=true`, and `ALLOW_PAID_IMAGE_GENERATION=true`) plus a separate `GEMINI_IMAGE_API_KEY`. Do not configure that key or enable those switches while all available Gemini projects are on the free tier. No paid image-generation fallback is automatic.

## GitHub Actions

### Content pipeline

Workflow: [Blogger Content Pipeline](.github/workflows/content-pipeline.yml)

- Triggers: daily schedule at 10:00 AM Zambia time (08:00 UTC) and manual `workflow_dispatch`.
- Scheduled runs execute the real content-generation pipeline (`DRY_RUN=false`).
- Blogger delivery is permanently restricted to **drafts** in application code; public publishing is disabled.
- Provider choice: `auto` (Gemini with Groq failover), `groq`, or `gemini`.
- Optional input: a specific topic ID from the optional `data/topics.csv` editorial ideas file. Leave it empty for autonomous Tavily discovery.
- Runs are serialized so concurrent executions do not race over topic state.
- Reports and output artifacts are uploaded; the latest scrubbed report is also published to the `run-reports` branch.

### Test workflow

Workflow: [Tests](.github/workflows/tests.yml)

The test workflow runs through its configured GitHub Actions events. Check the Actions tab for the latest result and current test count rather than relying on a hard-coded count in this README.

## SEO output and Blogger limitations

- Article structured data uses Google's supported `BlogPosting` type, with the article headline, description, publisher, author identity, language, and a verified public cover image when available.
- The final HTML validator checks that the JSON-LD is valid and contains a `BlogPosting` headline and description before Blogger draft insertion.
- SEO title and description lengths are measured and reported as advisories; they do not guarantee rankings or a particular search snippet.
- **Important Blogger API limitation:** Blogger API v3's documented post resource does not expose a per-post Search Description field. The generated description is therefore included in structured data and QA, but the pipeline does not claim it has populated Blogger's separate Search Description setting. Google may also choose a snippet from visible page text.
- The live Blogger theme controls page-head metadata and canonical tags. Those must be checked on a public post URL after manual publication; the pipeline's article-body validator cannot inspect the theme's final page head.

## Publishing safety

The pipeline has two execution modes, but only one Blogger delivery mode:

- **Dry run (`dry_run=true`)**: runs in test mode and does not create a Blogger post or mutate processed-topic state.
- **Live generation (`dry_run=false`)**: performs research and article generation and creates a Blogger **draft** for review.
- **Public publishing is disabled**: configuration validation rejects `publish_mode=publish`, and the Blogger client refuses any request to create a public post. `CONFIRM_LIVE_PUBLISH` cannot override this protection.

Review each draft in Blogger and publish manually from the Blogger dashboard only when you decide it is ready.

## Repository layout

```text
.github/workflows/   GitHub Actions workflows
config/              Example settings and editorial policy
data/                Topic queue and processed-topic state
output/              Generated reports, drafts, logs, and visual assets
scripts/             Setup and repository utility scripts
src/                 Pipeline implementation
templates/            Article-generation prompt templates
tests/                Automated tests
README.md             Project documentation
requirements.txt      Root-level dependency file, if used by local tooling
server.ts             Developer console server
```

The active workflow installs dependencies from `config/requirements.txt`.

## Required GitHub Actions secrets

Add secrets under **Repository → Settings → Secrets and variables → Actions**. The workflow passes these credentials to the pipeline:

| Secret | Purpose |
|---|---|
| `GEMINI_API_KEY` | Gemini article generation |
| `GROQ_API_KEY` | Groq fallback/provider |
| `TAVILY_API_KEY` | Research discovery |
| `BLOGGER_BLOG_ID` | Target Blogger blog |
| `BLOGGER_CLIENT_ID` | Blogger OAuth client |
| `BLOGGER_CLIENT_SECRET` | Blogger OAuth client secret |
| `BLOGGER_REFRESH_TOKEN` | Blogger API authorization |

The Gemini/Groq provider and model can also be configured with repository variables or the supported workflow inputs. The workflow has defaults for the model and provider. The three Gemini article-generation keys can be supplied from separate Google projects as fallback credentials; they are never passed to image generation.

Do not place API keys, refresh tokens, passwords, or other credentials in source files, commits, issues, or workflow logs. Rotate any credential that is accidentally exposed.

## Running the workflow

1. Open the repository's **Actions** tab.
2. Select **Blogger Content Pipeline**.
3. Choose **Run workflow**.
4. Keep **Dry-run mode** enabled for a safe test.
5. Start the run and inspect its job summary and artifacts.

The scheduled workflow runs live generation automatically, but Blogger insertion remains draft-only. Public publishing is blocked in application code; there is no public-publishing workflow option.

## Local development and tests

Use Python 3.11 or a compatible version supported by the project.

Install the active pipeline dependencies:

```bash
python -m pip install -r config/requirements.txt
playwright install chromium
```

Run a dry-run pipeline:

```bash
python -m src.main --dry-run
```

Run the automated tests:

```bash
python -m unittest discover tests -v
```

Some live pipeline functions require valid API credentials and network access. Keep tests and dry runs separate from live Blogger publishing.

## Topic state and run reports

- `data/topics.csv` is an optional manual/editorial seed list. Normal runs discover topics through Tavily and do not depend on this file.
- `data/processed_topics.json` records processed-topic state and helps prevent duplicate work.
- Live runs can commit updated topic state back to the branch.
- The workflow uploads execution artifacts with a 14-day retention period.
- The latest report is made available on the [run-reports branch](https://github.com/lubinda2003/Blogger/tree/run-reports).

## Security and operational notes

- The content workflow declares `contents: write` because successful live runs persist topic-state changes.
- Workflow concurrency is configured to queue runs rather than cancel an active run.
- Third-party GitHub Actions are pinned to reviewed commit SHAs in the content workflow.
- Blogger lookup failures and insufficient research evidence stop the pipeline to reduce duplicate or unsupported posts.
- Local screenshot paths are not intended to be embedded in published HTML; only suitable public HTTPS image URLs should be used.
- The content workflow runs daily at 10:00 AM Zambia time and can also be started manually.
- The Blogger API OAuth permission may be broader than draft creation; application code restricts its own write operation to drafts.

## License

This repository includes an Apache License 2.0 license. See [LICENSE](LICENSE).
