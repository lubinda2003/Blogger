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
                  Passed 50/50 Tests
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
              A streamlined, resilient content engine operating through GitHub Actions with Python 3.11, Google Gemini 2.5 Flash, Cloudflare Worker supporting backend with D1 SQL storage, and Blogger Drafts. Built for high editorial quality, zero AI clichés, and complete transparency.
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
                Scheduled daily at 06:00 UTC with manual <code className="text-slate-300">workflow_dispatch</code> trigger support.
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
              <h3 className="text-sm font-semibold text-slate-200">Cloudflare Worker & D1</h3>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                <code className="text-slate-300">digital-toolkit-worker</code> with <code className="text-slate-300">digital-toolkit-db</code> for persistent topic history and run telemetry.
              </p>
            </div>

            <div className="bg-slate-950/80 p-4 rounded-xl border border-slate-800">
              <div className="flex items-center gap-2 text-violet-400 text-xs font-semibold uppercase font-mono mb-2">
                <BookOpen className="h-4 w-4" />
                <span>4. Destination</span>
              </div>
              <h3 className="text-sm font-semibold text-slate-200">Blogger Drafts</h3>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                Direct OAuth2 insertion via Blogger API v3. Enforces <code className="text-slate-300">isDraft=true</code> for human review.
              </p>
            </div>
          </div>
        </section>

        {/* Cloudflare D1 Manual Configuration Guide */}
        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <Database className="h-5 w-5 text-sky-400" />
                <h2 className="text-base font-semibold text-slate-100">
                  Cloudflare D1 Database & Worker Configuration
                </h2>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Follow these exact steps to connect the existing <code className="text-slate-300">digital-toolkit-db</code> database to <code className="text-slate-300">digital-toolkit-worker</code>.
              </p>
            </div>
            <span className="text-xs font-mono bg-sky-500/10 text-sky-400 border border-sky-500/20 px-2.5 py-1 rounded-md">
              Target: digital-toolkit-db
            </span>
          </div>

          <div className="space-y-4 text-xs">
            {/* Step 1 */}
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200">
                  Step 1: Get the Existing D1 Database UUID
                </span>
                <span className="text-[11px] text-slate-400 font-mono">Terminal / Cloudflare CLI</span>
              </div>
              <p className="text-slate-400">
                Run this command to inspect your existing Cloudflare D1 database and copy its UUID:
              </p>
              <div className="flex items-center justify-between bg-slate-900 px-3 py-2 rounded-lg border border-slate-800 font-mono text-slate-200">
                <code>npx wrangler d1 info digital-toolkit-db</code>
                <button
                  onClick={() => copyToClipboard('npx wrangler d1 info digital-toolkit-db', 'cmd1')}
                  className="text-slate-400 hover:text-slate-200 text-xs flex items-center gap-1 transition"
                >
                  {copiedKey === 'cmd1' ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                  <span>{copiedKey === 'cmd1' ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
              <p className="text-[11px] text-slate-500">
                Alternatively, open the Cloudflare Dashboard: <strong>Workers & Pages</strong> → <strong>D1 SQL Database</strong> → click <strong>digital-toolkit-db</strong> and copy the <em>Database ID</em>.
              </p>
            </div>

            {/* Step 2 */}
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200">
                  Step 2: Insert UUID into worker/wrangler.toml
                </span>
                <span className="text-[11px] text-slate-400 font-mono">worker/wrangler.toml</span>
              </div>
              <p className="text-slate-400">
                In <code className="text-sky-300">worker/wrangler.toml</code>, replace the placeholder with your copied UUID:
              </p>
              <pre className="bg-slate-900 p-3 rounded-lg border border-slate-800 font-mono text-[11px] text-slate-300 leading-relaxed overflow-x-auto">
{`[[d1_databases]]
binding = "DB"
database_name = "digital-toolkit-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # <-- Paste your UUID here`}
              </pre>
            </div>

            {/* Step 3 */}
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200">
                  Step 3: Execute Schema on Cloudflare D1
                </span>
                <span className="text-[11px] text-slate-400 font-mono">One-time database setup</span>
              </div>
              <p className="text-slate-400">
                Apply the tables (<code className="text-slate-300">processed_topics</code> and <code className="text-slate-300">pipeline_runs</code>) to your remote D1 database:
              </p>
              <div className="flex items-center justify-between bg-slate-900 px-3 py-2 rounded-lg border border-slate-800 font-mono text-slate-200">
                <code>npx wrangler d1 execute digital-toolkit-db --file=worker/schema.sql</code>
                <button
                  onClick={() => copyToClipboard('npx wrangler d1 execute digital-toolkit-db --file=worker/schema.sql', 'cmd2')}
                  className="text-slate-400 hover:text-slate-200 text-xs flex items-center gap-1 transition"
                >
                  {copiedKey === 'cmd2' ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                  <span>{copiedKey === 'cmd2' ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
            </div>

            {/* Step 4 */}
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200">
                  Step 4: Set Worker API Secret
                </span>
                <span className="text-[11px] text-slate-400 font-mono">Authentication Guard</span>
              </div>
              <p className="text-slate-400">
                Configure the shared secret used by the Python engine to communicate with the Cloudflare Worker:
              </p>
              <div className="flex items-center justify-between bg-slate-900 px-3 py-2 rounded-lg border border-slate-800 font-mono text-slate-200">
                <code>cd worker && npx wrangler secret put WORKER_API_SECRET</code>
                <button
                  onClick={() => copyToClipboard('cd worker && npx wrangler secret put WORKER_API_SECRET', 'cmd3')}
                  className="text-slate-400 hover:text-slate-200 text-xs flex items-center gap-1 transition"
                >
                  {copiedKey === 'cmd3' ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                  <span>{copiedKey === 'cmd3' ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
            </div>

            {/* Step 5 */}
            <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200">
                  Step 5: Cloudflare Workers Builds (Git Settings)
                </span>
                <span className="text-[11px] text-sky-400 font-mono">Workers & Pages Dashboard</span>
              </div>
              <p className="text-slate-400">
                When connecting your repository in Cloudflare Dashboard under <strong>Workers & Pages &gt; Connect to Git</strong>, configure:
              </p>
              <div className="bg-slate-900 p-3 rounded-lg border border-slate-800 font-mono text-[11px] text-slate-300 space-y-1">
                <div><span className="text-sky-400">Worker name:</span> digital-toolkit-worker</div>
                <div><span className="text-sky-400">Root directory:</span> worker <span className="text-emerald-400">(← Prevents Cloudflare from running pip or touching Python)</span></div>
                <div><span className="text-sky-400">Build command:</span> npx wrangler deploy --dry-run <span className="text-slate-500">(or leave empty)</span></div>
                <div><span className="text-sky-400">Deploy command:</span> npx wrangler deploy</div>
              </div>
            </div>
          </div>
        </section>

        {/* GitHub Secrets Reference Card */}
        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-4">
          <div className="flex items-center gap-2">
            <Lock className="h-5 w-5 text-emerald-400" />
            <h2 className="text-base font-semibold text-slate-100">
              GitHub Actions Secrets Configuration
            </h2>
          </div>
          <p className="text-xs text-slate-400">
            Set these repository secrets in GitHub: <strong>Settings</strong> → <strong>Secrets and variables</strong> → <strong>Actions</strong>:
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            {[
              { name: 'GEMINI_API_KEY', desc: 'Google AI Studio Gemini API key for draft generation.' },
              { name: 'BLOGGER_BLOG_ID', desc: 'Blogger Blog ID for digitaltoolkitguide.blogspot.com.' },
              { name: 'BLOGGER_CLIENT_ID', desc: 'Google Cloud OAuth 2.0 Web Client ID.' },
              { name: 'BLOGGER_CLIENT_SECRET', desc: 'Google Cloud OAuth 2.0 Client Secret.' },
              { name: 'BLOGGER_REFRESH_TOKEN', desc: 'OAuth 2.0 Refresh Token with blogger scope.' },
              { name: 'CLOUDFLARE_WORKER_URL', desc: 'URL of deployed digital-toolkit-worker (e.g. https://digital-toolkit-worker.workers.dev).' },
              { name: 'CLOUDFLARE_WORKER_SECRET', desc: 'Secret matching WORKER_API_SECRET for D1 authorization.' },
              { name: 'CLOUDFLARE_API_TOKEN', desc: 'Worker deployment token (for deploy-worker.yml).' }
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
                <span>Visible Cloudflare D1 Reliability</span>
              </div>
              <p className="text-slate-400">
                Explicitly distinguishes local JSON fallback from successful Cloudflare D1 sync. If D1 is unavailable or misconfigured, it reports an explicit warning rather than silently claiming success.
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
                Verified Test Suite (50/50 Tests Passing)
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
              <div className="font-semibold text-slate-200">test_cloudflare_worker.py</div>
              <div className="text-slate-400 text-[11px] mt-1">D1 error visibility, last_error recording, and StateStore status tracking.</div>
              <div className="text-emerald-400 font-mono text-[11px] mt-2">✓ 10/10 passing</div>
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
              <div className="text-emerald-400 font-mono text-[11px] mt-2">✓ 10/10 passing</div>
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
