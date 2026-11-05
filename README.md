# The Digital Toolkit — Content Automation Engine

[![The Digital Toolkit](https://img.shields.io/badge/Publication-The_Digital_Toolkit-0284c7?logo=blogger&logoColor=white)](https://digitaltoolkitguide.blogspot.com/)
[![Blogger Content Pipeline](https://img.shields.io/badge/Workflow-GitHub_Actions-2088FF?logo=github-actions&logoColor=white)](.github/workflows/content-pipeline.yml)
[![State Persistence](https://img.shields.io/badge/State_Persistence-Repository_JSON-0284c7?logo=git&logoColor=white)](data/processed_topics.json)
[![Python 3.11](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Tests: 45 Passing](https://img.shields.io/badge/Tests-45_Passing-emerald)](tests/)
[![Safety: Draft First](https://img.shields.io/badge/Safety-Draft_Default-success)](config/editorial_policy.md)
[![Style: Plain English](https://img.shields.io/badge/Style-Plain_English-emerald)](config/editorial_policy.md)

An automated content production engine built for **The Digital Toolkit** ([digitaltoolkitguide.blogspot.com](https://digitaltoolkitguide.blogspot.com/)).

**Tagline:** *Discover smarter tools. Work better. Do more.*

The purpose of the engine is to research, create, optimize, and prepare useful educational articles for The Digital Toolkit with minimal manual work. The system operates self-contained through **GitHub Actions**, with repository-native state persistence via **data/processed_topics.json** providing safe, serialized deduplication across workflow runs without requiring external databases or Cloudflare services.

### Core Audience & Scope
The Digital Toolkit is an educational publication covering digital tools, software, artificial intelligence, and practical technology solutions for an **international English-speaking audience** (students, freelancers, entrepreneurs, small-business owners, content creators, digital marketers, and remote workers).

### Main Content Categories
- **A. Artificial Intelligence and AI Tools (~35%):** Useful AI tools, free tools, writing assistants, image/video generators, productivity & research assistants, and practical tutorials.
- **B. Software and Productivity (~30%):** Project management, note-taking, design tools, browser extensions, collaboration platforms, and software comparisons.
- **C. Digital Business Tools (~20%):** Online business platforms, website builders, e-commerce, invoicing, email marketing, and business automation.
- **D. Tutorials and Practical Solutions (~15%):** Step-by-step guides, beginner tutorials, troubleshooting common digital problems, and software walkthroughs.

---

## 1. System Architecture & Fail-Closed Pipeline Flow

```
+-----------------------------------------------------------------------------------+
|                            Scheduled GitHub Actions Run                            |
|                 (or manual workflow_dispatch with serialized queue)               |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
                      +--------------------------------------+
                      |      Stage 1: Validation             |
                      |  Validate 5 secrets & safe config    |
                      +--------------------------------------+
                                         |
                                         v
                      +--------------------------------------+
                      |      Stage 2: Topic Selection        |
                      |  Verify repository state file write  |
                      |  Deduplicate via SHA-256 fingerprint |
                      +--------------------------------------+
                                         |
                                         v
                      +--------------------------------------+
                      |      Pre-Check Reconciliation        |
                      |  Query Blogger API for existing post |
                      |  Fails closed if search errors out   |
                      +--------------------------------------+
                                         |
                                         v
                      +--------------------------------------+
                      |      Stage 3: Live Research          |
                      |  Live HTTP HEAD/GET verification     |
                      |  Extract title, excerpt & claims     |
                      |  Fails closed if < 2 sources verified|
                      +--------------------------------------+
                                         |
                                         v
                      +--------------------------------------+
                      |      Stage 4: Article Generation     |
                      |  Gemini structured schema invocation |
                      |  Plain-English mandate (no cliches)  |
                      |  Fails closed on malformed JSON      |
                      +--------------------------------------+
                                         |
                                         v
                      +--------------------------------------+
                      |      Stage 5: Screenshot Capture     |
                      |  Playwright Chromium capture         |
                      |  Validates PNG header, size (>5KB)   |
                      |  Uploads to HTTPS host or omits image|
                      |  (Never leaks runner-local paths)    |
                      +--------------------------------------+
                                         |
                                         v
                      +--------------------------------------+
                      |      Stage 6: Hard Quality Gate      |
                      |  Fails closed on:                    |
                      |  - Generic AI filler / cliches       |
                      |  - Word count < 800 words            |
                      |  - Missing / unverified citations    |
                      |  - Banned financial guarantees       |
                      |  - Runner-local path in HTML         |
                      |  - Duplicate title or text hash      |
                      +--------------------------------------+
                                         |
                                         v
                      +--------------------------------------+
                      |      Stage 7: Blogger API v3         |
                      |  OAuth2 loopback token exchange      |
                      |  Create Draft (`isDraft=true`)       |
                      +--------------------------------------+
                                         |
                                         v
                      +--------------------------------------+
                      |      Stage 8: State Persistence      |
                      |  Atomic save to processed_topics.json|
                      |  Commit & push changes via workflow  |
                      |  Emit report.json & job summary      |
                      +--------------------------------------+
```

---

## 2. Directory Structure

```text
blogger-content-engine/
├── .github/
│   └── workflows/
│       ├── content-pipeline.yml   # Pinned Actions SHAs, serialized queue & state commit
│       └── tests.yml              # CI test runner (automated unit tests)
├── config/
│   ├── settings.example.yaml      # Pipeline, model, and quality thresholds
│   └── editorial_policy.md        # Plain-English mandate & anti-spam guidelines
├── data/
│   ├── topics.csv                 # Queue of eligible candidate topics (4 categories)
│   └── processed_topics.json      # Persistent history committed across workflow runs
├── output/
│   ├── report.json                # Structured execution results (generated per run)
│   ├── summary.md                 # Markdown summary for GitHub Step Summary
│   └── screenshots/               # Playwright captures
├── scripts/
│   ├── bundle_repo_zip.py         # Packaging utility for distribution
│   └── get_blogger_refresh_token.py # Supported OAuth2 loopback token generator
├── src/
│   ├── __init__.py
│   ├── article_writer.py          # Gemini API client with fail-closed schema & slugs
│   ├── blogger_client.py          # Blogger API v3 & fail-closed reconciliation
│   ├── config.py                  # Env parsing & credential redaction
│   ├── main.py                    # Master CLI pipeline orchestrator
│   ├── quality_checks.py          # Hard quality gates & plain-English style checks
│   ├── report.py                  # report.json & GitHub step summary emitter
│   ├── research.py                # Live HTTP source verification & claim mapping
│   ├── screenshot_capture.py      # Playwright browser capture & HTTPS hosting
│   ├── seo_metadata.py            # Label normalization & local path defense
│   ├── state_store.py             # Atomic file swap, fail-closed check & fingerprinting
│   └── topic_discovery.py         # CSV topic intake and priority selection
├── templates/
│   └── article_prompt.md          # Master prompt template for Gemini
├── tests/
│   ├── test_blogger_payload.py    # Blogger v3 schema & safe reconciliation
│   ├── test_deduplication.py      # Multi-run state persistence & fingerprinting
│   ├── test_quality_checks.py     # Quality gate, plain English & local path leak tests
│   ├── test_research_and_sources.py # Live source verification & claim mapping
│   ├── test_security_and_console.py # Safe process spawning & traversal defense
│   ├── test_state_persistence.py  # Repository state write check & atomic swap
│   └── test_style_and_writer.py   # Fail-closed Gemini JSON & AI cliché checks
├── worker/                        # (Reference only - decoupled from active pipeline)
│   ├── index.ts
│   ├── schema.sql
│   └── wrangler.toml
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
└── server.ts                      # Secure developer console API & Vite server
```

---

## 3. Mandatory Writing Style Rules

Every generated article must sound like a clear, helpful human wrote it:
1. **Plain, familiar words:** Use ordinary language and short-to-medium sentences.
2. **Explain one idea at a time:** Provide step-by-step instructions and practical examples.
3. **Banned AI clichés:** The automated quality gate actively rejects generic filler such as:
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
4. **No invented stories or fake earnings:** Never invent personal testimonials, fake earnings numbers, or fake tests.
5. **Realistic regional advice:** Discuss Zambian payment routes (FNB, Stanbic, Absa, Payoneer, Mobile Money) and tax reporting (ZRA) based on verified guidelines.

---

## 4. Setup Guide (Zero to Deployed)

### Step 1: Push Repository to GitHub
Create a new **Private** GitHub repository (e.g. `blogger-content-engine`) and push the codebase:
```bash
git init
git add .
git commit -m "Initial commit of Blogger Content Automation Engine"
git remote add origin https://github.com/YOUR_USERNAME/blogger-content-engine.git
git branch -M main
git push -u origin main
```

### Step 2: Configure GitHub Actions Workflow Permissions
To allow GitHub Actions to commit and push updated topic records in `data/processed_topics.json`:
1. In your GitHub repository, open **Settings**.
2. Click **Actions** → **General** in the left sidebar.
3. Scroll down to **Workflow permissions**.
4. Select **Read and write permissions**.
5. Check **Allow GitHub Actions to create and approve pull requests**.
6. Click **Save**.

### Step 3: Obtain Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Click **Get API key** and create a key in your Google Cloud project.
3. Save this value for GitHub Secret `GEMINI_API_KEY`.

### Step 4: Configure Google Cloud & Blogger API v3
1. Navigate to the [Google Cloud Console](https://console.cloud.google.com/).
2. Enable **Blogger API v3**:
   - Go to **APIs & Services > Library** and search for `Blogger API v3`. Click **Enable**.
3. Configure the **OAuth Consent Screen**:
   - User Type: **External**.
   - Under Scopes, add: `https://www.googleapis.com/auth/blogger`.
   - Add your Google account email under **Test Users**.
4. Create OAuth Client Credentials:
   - Go to **APIs & Services > Credentials > Create Credentials > OAuth client ID**.
   - Application type: **Desktop app**.
   - Copy your **Client ID** and **Client Secret**.

### Step 5: Generate Blogger Refresh Token (Supported Loopback Flow)
Run the included setup script on your local machine:
```bash
python scripts/get_blogger_refresh_token.py \
  --client-id "YOUR_CLIENT_ID.apps.googleusercontent.com" \
  --client-secret "YOUR_CLIENT_SECRET"
```
The script opens your browser to Google OAuth consent, catches the callback at `http://localhost:8080`, and securely exchanges the authorization code for your permanent `BLOGGER_REFRESH_TOKEN`.

### Step 6: Locate your Blogger Blog ID
1. Log in to [Blogger.com](https://www.blogger.com/).
2. Select your blog. The URL in your browser will be:
   `https://www.blogger.com/blog/posts/YOUR_BLOG_ID`
3. Copy the numeric string (e.g. `8391048123910391029`).

### Step 7: Configure GitHub Repository Secrets (Only 5 Required)
In your GitHub repository, navigate to **Settings > Secrets and variables > Actions > New repository secret**:

| Secret Name | Required For | Example / Description |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Article writer & claim research | `AIzaSy...` |
| `BLOGGER_BLOG_ID` | Blogger blog identification | `8391048123910391029` |
| `BLOGGER_CLIENT_ID` | OAuth2 token exchange | `*.apps.googleusercontent.com` |
| `BLOGGER_CLIENT_SECRET` | OAuth2 token exchange | `GOCSPX-...` |
| `BLOGGER_REFRESH_TOKEN` | Blogger post authorization | `1//04...` |
| `SCREENSHOT_HOST_URL` | *(Optional)* Image hosting | HTTPS endpoint to receive and host PNGs |

*Note: Cloudflare Worker and D1 secrets (`CLOUDFLARE_WORKER_URL`, `CLOUDFLARE_WORKER_SECRET`, `CLOUDFLARE_API_TOKEN`) are no longer required.*

---

## 5. Local Execution & Testing

### Running Dry-Run Pipeline
Execute the full pipeline locally in dry-run mode without modifying Blogger state:
```bash
python -m src.main --dry-run
```

### Running the Complete Test Suite (45 Tests)
Run all 7 unit test suites with standard library `unittest` or `pytest`:
```bash
python -m unittest discover tests -v
# or
pytest tests/ -v
```

---

## 6. Security & Fail-Closed Integrity

1. **Fail-Closed Persistence Verification:** The pipeline validates write permissions to `data/processed_topics.json` before selecting a topic. If state cannot be read or written, the pipeline stops immediately to prevent duplicate runs.
2. **Concurrency Serialization:** The GitHub Actions workflow is assigned to a shared concurrency group with `cancel-in-progress: false`, ensuring overlapping runs queue sequentially rather than racing against git history.
3. **No Shell Concatenation:** `server.ts` uses `child_process.execFile` with separate argument arrays. Topic IDs are validated against strict regex (`^[a-zA-Z0-9_-]{1,64}$`), eliminating command injection.
4. **Path Traversal Defense:** Developer console file reads are locked to a strict allowlist of repository files. Any path containing `..` or targeting sensitive files (`.env`, private keys) is rejected with HTTP 403.
5. **No Runner-Local Paths in HTML:** Article HTML is strictly audited. If an image is captured but no public HTTPS host is configured, the image tag is safely omitted so readers never see broken local runner paths.
6. **Fail-Closed Reconciliation:** If Blogger post lookup fails due to a network or auth error, the pipeline stops immediately rather than risking duplicate post creation.
7. **No Mock Data in Live Mode:** Test fixtures and mock screenshots fail closed if submitted in live mode.

---

## 7. License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
