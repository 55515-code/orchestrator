// Worker test harness — imports the resource-delivery worker with stubbed
// D1 and R2 bindings and exercises the free-token / 402 / delivery flows.
//
// Run: node workers/test/run-tests.mjs
import { test, run } from './harness.mjs';
import deliveryWorker from '../resource-delivery/index.js';
import paymentWorker from '../payment-verifier/index.js';

function memoryDB() {
  const tables = {
    resources: [
      {
        id: 'free-item',
        title: 'Free Checklist',
        category: 'security',
        price_usdc: 0,
        resource_path: 'resources/security/free-item.md',
        checksum: 'sha256:abc',
        version: '1.0',
      },
      {
        id: 'paid-item',
        title: 'Paid Guide',
        category: 'compliance',
        price_usdc: 50,
        resource_path: 'resources/compliance/paid-item.md',
        checksum: 'sha256:def',
        version: '1.0',
      },
    ],
    payments: [],
    delivery_tokens: [],
    donation_addresses: [{ network: 'polygon', token: 'USDC', address: '0xDonate' }],
    rate_limits: [],
  };
  return {
    prepare(sql) {
      const stmt = {
        bind(...args) {
          return {
            run: () => stmt._run(...args),
            first: () => stmt._first(...args),
            all: () => stmt._all(...args),
          };
        },
        run: (...args) => stmt._run(...args),
        first: (...args) => stmt._first(...args),
        all: (...args) => stmt._all(...args),
      };
      const select = sql.includes('SELECT');
      const from = (sql.match(/FROM\s+(\w+)/) || [])[1];
      const whereMatch = sql.match(/WHERE\s+(\w+)\s*=\s*\?/);
      stmt._run = async (...args) => {
        if (sql.startsWith('INSERT') || sql.startsWith('UPDATE')) {
          if (sql.includes('rate_limits')) {
            const key = args[0];
            const existing = tables.rate_limits.find((r) => r.key === key);
            if (existing) existing.count += 1;
            else tables.rate_limits.push({ key, count: 1 });
          }
          if (sql.includes('delivery_tokens') && sql.includes('UPDATE')) {
            const token = args[args.length - 1];
            const row = tables.delivery_tokens.find((t) => t.token === token);
            if (row) row.used = 1;
          }
          if (sql.includes('delivery_tokens') && sql.startsWith('INSERT')) {
            tables.delivery_tokens.push({
              token: args[0],
              resource_id: args[1],
              resource_path: args[2],
              expires_at: args[3],
              used: args[4] ?? 0,
            });
          }
        }
        return {};
      };
      stmt._first = async (...args) => {
        if (!from) return null;
        const rows = tables[from] || [];
        if (whereMatch) {
          const col = whereMatch[1];
          const value = args[0];
          return rows.find((r) => String(r[col]) === String(value)) || null;
        }
        return rows[0] || null;
      };
      stmt._all = async () => ({ results: tables[from] || [] });
      return stmt;
    },
    // Overridden per-test via withTables
    async withTables(set) {
      Object.assign(tables, set);
    },
    tables,
  };
}

