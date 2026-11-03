# The Digital Toolkit — Content Automation Engine

[![The Digital Toolkit](https://img.shields.io/badge/Publication-The_Digital_Toolkit-0284c7?logo=blogger&logoColor=white)](https://digitaltoolkitguide.blogspot.com/)
[![Blogger Content Pipeline](https://img.shields.io/badge/Workflow-GitHub_Actions-2088FF?logo=github-actions&logoColor=white)](.github/workflows/content-pipeline.yml)
[![Cloudflare Worker](https://img.shields.io/badge/Backend-Cloudflare_Worker_%26_D1-F38020?logo=cloudflare&logoColor=white)](worker/wrangler.toml)
[![Python 3.11](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Tests: 50 Passing](https://img.shields.io/badge/Tests-50_Passing-emerald)](tests/)
[![Safety: Draft First](https://img.shields.io/badge/Safety-Draft_Default-success)](config/editorial_policy.md)
[![Style: Plain English](https://img.shields.io/badge/Style-Plain_English-emerald)](config/editorial_policy.md)

An automated content production engine built for **The Digital Toolkit** ([digitaltoolkitguide.blogspot.com](https://digitaltoolkitguide.blogspot.com/)).

**Tagline:** *Discover smarter tools. Work better. Do more.*

The purpose of the engine is to research, create, optimize, and prepare useful educational articles for The Digital Toolkit with minimal manual work. The system operates primarily through **GitHub Actions**, with a lightweight **Cloudflare Worker & D1 database** providing persistent state coordination across runner environments.

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
|                          (or manual workflow_dispatch)                            |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
                      +--------------------------------------+
                      |      Stage 1: Validation             |
                      |  Validate secrets & safe config      |
                      +--------------------------------------+
                                         |
                                         v
                      +--------------------------------------+
                      |      Stage 2: Topic Selection        |
                      |  Check persistent state history      |
                      |  Deduplicate using SHA-256 fingerprint|
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
                      |  Save state to GitHub cache & file   |
                      |  Emit report.json & job summary      |
                      +--------------------------------------+
```

---

## 2. Directory Structure

```text
blogger-content-engine/
├── .github/
│   └── workflows/
│       ├── content-pipeline.yml   # Pinned Actions SHAs, state cache & schedule
│       ├── deploy-worker.yml      # Automated Cloudflare Worker deployment
│       └── tests.yml              # CI test runner (36 automated unit tests)
├── config/
│   ├── settings.example.yaml      # Pipeline, model, and quality thresholds
│   └── editorial_policy.md        # Plain-English mandate & anti-spam guidelines
├── data/
│   ├── topics.csv                 # Queue of eligible candidate topics (4 categories)
│   └── processed_topics.json      # Persistent history across workflow runs
├── output/
│   ├── report.json                # Structured execution results (generated per run)
│   ├── summary.md                 # Markdown summary for GitHub Step Summary
│   └── screenshots/               # Playwright captures
├── scripts/
│   └── get_blogger_refresh_token.py # Supported OAuth2 loopback token generator
├── src/
│   ├── __init__.py
│   ├── article_writer.py          # Gemini API client with fail-closed schema & slugs
│   ├── blogger_client.py          # Blogger API v3 & fail-closed reconciliation
│   ├── cloudflare_client.py       # Cloudflare Worker bridge & persistent D1 sync
│   ├── config.py                  # Env parsing & credential redaction
│   ├── main.py                    # Master CLI pipeline orchestrator
│   ├── quality_checks.py          # Hard quality gates & plain-English style checks
│   ├── report.py                  # report.json & GitHub step summary emitter
│   ├── research.py                # Live HTTP source verification & claim mapping
│   ├── screenshot_capture.py      # Playwright browser capture & HTTPS hosting
│   ├── seo_metadata.py            # Label normalization & local path defense
│   ├── state_store.py             # Atomic state persistence, D1 merge & fingerprinting
│   └── topic_discovery.py         # CSV topic intake and priority selection
├── worker/
│   ├── index.ts                   # Cloudflare Worker API router & D1 SQL queries
│   ├── schema.sql                 # D1 table schemas for processed topics & runs
│   └── wrangler.toml              # Cloudflare Worker configuration & D1 binding
├── templates/
│   └── article_prompt.md          # Master prompt template for Gemini
├── tests/
│   ├── test_blogger_payload.py    # Blogger v3 schema & safe reconciliation
│   ├── test_cloudflare_worker.py  # Cloudflare Worker client & D1 coordination
│   ├── test_deduplication.py      # Multi-run state persistence & fingerprinting
│   ├── test_quality_checks.py     # Quality gate, plain English & local path leak tests
│   ├── test_research_and_sources.py # Live source verification & claim mapping
│   ├── test_security_and_console.py # Safe process spawning & traversal defense
│   └── test_style_and_writer.py   # Fail-closed Gemini JSON & AI cliché checks
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

### Step 2: Obtain Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Click **Get API key** and create a key in your Google Cloud project.
3. Save this value for GitHub Secret `GEMINI_API_KEY`.

### Step 3: Configure Google Cloud & Blogger API v3
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

### Step 4: Generate Blogger Refresh Token (Supported Loopback Flow)
Run the included setup script on your local machine:
```bash
python scripts/get_blogger_refresh_token.py \
  --client-id "YOUR_CLIENT_ID.apps.googleusercontent.com" \
  --client-secret "YOUR_CLIENT_SECRET"
```
The script opens your browser to Google OAuth consent, catches the callback at `http://localhost:8080`, and securely exchanges the authorization code for your permanent `BLOGGER_REFRESH_TOKEN`.

### Step 5: Locate your Blogger Blog ID
1. Log in to [Blogger.com](https://www.blogger.com/).
2. Select your blog. The URL in your browser will be:
   `https://www.blogger.com/blog/posts/YOUR_BLOG_ID`
3. Copy the numeric string (e.g. `8391048123910391029`).

### Step 6: Configure Cloudflare Worker & Existing D1 Database
The Worker is configured as `digital-toolkit-worker` bound to the existing database `digital-toolkit-db`:

1. **Find your existing D1 database UUID:**
   ```bash
   npx wrangler d1 info digital-toolkit-db
   ```
   *(Or in Cloudflare Dashboard: Workers & Pages → D1 → digital-toolkit-db → copy Database ID).*

2. **Insert the UUID into `worker/wrangler.toml`:**
   Open `worker/wrangler.toml` and replace `<YOUR_D1_DATABASE_ID_FROM_CLOUDFLARE>`:
   ```toml
   [[d1_databases]]
   binding = "DB"
   database_name = "digital-toolkit-db"
   database_id = "PASTE_YOUR_COPIED_D1_UUID_HERE"
   ```

3. **Apply the database schema to remote D1:**
   ```bash
   npx wrangler d1 execute digital-toolkit-db --file=worker/schema.sql
   ```

4. **Set the Worker API secret:**
   ```bash
   cd worker && npx wrangler secret put WORKER_API_SECRET
   ```

5. **Deploy the Worker:**
   - **Option A: Via CLI**
     ```bash
     cd worker && npx wrangler deploy
     ```
   - **Option B: Via Cloudflare Workers Builds (Git Integration)**
     When connecting your GitHub repository to Cloudflare Workers Builds in the Cloudflare Dashboard (**Workers & Pages > Connect to Git**):
     - **Worker Name**: `digital-toolkit-worker`
     - **Root directory**: `worker` *(CRITICAL: This directs Cloudflare into the `worker/` subfolder, ensuring it deploys only the TypeScript Worker and never attempts to install root Python dependencies)*
     - **Build command**: `npx wrangler deploy --dry-run` *(or leave empty)*
     - **Deploy command**: `npx wrangler deploy`
     - **Environment variables**: Add `WORKER_API_SECRET` under Worker Settings > Variables.

### Step 7: Configure GitHub Repository Secrets
In your GitHub repository, navigate to **Settings > Secrets and variables > Actions > New repository secret**:

| Secret Name | Required For | Example / Description |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Article writer | `AIzaSy...` |
| `BLOGGER_BLOG_ID` | Blogger blog identification | `8391048123910391029` |
| `BLOGGER_CLIENT_ID` | OAuth2 token exchange | `*.apps.googleusercontent.com` |
| `BLOGGER_CLIENT_SECRET` | OAuth2 token exchange | `GOCSPX-...` |
| `BLOGGER_REFRESH_TOKEN` | Blogger post authorization | `1//04...` |
| `CLOUDFLARE_WORKER_URL` | *(Optional)* D1 state & telemetry | `https://digital-toolkit-worker.<subdomain>.workers.dev` |
| `CLOUDFLARE_WORKER_SECRET`| *(Optional)* D1 API authentication | Shared bearer secret matching WORKER_API_SECRET |
| `CLOUDFLARE_API_TOKEN` | *(Optional)* Worker deployment CI | Cloudflare API token with Edit Workers permissions |
| `CLOUDFLARE_ACCOUNT_ID` | *(Optional)* Worker deployment CI | Cloudflare account ID |
| `SCREENSHOT_HOST_URL` | *(Optional)* Image hosting | HTTPS endpoint to receive and host PNGs |

---

## 5. Local Execution & Testing

### Running Dry-Run Pipeline
Execute the full pipeline locally in dry-run mode without modifying Blogger state:
```bash
python -m src.main --dry-run
```

### Running the Complete Test Suite (42 Tests)
Run all 7 unit test suites with standard library `unittest` or `pytest`:
```bash
python -m unittest discover tests -v
# or
pytest tests/ -v
```

---

## 6. Security & Fail-Closed Integrity

1. **No Shell Concatenation:** `server.ts` uses `child_process.execFile` with separate argument arrays. Topic IDs are validated against strict regex (`^[a-zA-Z0-9_-]{1,64}$`), eliminating command injection.
2. **Path Traversal Defense:** Developer console file reads are locked to a strict allowlist of 28 repository files. Any path containing `..` or targeting sensitive files (`.env`, private keys) is rejected with HTTP 403.
3. **No Runner-Local Paths in HTML:** Article HTML is strictly audited. If an image is captured but no public HTTPS host is configured, the image tag is safely omitted so readers never see broken local runner paths.
4. **Fail-Closed Reconciliation:** If Blogger post lookup fails due to a network or auth error, the pipeline stops immediately rather than risking duplicate post creation.
5. **No Mock Data in Live Mode:** Test fixtures and mock screenshots fail closed if submitted in live mode.

---

## 7. License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
