# The Digital Toolkit — Content Automation Engine

[![Publication](https://img.shields.io/badge/Publication-The_Digital_Toolkit-0284c7?logo=blogger&logoColor=white)](https://digitaltoolkitguide.blogspot.com/)
[![Automation](https://img.shields.io/badge/Automation-GitHub_Actions-2088FF?logo=github-actions&logoColor=white)](.github/workflows/content-pipeline.yml)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Publishing](https://img.shields.io/badge/Publishing-Draft_First-success)](https://www.blogger.com/)

An automated research, writing, quality-checking, and Blogger publishing pipeline for **The Digital Toolkit**.

**Tagline:** *Discover smarter tools. Work better. Do more.*

Website: https://digitaltoolkitguide.blogspot.com/

The entire content pipeline runs through GitHub Actions. GitHub Actions handles research, article generation, quality checks, run reports, and Blogger draft creation through the Blogger API.

## Publication scope

The Digital Toolkit is an international English-language publication for students, freelancers, entrepreneurs, small-business owners, creators, digital marketers, and remote workers.

| Editorial category | Target share |
|---|---:|
| Artificial Intelligence and AI Tools | 35% |
| Software and Productivity | 30% |
| Digital Business Tools | 20% |
| Tutorials and Practical Solutions | 15% |

Articles should use plain English, practical examples, accurate sourcing, and honest descriptions of free plans, trials, limitations, and pricing. The pipeline must not invent testimonials, tests, earnings, or unsupported claims.

## How the pipeline works

1. **Configuration and safety checks** — load settings and validate required credentials.
2. **Autonomous topic discovery** — Tavily searches across the four editorial pillars, identifies fresh search-result opportunities, filters previously processed topics, and selects a candidate. The CSV is optional for manual topic selection, not a required queue.
3. **Duplicate reconciliation** — in live mode, check Blogger for an existing post before generating another.
4. **Research** — discover and verify sources; insufficient evidence stops the run.
5. **Article generation** — generate structured article content using the configured language-model provider.
6. **Visual assets** — capture required software screenshots and prepare a featured image when enabled.
7. **Quality checks** — validate article length, sources, style, safety, and duplication.
8. **Blogger action** — create a draft by default; public publishing requires explicit confirmation.
9. **State and reports** — persist topic outcomes and upload run artifacts/reports.

The pipeline is designed to fail closed when important checks fail rather than publish an article that has not passed them.

## GitHub Actions

### Content pipeline

Workflow: [Blogger Content Pipeline](.github/workflows/content-pipeline.yml)

- Trigger: manual `workflow_dispatch`. The schedule is currently commented out.
- Default dry-run setting: **true**.
- Default publishing mode: **draft**.
- Provider choice: `auto` (Gemini with Groq failover), `groq`, or `gemini`.
- Optional input: a specific topic ID from the optional `data/topics.csv` editorial ideas file. Leave it empty for autonomous Tavily discovery.
- Runs are serialized so concurrent executions do not race over topic state.
- Reports and output artifacts are uploaded; the latest scrubbed report is also published to the `run-reports` branch.

### Test workflow

Workflow: [Tests](.github/workflows/tests.yml)

The test workflow runs through its configured GitHub Actions events. Check the Actions tab for the latest result and current test count rather than relying on a hard-coded count in this README.

## Publishing safety

There are two separate controls:

- **Dry run (`dry_run=true`)**: runs the pipeline in test mode and does not create or publish a Blogger post or mutate processed-topic state.
- **Live draft (`dry_run=false`, `publish_mode=draft`)**: performs the live pipeline and creates a Blogger draft for review. It is not publicly published.
- **Live public publishing**: requires `dry_run=false`, `publish_mode=publish`, and `confirm_live_publish=true`. Use this only when you deliberately intend to publish publicly.

The workflow defaults to dry-run and draft mode. Review every generated draft in Blogger before enabling public publishing.

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

The Gemini/Groq provider and model can also be configured with repository variables or the supported workflow inputs. The workflow has defaults for the model and provider.

Do not place API keys, refresh tokens, passwords, or other credentials in source files, commits, issues, or workflow logs. Rotate any credential that is accidentally exposed.

## Running the workflow

1. Open the repository's **Actions** tab.
2. Select **Blogger Content Pipeline**.
3. Choose **Run workflow**.
4. Keep **Dry-run mode** enabled for a safe test.
5. Leave publishing mode set to **draft**.
6. Start the run and inspect its job summary and artifacts.

For a live draft, deliberately turn dry-run off while keeping publishing mode set to `draft`. Do not select public publishing unless you also intentionally confirm it.

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
- The scheduled trigger is disabled in the workflow. It should only be enabled after end-to-end testing and an explicit decision about the publishing schedule.

## License

This repository includes an Apache License 2.0 license. See [LICENSE](LICENSE).
