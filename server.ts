import express from 'express';
import { createServer as createViteServer } from 'vite';
import { execFile } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import path from 'path';

const execFileAsync = promisify(execFile);

// Strict allowlist of repository files readable via the developer console
const ALLOWED_REPO_FILES = new Set([
  '.github/workflows/content-pipeline.yml',
  '.github/workflows/deploy-worker.yml',
  '.github/workflows/tests.yml',
  'config/settings.example.yaml',
  'config/editorial_policy.md',
  'config/config.json',
  'config/config.example.json',
  'data/topics.csv',
  'data/processed_topics.json',
  'src/__init__.py',
  'src/main.py',
  'src/config.py',
  'src/topic_discovery.py',
  'src/research.py',
  'src/article_writer.py',
  'src/screenshot_capture.py',
  'src/seo_metadata.py',
  'src/quality_checks.py',
  'src/blogger_client.py',
  'src/state_store.py',
  'src/report.py',
  'templates/article_prompt.md',
  'tests/test_quality_checks.py',
  'tests/test_deduplication.py',
  'tests/test_blogger_payload.py',
  'tests/test_research_and_sources.py',
  'tests/test_style_and_writer.py',
  'tests/test_security_and_console.py',
  'tests/test_state_persistence.py',
  'scripts/get_blogger_refresh_token.py',
  'config/requirements.txt',
  'README.md',
  'LICENSE',
  '.gitignore',
]);

const ALLOWED_STAGES = new Set(['all', 'discover', 'research', 'write', 'screenshot', 'qa', 'publish']);

