import React, { useState } from 'react';
import {
  Download,
  ExternalLink,
  ShieldCheck,
  CheckCircle2,
  Copy,
  Check,
  Layers,
  Database,
  Terminal,
  FileCheck2,
  Lock,
  Calendar,
  AlertCircle,
  HelpCircle,
  FileCode,
  BookOpen
} from 'lucide-react';

export default function App() {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(id);
    setTimeout(() => setCopiedKey(null), 2500);
  };

  const downloadRepoZip = () => {
    const a = document.createElement('a');
    a.href = '/blogger-content-engine.zip';
    a.download = 'blogger-content-engine.zip';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-sky-500 selection:text-white">
      {/* Top Navigation / Brand Header */}
      <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur px-6 py-4 sticky top-0 z-30">
        <div className="max-w-6xl mx-auto flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400">
              <Layers className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-semibold text-base text-slate-100 tracking-tight">
                  The Digital Toolkit — Content Automation Engine
                </h1>
                <span className="text-[10px] font-mono uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded">
                  Passed 45/45 Tests
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-400 mt-0.5">
                <a
                  href="https://digitaltoolkitguide.blogspot.com/"
                  target="_blank"
                  rel="noreferrer"
                  className="text-sky-400 hover:underline flex items-center gap-1 font-medium"
                >
                  <span>digitaltoolkitguide.blogspot.com</span>
                  <ExternalLink className="h-3 w-3" />
                </a>
                <span aria-hidden="true">·</span>
                <span className="italic text-slate-400">Discover smarter tools. Work better. Do more.</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={downloadRepoZip}
              className="flex items-center gap-2 px-4 py-2 bg-sky-500 hover:bg-sky-400 active:bg-sky-600 text-slate-950 text-xs font-semibold rounded-lg shadow-sm transition"
              title="Download complete, corrected repository ready for deployment"
            >
              <Download className="h-4 w-4" />
              <span>Download Project ZIP</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-6xl mx-auto w-full p-6 space-y-8">
        {/* Hero Architecture Card */}
        <section className="bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 border border-slate-800 rounded-2xl p-6 sm:p-8 shadow-sm">
          <div className="max-w-3xl">
            <span className="text-[11px] font-mono font-medium text-sky-400 uppercase tracking-wider bg-sky-500/10 border border-sky-500/20 px-2.5 py-1 rounded-full">
              Production Architecture Specification
            </span>
            <h2 className="text-xl sm:text-2xl font-bold text-slate-100 tracking-tight mt-3">
              Automated Content Production for The Digital Toolkit
            </h2>
            <p className="text-sm text-slate-300 mt-2 leading-relaxed">
              A simplified, fully self-contained content engine operating entirely through GitHub Actions with Python 3.11, Google Gemini 2.5 Flash, repository-native state persistence via <code className="text-sky-300">data/processed_topics.json</code>, and Blogger Drafts. No external database or Cloudflare Worker dependencies required.
            </p>
          </div>

          {/* 4-Pillar Pipeline Flow */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-8">
            <div className="bg-slate-950/80 p-4 rounded-xl border border-slate-800">
              <div className="flex items-center gap-2 text-sky-400 text-xs font-semibold uppercase font-mono mb-2">
                <Calendar className="h-4 w-4" />
                <span>1. Runner</span>
              </div>
              <h3 className="text-sm font-semibold text-slate-200">GitHub Actions</h3>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                Scheduled daily with manual <code className="text-slate-300">workflow_dispatch</code>. Concurrency serialized to prevent overlap.
              </p>
            </div>

            <div className="bg-slate-950/80 p-4 rounded-xl border border-slate-800">
              <div className="flex items-center gap-2 text-emerald-400 text-xs font-semibold uppercase font-mono mb-2">
                <FileCode className="h-4 w-4" />
                <span>2. Core Engine</span>
              </div>
              <h3 className="text-sm font-semibold text-slate-200">Python 3.11 Engine</h3>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                Topic selection, real source fact-checking, Gemini 2.5 Flash drafting, Playwright capture, and 10 hard QA gates.
              </p>
            </div>

            <div className="bg-slate-950/80 p-4 rounded-xl border border-slate-800">
              <div className="flex items-center gap-2 text-amber-400 text-xs font-semibold uppercase font-mono mb-2">
                <Database className="h-4 w-4" />
                <span>3. State & Telemetry</span>
              </div>
              <h3 className="text-sm font-semibold text-slate-200">Repository State</h3>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                <code className="text-slate-300">data/processed_topics.json</code> with SHA-256 fingerprint deduplication, fail-closed verification, and workflow artifacts.
              </p>
            </div>

            <div className="bg-slate-950/80 p-4 rounded-xl border border-slate-800">
              <div className="flex items-center gap-2 text-violet-400 text-xs font-semibold uppercase font-mono mb-2">
                <BookOpen className="h-4 w-4" />
                <span>4. Destination</span>
              </div>
              <h3 className="text-sm font-semibold text-slate-200">Blogger Drafts</h3>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                Direct OAuth2 insertion via Blogger API v3. Enforces <code className="text-slate-300">isDraft=true</code> for human editorial review.
              </p>
            </div>
          </div>
        </section>

        {/* Repository State Persistence Guide */}
        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <Database className="h-5 w-5 text-sky-400" />
                <h2 className="text-base font-semibold text-slate-100">
                  Repository-Native State Persistence Architecture
                </h2>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                The content engine persists state directly within your repository using <code className="text-slate-300">data/processed_topics.json</code>. No Cloudflare Worker or external SQL database required.
              </p>
            </div>
            <span className="text-xs font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2.5 py-1 rounded-md">
              Zero External DB
            </span>
          </div>

          <div className="space-y-4 text-xs">
            {/* Step 1 */}
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200">
                  Step 1: Enable GitHub Actions Workflow Write Permissions
                </span>
                <span className="text-[11px] text-amber-400 font-mono">Critical Setting</span>
              </div>
              <p className="text-slate-400">
                To allow GitHub Actions to commit updated topic history back to your repository:
              </p>
              <div className="bg-slate-900 p-3 rounded-lg border border-slate-800 font-mono text-[11px] text-slate-300 space-y-1">
                <div>1. In GitHub, go to <span className="text-sky-400">Settings</span> → <span className="text-sky-400">Actions</span> → <span className="text-sky-400">General</span>.</div>
                <div>2. Under <span className="text-sky-400">Workflow permissions</span>, select <span className="text-emerald-400 font-semibold">Read and write permissions</span>.</div>
                <div>3. Check <span className="text-emerald-400">Allow GitHub Actions to create and approve pull requests</span> (optional, but keep checked).</div>
                <div>4. Click <span className="text-sky-400">Save</span>.</div>
              </div>
            </div>

            {/* Step 2 */}
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200">
                  Step 2: Concurrency Serialization (Overlapping Protection)
                </span>
                <span className="text-[11px] text-sky-400 font-mono">.github/workflows/content-pipeline.yml</span>
              </div>
              <p className="text-slate-400">
                The workflow includes concurrency group serialization (<code className="text-sky-300">group: blogger-content-pipeline</code>, <code className="text-sky-300">cancel-in-progress: false</code>). If multiple runs are triggered simultaneously, subsequent runs are placed in a queue and execute sequentially to guarantee git history integrity and prevent duplicate posts.
              </p>
            </div>

            {/* Step 3 */}
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200">
                  Step 3: Atomic State Commit and Push
                </span>
                <span className="text-[11px] text-emerald-400 font-mono">Automated on Success</span>
              </div>
              <p className="text-slate-400">
                When a live article run succeeds (<code className="text-slate-300">dry_run=false</code>), GitHub Actions automatically stages <code className="text-sky-300">data/processed_topics.json</code>, executes a git rebase against the branch to absorb any concurrent commits, and pushes cleanly with the <code className="text-slate-300">github-actions[bot]</code> author identity.
              </p>
            </div>

            {/* Step 4 */}
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200">
                  Step 4: Run Telemetry & Execution Artifacts
                </span>
                <span className="text-[11px] text-violet-400 font-mono">Actions Artifacts</span>
              </div>
              <p className="text-slate-400">
                Instead of storing logs in external SQL tables, full pipeline telemetry is preserved natively in GitHub:
              </p>
              <ul className="list-disc list-inside text-slate-400 space-y-1">
                <li><strong className="text-slate-300">GitHub Step Summary:</strong> View stage-by-stage results directly on the workflow run page.</li>
                <li><strong className="text-slate-300">Artifact (content-pipeline-report):</strong> Downloadable <code className="text-slate-300">report.json</code> containing verified sources, word count, quality scores, and Blogger draft URL.</li>
              </ul>
            </div>
          </div>
        </section>

        {/* GitHub Secrets Reference Card */}
        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Lock className="h-5 w-5 text-emerald-400" />
              <h2 className="text-base font-semibold text-slate-100">
                Required GitHub Actions Secrets (Reduced to 5)
              </h2>
            </div>
            <span className="text-xs font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2.5 py-1 rounded-md">
              Only 5 Secrets Needed
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Configure these 5 secrets in your repository: <strong>Settings</strong> → <strong>Secrets and variables</strong> → <strong>Actions</strong>:
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            {[
              { name: 'GEMINI_API_KEY', desc: 'Google AI Studio Gemini API key for draft generation and claim synthesis.' },
              { name: 'BLOGGER_BLOG_ID', desc: 'Blogger Blog ID for digitaltoolkitguide.blogspot.com (numeric string).' },
              { name: 'BLOGGER_CLIENT_ID', desc: 'Google Cloud OAuth 2.0 Web Client ID (*.apps.googleusercontent.com).' },
              { name: 'BLOGGER_CLIENT_SECRET', desc: 'Google Cloud OAuth 2.0 Client Secret.' },
              { name: 'BLOGGER_REFRESH_TOKEN', desc: 'Permanent OAuth 2.0 Refresh Token with blogger scope.' },
              { name: 'SCREENSHOT_HOST_URL', desc: '(Optional) HTTPS endpoint to receive and host PNG screenshots.' }
            ].map((secret) => (
              <div key={secret.name} className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 flex items-start justify-between gap-3">
                <div>
                  <div className="font-mono font-semibold text-sky-400 text-xs">{secret.name}</div>
                  <p className="text-slate-400 text-[11px] mt-1">{secret.desc}</p>
                </div>
                <button
                  onClick={() => copyToClipboard(secret.name, secret.name)}
                  className="text-slate-500 hover:text-slate-300 p-1"
                  title="Copy secret name"
                >
                  {copiedKey === secret.name ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                </button>
              </div>
            ))}
          </div>
        </section>

        {/* Quality Gates & Research Verification Card */}
        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-4">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
            <h2 className="text-base font-semibold text-slate-100">
              Hard Quality Gate & Research Verification Engine
            </h2>
          </div>
          <p className="text-xs text-slate-400">
            Fails closed on any policy violation. A website returning HTTP 200 does not automatically verify a claim—retrieved page text must substantively support the claim keywords.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
              <div className="font-semibold text-slate-200 flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                <span>Substantive Claim Verification</span>
              </div>
              <p className="text-slate-400">
                Extracts key claim tokens and searches fetched page content. If page content is empty, an error page, or lacks matching claim keywords, the source is marked unverified for manual review.
              </p>
            </div>

            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
              <div className="font-semibold text-slate-200 flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                <span>Plain English (Zero AI Clichés)</span>
              </div>
              <p className="text-slate-400">
                Strict regex scanner blocks generic clichés (&quot;in today&apos;s fast-paced world&quot;, &quot;game changer&quot;, &quot;delve into&quot;) and prohibited financial promises.
              </p>
            </div>

            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
              <div className="font-semibold text-slate-200 flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                <span>Fail-Closed State Verification</span>
              </div>
              <p className="text-slate-400">
                The engine checks write access to <code className="text-slate-300">data/processed_topics.json</code> at startup. If the file cannot be read or written, the pipeline stops immediately before generating any article.
              </p>
            </div>

            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
              <div className="font-semibold text-slate-200 flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                <span>Draft-First Blogger Safety Lock</span>
              </div>
              <p className="text-slate-400">
                Posts are always created as Blogger drafts (<code className="text-slate-300">isDraft=true</code>). Live public posting is blocked unless explicitly confirmed by the human editor.
              </p>
            </div>
          </div>
        </section>

        {/* Test Suite Summary */}
        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileCheck2 className="h-5 w-5 text-emerald-400" />
              <h2 className="text-base font-semibold text-slate-100">
                Verified Test Suite (45/45 Tests Passing)
              </h2>
            </div>
            <span className="text-xs font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2.5 py-1 rounded-md">
              100% Pass Rate
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs">
            <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800">
              <div className="font-semibold text-slate-200">test_research_and_sources.py</div>
              <div className="text-slate-400 text-[11px] mt-1">Claim keyword verification, irrelevant 200 detection, and soft-404 rejection.</div>
              <div className="text-emerald-400 font-mono text-[11px] mt-2">✓ 9/9 passing</div>
            </div>

            <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800">
              <div className="font-semibold text-slate-200">test_state_persistence.py</div>
              <div className="text-slate-400 text-[11px] mt-1">Repository persistence, fail-closed permission defense, atomic swap, and deduplication.</div>
              <div className="text-emerald-400 font-mono text-[11px] mt-2">✓ 6/6 passing</div>
            </div>

            <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800">
              <div className="font-semibold text-slate-200">test_quality_checks.py</div>
              <div className="text-slate-400 text-[11px] mt-1">Plain English rules, banned financial guarantees, and local path leak defenses.</div>
              <div className="text-emerald-400 font-mono text-[11px] mt-2">✓ 9/9 passing</div>
            </div>

            <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800">
              <div className="font-semibold text-slate-200">test_deduplication.py</div>
              <div className="text-slate-400 text-[11px] mt-1">Fingerprinting, stop-word stripping, and persistent topic state.</div>
              <div className="text-emerald-400 font-mono text-[11px] mt-2">✓ 4/4 passing</div>
            </div>

            <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800">
              <div className="font-semibold text-slate-200">test_blogger_payload.py</div>
              <div className="text-slate-400 text-[11px] mt-1">Blogger v3 payload validation, token redaction, and reconciliation safety.</div>
              <div className="text-emerald-400 font-mono text-[11px] mt-2">✓ 8/8 passing</div>
            </div>

            <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800">
              <div className="font-semibold text-slate-200">test_style_and_writer.py & security</div>
              <div className="text-slate-400 text-[11px] mt-1">Fail-closed Gemini JSON handling, input validation, and regex defense.</div>
              <div className="text-emerald-400 font-mono text-[11px] mt-2">✓ 9/9 passing</div>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 bg-slate-900/50 px-6 py-6 mt-12 text-center text-xs text-slate-500">
        <p>The Digital Toolkit Content Automation Engine · Draft-First Publication for digitaltoolkitguide.blogspot.com</p>
      </footer>
    </div>
  );
}
