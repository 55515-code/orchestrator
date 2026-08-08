// resource-delivery — token-gated delivery of digital resources.
//
// Security rules (see crypto-rules.yaml, docs/CRYPTO_PAYMENT_RUNBOOK.md):
//  - Delivery tokens are one-time use and expire.
//  - Free resources (price_usdc = 0) get rate-limited tokens with no payment.
//  - Responses include the resource checksum for client-side verification.
//  - IP-based rate limiting on every public endpoint.
//
// Resources are shipped as Workers static assets (R2 is not enabled on this
// account). The delivery path is isolated so R2 can be swapped in later.

const json = (payload, status = 200) =>
  new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json', 'access-control-allow-origin': '*' },
  });

async function rateLimited(env, ip, limitPerHour = 30) {
  const window = new Date(Math.floor(Date.now() / 3600000) * 3600000).toISOString();
  const key = `delivery:${ip}:${window}`;
  const row = await env.DB.prepare('SELECT count FROM rate_limits WHERE key = ?')
    .bind(key)
    .first();
  const count = row ? Number(row.count) : 0;
  if (count >= limitPerHour) return true;
  await env.DB.prepare(
    'INSERT INTO rate_limits (key, count) VALUES (?, ?) ' +
      'ON CONFLICT(key) DO UPDATE SET count = count + 1',
  )
    .bind(key, count + 1)
    .run();
  return false;
}

async function issueFreeToken(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'invalid JSON body' }, 400);
  }
  const { resourceId } = body || {};
  if (!resourceId) return json({ error: 'resourceId is required' }, 400);

  const resource = await env.DB.prepare('SELECT * FROM resources WHERE id = ?')
    .bind(resourceId)
    .first();
  if (!resource) return json({ error: 'unknown resource' }, 404);
  if (Number(resource.price_usdc) !== 0) {
    return json({ error: 'resource is not free; payment required' }, 402);
  }

  const token = crypto.randomUUID();
  const expiresAt = new Date(Date.now() + 3600 * 1000).toISOString();
  await env.DB.prepare(
    'INSERT INTO delivery_tokens (token, resource_id, resource_path, expires_at, used) VALUES (?, ?, ?, ?, 0)',
  )
    .bind(token, resourceId, resource.resource_path, expiresAt)
    .run();
  return json({ deliveryToken: token, expires_at: expiresAt, free: true });
}

async function deliverResource(request, env, resourceId) {
  const deliveryToken = request.headers.get('x-delivery-token');
  const resource = await env.DB.prepare('SELECT * FROM resources WHERE id = ?')
    .bind(resourceId)
    .first();

  if (!deliveryToken) {
    // x402-style payment-required contract for autonomous agent buyers.
    if (resource && Number(resource.price_usdc) === 0) {
      return json({ error: 'resource is free; POST /api/free-token for a delivery token' }, 402);
    }
    if (resource) {
      return json(
        {
          error: 'payment required',
          payment: {
            resource_id: resourceId,
            amount_usdc: Number(resource.price_usdc),
            tokens: ['USDC', 'DAI'],
            networks: ['polygon', 'base'],
            verify_endpoint: '/api/verify-payment',
            verify_method: 'POST',
            delivery_endpoint: `/api/resource/${resourceId}`,
            delivery_header: 'X-Delivery-Token',
          },
        },
        402,
      );
    }
    return json({ error: 'unknown resource' }, 404);
  }

  const row = await env.DB.prepare(
    'SELECT * FROM delivery_tokens WHERE token = ? AND resource_id = ?',
  )
    .bind(deliveryToken, resourceId)
    .first();

  if (!row) return json({ error: 'invalid token' }, 401);
  if (row.used) return json({ error: 'token already used' }, 401);
  if (new Date(row.expires_at) < new Date()) {
    return json({ error: 'token expired' }, 401);
  }

  const resourceUrl = new URL(`/${row.resource_path}`, 'https://assets.local');
  const asset = await env.ASSETS.fetch(resourceUrl.toString());
  if (!asset || asset.status === 404) {
    return json({ error: 'resource file missing' }, 404);
  }

  await env.DB.prepare('UPDATE delivery_tokens SET used = 1, used_at = ? WHERE token = ?')
    .bind(new Date().toISOString(), deliveryToken)
    .run();

  const filename = row.resource_path.split('/').pop() || 'resource';
  return new Response(asset.body, {
    status: 200,
    headers: {
      'content-type':
        asset.headers.get('content-type') || 'text/plain; charset=utf-8',
      'content-disposition': `attachment; filename="${filename}"`,
      'x-resource-checksum': resource?.checksum || '',
      'x-resource-version': resource?.version || '',
    },
  });
}

async function publicCatalog(env) {
  const rows = await env.DB.prepare(
    'SELECT id, title, category, price_usdc, version FROM resources ORDER BY category, id',
  ).all();
  return json({
    resources: (rows.results || []).map((row) => ({
      ...row,
      free: Number(row.price_usdc) === 0,
    })),
  });
}

// llms.txt-style machine catalog for LLM/agent discovery (PF-014).
async function llmsCatalog(env) {
  const rows = await env.DB.prepare(
    'SELECT id, title, category, price_usdc FROM resources ORDER BY category, id',
  ).all();
  const lines = [
    '# 1pointo digital resources',
    '',
    '> Programmatic catalog for bots and agents. Pay with USDC/DAI (Polygon or Base).',
    '> Verify payment: POST /api/verify-payment on payment-verifier. Deliver via',
    '> /api/free-token (free items) or X-Delivery-Token (paid items).',
    '',
  ];
  for (const row of rows.results || []) {
    const price =
      Number(row.price_usdc) === 0 ? 'FREE' : `$${row.price_usdc.toFixed(0)} USDC`;
    lines.push(`[${row.id}] (${price}) ${row.title} — category: ${row.category}`);
    lines.push(`  - id: ${row.id}`);
    lines.push(`  - delivery: https://${env.DELIVERY_HOST}/api/resource/${row.id}`);
    lines.push('');
  }
  return new Response(lines.join('\n'), {
    headers: { 'content-type': 'text/plain; charset=utf-8' },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const ip = request.headers.get('cf-connecting-ip') || 'unknown';

    if (url.pathname === '/api/health') {
      return json({ ok: true, service: 'resource-delivery' });
    }

    try {
      if (await rateLimited(env, ip)) {
        return json({ error: 'rate limit exceeded' }, 429);
      }
    } catch {
      // Rate-limit bookkeeping failures must not block delivery.
    }

    if (url.pathname === '/api/free-token' && request.method === 'POST') {
      return issueFreeToken(request, env);
    }
    if (url.pathname === '/api/catalog' && request.method === 'GET') {
      return publicCatalog(env);
    }
    if (url.pathname === '/api/llms' && request.method === 'GET') {
      return llmsCatalog(env);
    }
    if (url.pathname.startsWith('/api/resource/') && request.method === 'GET') {
      const resourceId = decodeURIComponent(url.pathname.split('/').pop() || '');
      if (!resourceId) return json({ error: 'resource id required' }, 400);
      return deliverResource(request, env, resourceId);
    }
    return json({ error: 'not found' }, 404);
  },
};