async function startServer() {
  const app = express();
  const PORT = process.env.PORT || 3000;

  app.use(express.json());

  // API Route: Secure Pipeline Execution (Uses execFile with separate argument array)
  app.post('/api/pipeline/run', async (req, res) => {
    try {
      const { dryRun = true, topicId, stage = 'all', liveConfirmationToken } = req.body;

      // Security check: Validate live run authorization (No weak fallback default token permitted)
      if (!dryRun) {
        const expectedToken = process.env.DEV_CONSOLE_SECRET;
        if (!expectedToken || !expectedToken.trim() || liveConfirmationToken !== expectedToken) {
          return res.status(403).json({
            success: false,
            error: 'Live pipeline runs via HTTP interface are disabled without an explicitly configured DEV_CONSOLE_SECRET.',
          });
        }
      }

      // Security check: Validate stage against allowlist
      if (typeof stage !== 'string' || !ALLOWED_STAGES.has(stage)) {
        return res.status(400).json({
          success: false,
          error: `Invalid stage parameter: '${stage}'`,
        });
      }

      // Build argument array safely without shell interpolation
      const args: string[] = ['-m', 'src.main'];

      if (dryRun) {
        args.push('--dry-run');
      } else {
        args.push('--live');
      }

      if (topicId) {
        // Validate topicId strictly with regex to eliminate injection vectors
        if (typeof topicId !== 'string' || !/^[a-zA-Z0-9_-]{1,64}$/.test(topicId)) {
          return res.status(400).json({
            success: false,
            error: 'Invalid topicId format. Only alphanumeric characters, hyphens, and underscores are allowed.',
          });
        }
        args.push('--topic-id', topicId);
      }

      if (stage !== 'all') {
        args.push('--stage', stage);
      }

      // Execute python3 directly using execFile (bypassing shell string execution)
      const { stdout, stderr } = await execFileAsync('python3', args, {
        cwd: process.cwd(),
        timeout: 45000,
        env: {
          ...process.env,
          // Ensure live publish is not inadvertently confirmed unless explicit
          CONFIRM_LIVE_PUBLISH: dryRun ? 'false' : process.env.CONFIRM_LIVE_PUBLISH || 'false',
        },
      });

      let report = null;
      const reportPath = path.join(process.cwd(), 'output', 'report.json');
      if (fs.existsSync(reportPath)) {
        try {
          report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'));
        } catch {
          // ignore
        }
      }

      res.json({
        success: true,
        command: `python3 ${args.join(' ')}`,
        stdout,
        stderr,
        report,
      });
    } catch (error: any) {
      let report = null;
      const reportPath = path.join(process.cwd(), 'output', 'report.json');
      if (fs.existsSync(reportPath)) {
        try {
          report = JSON.parse(fs.readFileSync(reportPath, 'utf-8'));
        } catch {
          // ignore
        }
      }

      res.status(200).json({
        success: false,
        error: error.message,
        stdout: error.stdout || '',
        stderr: error.stderr || '',
        report,
      });
    }
  });

  // API Route: Run Unit Tests using execFile
  app.post('/api/pipeline/test', async (req, res) => {
    try {
      const { stdout, stderr } = await execFileAsync('python3', ['-m', 'unittest', 'discover', 'tests', '-v'], {
        cwd: process.cwd(),
        timeout: 20000,
      });
      res.json({
        success: true,
        output: stdout || stderr,
        passed: true,
      });
    } catch (error: any) {
      res.json({
        success: false,
        output: error.stderr || error.stdout || error.message,
        passed: false,
      });
    }
  });

  // API Route: Read Repository File Content (Strict Allowlist & Traversal Defense)
  app.get('/api/repo/file', (req, res) => {
    const rawPath = (req.query.path as string) || '';

    // Block directory traversal attempts
    if (rawPath.includes('..') || path.isAbsolute(rawPath)) {
      return res.status(403).json({ error: 'Directory traversal forbidden.' });
    }

    const normalizedPath = path.normalize(rawPath).replace(/\\/g, '/');

    // Strict allowlist validation
    if (!ALLOWED_REPO_FILES.has(normalizedPath)) {
      return res.status(403).json({ error: 'Access to this file path is restricted.' });
    }

    const absolutePath = path.join(process.cwd(), normalizedPath);

    if (!fs.existsSync(absolutePath) || fs.statSync(absolutePath).isDirectory()) {
      return res.status(404).json({ error: 'File not found' });
    }

    const content = fs.readFileSync(absolutePath, 'utf-8');
    res.json({ path: normalizedPath, content });
  });

  // API Route: List Topics
  app.get('/api/topics', (req, res) => {
    const csvPath = path.join(process.cwd(), 'data', 'topics.csv');
    const processedPath = path.join(process.cwd(), 'data', 'processed_topics.json');

    let csvContent = '';
    let processedContent: any = { processed: [] };

    if (fs.existsSync(csvPath)) {
      csvContent = fs.readFileSync(csvPath, 'utf-8');
    }
    if (fs.existsSync(processedPath)) {
      try {
        processedContent = JSON.parse(fs.readFileSync(processedPath, 'utf-8'));
      } catch {
        // ignore
      }
    }

    res.json({
      rawCsv: csvContent,
      processed: processedContent.processed || [],
    });
  });

  // API Route: Bundle and download clean repository ZIP
  app.post('/api/repo/bundle-zip', async (req, res) => {
    try {
      await execFileAsync('python3', [
        '-c',
        `
import zipfile, os
from pathlib import Path

repo_files = [
    '.github/workflows/content-pipeline.yml',
    '.github/workflows/tests.yml',
    'config/settings.example.yaml',
    'config/editorial_policy.md',
    'data/topics.csv',
    'data/processed_topics.json',
    'src/__init__.py',
    'src/main.py',
    'src/config.py',
    'src/topic_discovery.py',
    'src/research.py',
    'src/article_writer.py',
    'src/screenshot_capture.py',
    'src/seo_metadata.py',
    'src/quality_checks.py',
    'src/blogger_client.py',
    'src/state_store.py',
    'src/report.py',
    'templates/article_prompt.md',
    'tests/test_quality_checks.py',
    'tests/test_deduplication.py',
    'tests/test_blogger_payload.py',
    'tests/test_research_and_sources.py',
    'tests/test_style_and_writer.py',
    'tests/test_security_and_console.py',
    'tests/test_state_persistence.py',
    'scripts/get_blogger_refresh_token.py',
    'config/requirements.txt',
    'README.md',
    'LICENSE',
    '.gitignore'
]

zip_path = Path('public/blogger-content-engine.zip')
zip_path.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for rel in repo_files:
        p = Path(rel)
        if p.exists():
            zf.write(p, arcname=f'blogger-content-engine/{rel}')
`,
      ]);
      res.json({ success: true, downloadUrl: '/blogger-content-engine.zip' });
    } catch (e: any) {
      res.status(500).json({ success: false, error: e.message });
    }
  });

  // Mount Vite development middlewares or serve static dist
  const isProduction = process.env.NODE_ENV === 'production';
  if (!isProduction) {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(Number(PORT), '0.0.0.0', () => {
    console.log(`Blogger Content Engine server running at http://0.0.0.0:${PORT}`);
  });
}

startServer().catch((err) => {
  console.error('Failed to start server:', err);
  process.exit(1);
});