function memoryAssets() {
  const files = new Map([
    ['resources/security/free-item.md', '# Free Checklist\n'],
    ['resources/compliance/paid-item.md', '# Paid Guide\n'],
  ]);
  return {
    async fetch(url) {
      const path = new URL(url).pathname.replace(/^\//, '');
      const body = files.get(path);
      if (body === undefined) return new Response('not found', { status: 404 });
      return new Response(body, { headers: { 'content-type': 'text/markdown' } });
    },
  };
}

test('free-token issues a token for a free resource', async () => {
  const db = memoryDB();
  const env = { DB: db, ASSETS: memoryAssets(), RATE_LIMIT_PER_HOUR: '30', DELIVERY_HOST: 'delivery.example' };
  const request = new Request('http://delivery.example/api/free-token', {
    method: 'POST',
    body: JSON.stringify({ resourceId: 'free-item' }),
  });
  const response = await deliveryWorker.fetch(request, env);
  if (response.status !== 200) throw new Error(`status ${response.status}`);
  const payload = await response.json();
  if (!payload.deliveryToken) throw new Error('no delivery token issued');
  if (!payload.free) throw new Error('free flag missing');
});

test('free-token refuses a paid resource', async () => {
  const db = memoryDB();
  const env = { DB: db, ASSETS: memoryAssets(), RATE_LIMIT_PER_HOUR: '30' };
  const request = new Request('http://delivery.example/api/free-token', {
    method: 'POST',
    body: JSON.stringify({ resourceId: 'paid-item' }),
  });
  const response = await deliveryWorker.fetch(request, env);
  if (response.status !== 402) throw new Error(`expected 402, got ${response.status}`);
});

test('paid resource without token returns 402 payment contract', async () => {
  const db = memoryDB();
  const env = { DB: db, ASSETS: memoryAssets(), RATE_LIMIT_PER_HOUR: '30' };
  const request = new Request('http://delivery.example/api/resource/paid-item');
  const response = await deliveryWorker.fetch(request, env);
  if (response.status !== 402) throw new Error(`expected 402, got ${response.status}`);
  const payload = await response.json();
  if (payload.payment.amount_usdc !== 50) throw new Error('wrong amount in payment contract');
  if (payload.payment.verify_endpoint !== '/api/verify-payment') throw new Error('missing verify endpoint');
});

test('free resource without token also returns 402 with guidance', async () => {
  const db = memoryDB();
  const env = { DB: db, ASSETS: memoryAssets(), RATE_LIMIT_PER_HOUR: '30' };
  const request = new Request('http://delivery.example/api/resource/free-item');
  const response = await deliveryWorker.fetch(request, env);
  if (response.status !== 402) throw new Error(`expected 402, got ${response.status}`);
});

test('delivery consumes one-time token and returns signed URL', async () => {
  const db = memoryDB();
  db.tables.delivery_tokens.push({
    token: 'tok-1',
    resource_id: 'free-item',
    resource_path: 'resources/security/free-item.md',
    expires_at: new Date(Date.now() + 3600_000).toISOString(),
    used: 0,
  });
  const env = { DB: db, ASSETS: memoryAssets(), RATE_LIMIT_PER_HOUR: '30' };
  const request = new Request('http://delivery.example/api/resource/free-item', {
    headers: { 'x-delivery-token': 'tok-1' },
  });
  const response = await deliveryWorker.fetch(request, env);
  if (response.status !== 200) throw new Error(`status ${response.status}`);
  const body = await response.text();
  if (!body.includes('Free Checklist')) throw new Error('asset body missing');
  if (!response.headers.get('x-resource-checksum')) throw new Error('checksum header missing');
  const row = db.tables.delivery_tokens.find((t) => t.token === 'tok-1');
  if (row.used !== 1) throw new Error('token was not marked used');
});

test('payment verifier exposes donation info', async () => {
  const db = memoryDB();
  const env = { DB: db, RATE_LIMIT_PER_HOUR: '60', RPC_URLS: 'https://a.example,https://b.example' };
  const request = new Request('http://pay.example/api/donation-info');
  const response = await paymentWorker.fetch(request, env);
  if (response.status !== 200) throw new Error(`status ${response.status}`);
  const payload = await response.json();
  if (payload.networks.length !== 1 || payload.networks[0].network !== 'polygon') {
    throw new Error('donation info wrong');
  }
});

test('payment verifier requires at least two RPC providers', async () => {
  const db = memoryDB();
  const env = { DB: db, RATE_LIMIT_PER_HOUR: '60', RPC_URLS: 'https://only-one.example' };
  const request = new Request('http://pay.example/api/verify-payment', {
    method: 'POST',
    body: JSON.stringify({ txHash: '0x1', resourceId: 'paid-item' }),
  });
  const response = await paymentWorker.fetch(request, env);
  if (response.status !== 503) throw new Error(`expected 503, got ${response.status}`);
});

test('health endpoints respond', async () => {
  const env = { DB: memoryDB(), ASSETS: memoryAssets(), RATE_LIMIT_PER_HOUR: '30' };
  const deliveryHealth = await deliveryWorker.fetch(new Request('http://delivery.example/api/health'), env);
  const paymentHealth = await paymentWorker.fetch(
    new Request('http://pay.example/api/health'),
    { ...env, RPC_URLS: 'https://a.example,https://b.example' },
  );
  if (deliveryHealth.status !== 200 || paymentHealth.status !== 200) {
    throw new Error('health check failed');
  }
});

run();
