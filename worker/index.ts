/**
 * The Digital Toolkit - Supporting Cloudflare Worker Backend
 * 
 * Responsibilities:
 * - Persistent topic deduplication and run history query/recording via Cloudflare D1
 * - Secure bridge for GitHub Actions workflows
 * - Health and publication status endpoint for https://digitaltoolkitguide.blogspot.com/
 */

export interface D1PreparedStatement {
  bind(...values: any[]): D1PreparedStatement;
  all<T = any>(): Promise<{ results?: T[]; success: boolean; error?: string }>;
  run(): Promise<{ success: boolean; error?: string }>;
}

export interface D1Database {
  prepare(query: string): D1PreparedStatement;
  dump?(): Promise<ArrayBuffer>;
  batch?(statements: D1PreparedStatement[]): Promise<any[]>;
  exec?(query: string): Promise<any>;
}

export interface Env {
  DB?: D1Database;
  WORKER_API_SECRET?: string;
  CLOUDFLARE_WORKER_SECRET?: string;
  WORKER_API_KEY?: string;
  PUBLICATION_NAME?: string;
  WEBSITE_URL?: string;
  TAGLINE?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const { pathname } = url;

    // CORS headers for local / cross-origin inspection
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // Health & Info Endpoint (Public - does not expose secret or credentials)
    if (pathname === '/' || pathname === '/api/health') {
      return new Response(
        JSON.stringify({
          status: 'healthy',
          publication: env.PUBLICATION_NAME || 'The Digital Toolkit',
          tagline: env.TAGLINE || 'Discover smarter tools. Work better. Do more.',
          website: env.WEBSITE_URL || 'https://digitaltoolkitguide.blogspot.com/',
          d1_connected: Boolean(env.DB),
          timestamp: new Date().toISOString(),
        }),
        {
          headers: { 'Content-Type': 'application/json', ...corsHeaders },
        }
      );
    }

