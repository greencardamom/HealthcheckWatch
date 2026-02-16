/* * Copyright (C) 2026 greencardamom
 * Licensed under the GNU AGPLv3. See LICENSE file for details.
 */

export default {
  // ========================================================================
  // 1. HTTP HANDLER (Receives Pings & Serves the Outbox)
  // ========================================================================
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    // SECURITY: Reject any request without the correct API_TOKEN
    const authHeader = request.headers.get('Authorization');
    const queryToken = url.searchParams.get('token');
    if (authHeader !== `Bearer ${env.API_TOKEN}` && queryToken !== env.API_TOKEN) {
      return new Response('Unauthorized', { status: 401 });
    }

    // --- ROUTE: POST/GET /ping/:id ---
    // Registers a script or updates its last seen time
    if ((request.method === 'POST' || request.method === 'GET') && path.startsWith('/ping/')) {
      const id = path.split('/')[2];
      
      // Default settings (Overridden by URL query parameters if present)
      let timeout = url.searchParams.get('t') || 13;
      let subject = url.searchParams.get('s') || null;
      let body = url.searchParams.get('b') || null;
      
      // If the bash script sent a JSON Last Will and Testament, parse it
      if (request.headers.get('content-type')?.includes('application/json')) {
        const data = await request.json();
        if (data.timeout !== undefined) timeout = data.timeout;
        if (data.subject !== undefined) subject = data.subject;
        if (data.body !== undefined) body = data.body;
      }

      const now = Math.floor(Date.now() / 1000); // Unix timestamp in seconds

      // Upsert: Insert new script, or update existing script's timer
      await env.DB.prepare(`
        INSERT INTO monitors (id, last_ping, timeout_hours, alert_subject, alert_body) 
        VALUES (?, ?, ?, ?, ?) 
        ON CONFLICT(id) DO UPDATE SET 
          last_ping = excluded.last_ping, 
          timeout_hours = excluded.timeout_hours, 
          alert_subject = excluded.alert_subject, 
          alert_body = excluded.alert_body
      `).bind(id, now, timeout, subject, body).run();

      return new Response(`[DONE] Heartbeat logged for monitor: ${id}`);
    }

    // --- ROUTE: GET /outbox ---
    // Your local polling script calls this to download pending alerts
    if (request.method === 'GET' && path === '/outbox') {
      const { results } = await env.DB.prepare('SELECT * FROM outbox').all();
      return new Response(JSON.stringify(results), { 
        headers: { 'Content-Type': 'application/json' } 
      });
    }

    // --- ROUTE: DELETE /outbox ---
    // Your local polling script calls this after successfully sending the emails
    if (request.method === 'DELETE' && path === '/outbox') {
      await env.DB.prepare('DELETE FROM outbox').run();
      return new Response('[DONE] Outbox cleared');
    }

    // Fallback for bad URLs
    return new Response('Not Found', { status: 404 });
  },


  // ========================================================================
  // 2. CRON WATCHDOG (Runs automatically every hour)
  // ========================================================================
  async scheduled(event, env, ctx) {
    const now = Math.floor(Date.now() / 1000);
    
    // Find all monitors where the elapsed time exceeds their timeout window
    const query = `SELECT * FROM monitors WHERE (? - last_ping) > (timeout_hours * 3600)`;
    const { results: deadMonitors } = await env.DB.prepare(query).bind(now).all();

    if (deadMonitors.length === 0) return;

    const stmts = [];
    
    for (const monitor of deadMonitors) {
      // Helper to format Unix Epoch to readable string
      const fmt = (epoch) => new Date(epoch * 1000).toISOString().replace('T', ' ').split('.')[0];
      
      const lastPingStr = fmt(monitor.last_ping);
      const expectedDeathStr = fmt(monitor.last_ping + (monitor.timeout_hours * 3600));

      // Build the diagnostic table for THIS specific failure
      const evidence = 
        `MONITOR ID                     | LAST PING (UTC)      | DEATH DATE (UTC)\n` +
        `---------------------------------------------------------------------------\n` +
        `${monitor.id.padEnd(30)} | ${lastPingStr} | ${expectedDeathStr}\n`;

      const subject = monitor.alert_subject || `CRITICAL: Watchdog Timeout - ${monitor.id}`;
      
      // Append the diagnostic table to the body
      const baseBody = monitor.alert_body || `The monitor '${monitor.id}' has not checked in for over ${monitor.timeout_hours} hours.`;
      const finalBody = `${baseBody}\n\n${evidence}`;
      
      // Step A: Insert the alert into the outbox
      stmts.push(env.DB.prepare('INSERT INTO outbox (subject, body) VALUES (?, ?)').bind(subject, finalBody));
      
      // Step B: Delete the dead monitor to prevent alert spamming
      stmts.push(env.DB.prepare('DELETE FROM monitors WHERE id = ?').bind(monitor.id));
    }

    await env.DB.batch(stmts);
  }

};