    // Authentication Guard for Protected API endpoints (Fail-Closed)
    // Supports WORKER_API_SECRET, CLOUDFLARE_WORKER_SECRET, or WORKER_API_KEY
    const rawSecret = env.WORKER_API_SECRET || env.CLOUDFLARE_WORKER_SECRET || env.WORKER_API_KEY || '';
    const secret = rawSecret.trim().replace(/^["']|["']$/g, '');
    if (!secret) {
      return new Response(
        JSON.stringify({
          error: 'Unauthorized: Worker API secret is not configured on server (set WORKER_API_SECRET in Worker Settings > Variables)',
          success: false,
        }),
        {
          status: 401,
          headers: { 'Content-Type': 'application/json', ...corsHeaders },
        }
      );
    }

    const authHeader = (request.headers.get('Authorization') || '').trim();
    if (!authHeader) {
      return new Response(
        JSON.stringify({
          error: 'Unauthorized: Missing Authorization header (expected Bearer <token>)',
          success: false,
        }),
        {
          status: 401,
          headers: { 'Content-Type': 'application/json', ...corsHeaders },
        }
      );
    }

    const match = authHeader.match(/^Bearer\s+(.+)$/i);
    if (!match) {
      return new Response(
        JSON.stringify({
          error: 'Unauthorized: Invalid Authorization scheme (expected Bearer <token>)',
          success: false,
        }),
        {
          status: 401,
          headers: { 'Content-Type': 'application/json', ...corsHeaders },
        }
      );
    }

    const clientToken = match[1].trim().replace(/^["']|["']$/g, '');
    if (clientToken !== secret) {
      return new Response(
        JSON.stringify({
          error: 'Unauthorized: Bearer token does not match configured secret',
          success: false,
        }),
        {
          status: 401,
          headers: { 'Content-Type': 'application/json', ...corsHeaders },
        }
      );
    }

    // Endpoint: GET /api/topics/processed (List all processed topics from D1)
    if (pathname === '/api/topics/processed' && request.method === 'GET') {
      if (!env.DB) {
        return new Response(
          JSON.stringify({ error: "D1 database binding 'DB' is not configured or unavailable", success: false }),
          {
            status: 503,
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          }
        );
      }

      try {
        const result = await env.DB.prepare(
          'SELECT id as topic_id, topic_title, fingerprint, category, post_id, post_url, publish_mode, created_at FROM processed_topics ORDER BY created_at DESC LIMIT 200'
        ).all();

        const records = (result.results || []).map((row: any) => ({
          topic_id: row.topic_id || row.id,
          topic_title: row.topic_title,
          fingerprint: row.fingerprint,
          category: row.category,
          post_id: row.post_id,
          post_url: row.post_url,
          publish_mode: row.publish_mode,
          created_at: row.created_at,
        }));

        return new Response(
          JSON.stringify({
            success: true,
            processed: records,
            total: records.length,
            d1_available: true,
          }),
          {
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          }
        );
      } catch (err: any) {
        return new Response(
          JSON.stringify({ error: `Database query failed: ${err.message}`, success: false }),
          {
            status: 500,
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          }
        );
      }
    }

    // Endpoint: POST /api/topics/record (Directly save or update a processed topic in D1)
    if ((pathname === '/api/topics/record' || pathname === '/api/topics/processed') && request.method === 'POST') {
      if (!env.DB) {
        return new Response(
          JSON.stringify({ error: "D1 database binding 'DB' is not configured or unavailable", success: false }),
          {
            status: 503,
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          }
        );
      }

      try {
        const body: any = await request.json();
        const topic_id = body.topic_id || body.id;
        const topic_title = body.topic_title || body.title || topic_id;
        const fingerprint = body.fingerprint || (topic_id ? `id:${topic_id}` : null);
        const category = body.category || 'General';
        const post_id = body.post_id || body.blogger?.post_id || null;
        const post_url = body.post_url || body.blogger?.post_url || null;
        const publish_mode = body.publish_mode || 'draft';

        if (!topic_id) {
          return new Response(
            JSON.stringify({ error: 'Missing required field: topic_id', success: false }),
            {
              status: 400,
              headers: { 'Content-Type': 'application/json', ...corsHeaders },
            }
          );
        }

        await env.DB.prepare(
          `INSERT OR REPLACE INTO processed_topics (id, topic_title, fingerprint, category, post_id, post_url, publish_mode, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
        )
          .bind(topic_id, topic_title, fingerprint, category, post_id, post_url, publish_mode)
          .run();

        return new Response(
          JSON.stringify({ success: true, topic_id, message: 'Processed topic recorded successfully in D1' }),
          {
            status: 200,
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          }
        );
      } catch (err: any) {
        return new Response(
          JSON.stringify({ error: `Database insert failed: ${err.message}`, success: false }),
          {
            status: 500,
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          }
        );
      }
    }

    // Endpoint: POST /api/runs/record (Record pipeline execution into D1)
    if (pathname === '/api/runs/record' && request.method === 'POST') {
      if (!env.DB) {
        return new Response(
          JSON.stringify({ error: "D1 database binding 'DB' is not configured or unavailable", success: false }),
          {
            status: 503,
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          }
        );
      }

      try {
        const body: any = await request.json();
        const run_id = body.run_id || `run-${Date.now()}`;
        const overall_status = (body.overall_status || body.status || 'UNKNOWN').toUpperCase();
        const selected_topic = body.selected_topic || body.topic_title || body.topic || null;
        const selected_topic_id = body.selected_topic_id || body.topic_id || null;
        const total_duration_seconds = Number(body.total_duration_seconds ?? body.duration_seconds ?? 0);
        const dry_run = Boolean(body.dry_run);
        const publish_mode = body.publish_mode || (body.is_draft === false ? 'publish' : 'draft');
        const post_id = body.blogger?.post_id || body.post_id || null;
        const post_url = body.blogger?.post_url || body.post_url || null;
        const category = body.category || 'Artificial Intelligence and AI Tools';
        const fingerprint = body.fingerprint || (selected_topic_id ? `id:${selected_topic_id}` : null);

        // 1. Record pipeline run execution telemetry
        await env.DB.prepare(
          `INSERT INTO pipeline_runs (run_id, overall_status, selected_topic, total_duration_seconds, dry_run, publish_mode, post_id, post_url, report_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
        )
          .bind(
            run_id,
            overall_status,
            selected_topic,
            total_duration_seconds,
            dry_run ? 1 : 0,
            publish_mode,
            post_id,
            post_url,
            JSON.stringify(body)
          )
          .run();

        // 2. If topic was successfully processed and not a dry run, record in processed_topics
        let recorded_topic = false;
        if (overall_status === 'SUCCESS' && !dry_run && selected_topic_id) {
          await env.DB.prepare(
            `INSERT OR REPLACE INTO processed_topics (id, topic_title, fingerprint, category, post_id, post_url, publish_mode, created_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
          )
            .bind(
              selected_topic_id,
              selected_topic || selected_topic_id,
              fingerprint || `id:${selected_topic_id}`,
              category,
              post_id,
              post_url,
              publish_mode
            )
            .run();
          recorded_topic = true;
        }

        return new Response(
          JSON.stringify({
            success: true,
            run_id,
            recorded_run: true,
            recorded_topic,
          }),
          {
            status: 200,
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          }
        );
      } catch (err: any) {
        return new Response(
          JSON.stringify({ error: `Failed to record pipeline run: ${err.message}`, success: false }),
          {
            status: 500,
            headers: { 'Content-Type': 'application/json', ...corsHeaders },
          }
        );
      }
    }

    return new Response(JSON.stringify({ error: 'Endpoint not found', success: false }), {
      status: 404,
      headers: { 'Content-Type': 'application/json', ...corsHeaders },
    });
  },
};

