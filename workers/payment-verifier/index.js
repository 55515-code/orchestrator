// payment-verifier — on-chain payment verification for digital resources.
//
// Security rules (see crypto-rules.yaml, docs/CRYPTO_PAYMENT_RUNBOOK.md):
//  - No secrets live here: only PUBLIC payment/donation addresses.
//  - Multiple RPC providers with fallback (PF-007).
//  - Replay protection via D1 primary key on tx_hash.
//  - IP-based rate limiting on every public endpoint (PF-006).
//  - Confirmation depth check before issuing delivery tokens.

const ERC20_TRANSFER_TOPIC =
  '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef';

const TOKEN_DECIMALS = { USDC: 6, DAI: 18, POL: 18, ETH: 18 };
const STABLE_TOKENS = new Set(['USDC', 'DAI']);

const json = (payload, status = 200) =>
  new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json', 'access-control-allow-origin': '*' },
  });

async function rpcCall(rpcUrls, method, params) {
  let lastError = 'no RPC providers configured';
  for (const url of rpcUrls) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
      });
      if (!response.ok) {
        lastError = `RPC HTTP ${response.status}`;
        continue;
      }
      const payload = await response.json();
      if (payload.error) {
        lastError = payload.error.message || 'RPC error';
        continue;
      }
      return payload.result;
    } catch (error) {
      lastError = String(error);
    }
  }
  throw new Error(`all RPC providers failed: ${lastError}`);
}

function rpcUrlsFromEnv(env, network = 'polygon') {
  const perNetwork = network === 'base' ? env.RPC_URLS_BASE : env.RPC_URLS_POLYGON;
  const raw = [perNetwork, env.RPC_URLS, env.RPC_URL].filter(Boolean).join(',');
  return raw
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
}

async function rateLimited(env, ip) {
  const limit = Number(env.RATE_LIMIT_PER_HOUR || 60);
  const window = new Date(Math.floor(Date.now() / 3600000) * 3600000).toISOString();
  const key = `${ip}:${window}`;
  const row = await env.DB.prepare('SELECT count FROM rate_limits WHERE key = ?')
    .bind(key)
    .first();
  const count = row ? Number(row.count) : 0;
  if (count >= limit) return true;
  await env.DB.prepare(
    'INSERT INTO rate_limits (key, count) VALUES (?, ?) ' +
      'ON CONFLICT(key) DO UPDATE SET count = count + 1',
  )
    .bind(key, count + 1)
    .run();
  return false;
}

function hexToBigInt(value) {
  if (value === null || value === undefined) return 0n;
  return BigInt(value);
}

async function fetchTransaction(rpcUrls, txHash) {
  const [tx, receipt, blockNumber] = await Promise.all([
    rpcCall(rpcUrls, 'eth_getTransactionByHash', [txHash]),
    rpcCall(rpcUrls, 'eth_getTransactionReceipt', [txHash]),
    rpcCall(rpcUrls, 'eth_blockNumber', []),
  ]);
  if (!tx || !receipt) return null;
  return { tx, receipt, confirmations: Number(hexToBigInt(blockNumber) - hexToBigInt(tx.blockNumber)) };
}

function erc20TransferToRecipient(receipt, paymentAddress) {
  const target = paymentAddress.toLowerCase();
  for (const log of receipt.logs || []) {
    if ((log.topics || [])[0] !== ERC20_TRANSFER_TOPIC) continue;
    const toTopic = (log.topics[2] || '').toLowerCase();
    if (toTopic.endsWith(target.replace(/^0x/, ''))) {
      return hexToBigInt(log.data);
    }
  }
  return null;
}

async function verifyPayment(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'invalid JSON body' }, 400);
  }
  const { txHash, resourceId, token = 'USDC', network = 'polygon' } = body || {};
  if (!txHash || !resourceId) {
    return json({ error: 'txHash and resourceId are required' }, 400);
  }

  const rpcUrls = rpcUrlsFromEnv(env, network);
  if (rpcUrls.length < 2) {
    return json({ error: 'server misconfigured: RPC fallback requires >= 2 providers' }, 503);
  }

  const existing = await env.DB.prepare('SELECT * FROM payments WHERE tx_hash = ?')
    .bind(txHash)
    .first();
  if (existing) {
    return json({ error: 'transaction already processed', verified: false }, 409);
  }

  const resource = await env.DB.prepare('SELECT * FROM resources WHERE id = ?')
    .bind(resourceId)
    .first();
  if (!resource) return json({ error: 'unknown resource' }, 404);
  if (Number(resource.price_usdc) === 0) {
    return json({ error: 'resource is free; use the delivery worker free-token endpoint' }, 400);
  }

  let chain;
  try {
    chain = await fetchTransaction(rpcUrls, txHash);
  } catch (error) {
    return json({ error: `rpc failure: ${error.message}` }, 503);
  }
  if (!chain) return json({ verified: false, reason: 'transaction not found' }, 404);

  const minConfirmations = Number(env.MIN_CONFIRMATIONS || 10);
  if (chain.confirmations < minConfirmations) {
    return json(
      { verified: false, reason: `insufficient confirmations (${chain.confirmations})` },
      425,
    );
  }
  if (chain.receipt.status !== '0x1') {
    return json({ verified: false, reason: 'transaction reverted' }, 422);
  }

  const decimals = TOKEN_DECIMALS[token.toUpperCase()] ?? 18;
  const required = BigInt(Math.ceil(Number(resource.price_usdc) * 10 ** decimals));

  if (STABLE_TOKENS.has(token.toUpperCase())) {
    const transferred = erc20TransferToRecipient(chain.receipt, env.PAYMENT_ADDRESS);
    if (transferred === null || transferred < required) {
      return json({ verified: false, reason: 'insufficient or missing ERC-20 transfer' }, 402);
    }
  } else {
    if ((chain.tx.to || '').toLowerCase() !== env.PAYMENT_ADDRESS.toLowerCase()) {
      return json({ verified: false, reason: 'invalid recipient' }, 402);
    }
    const rateEnv = Number(env.POL_USD || 0);
    if (!rateEnv) {
      return json({ error: 'no USD rate configured for volatile token pricing' }, 503);
    }
    const requiredNative = BigInt(
      Math.floor((Number(resource.price_usdc) / rateEnv) * 10 ** decimals),
    );
    if (hexToBigInt(chain.tx.value) < requiredNative) {
      return json({ verified: false, reason: 'insufficient amount' }, 402);
    }
  }

  const deliveryToken = crypto.randomUUID();
  const expiresAt = new Date(Date.now() + 24 * 3600 * 1000).toISOString();
  await env.DB.prepare(
    'INSERT INTO payments (tx_hash, resource_id, payer, token, amount, network, status, verified_at, delivery_token) ' +
      'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
  )
    .bind(
      txHash,
      resourceId,
      chain.tx.from || '',
      token.toUpperCase(),
      String(chain.tx.value || ''),
      network,
      'verified',
      new Date().toISOString(),
      deliveryToken,
    )
    .run();
  await env.DB.prepare(
    'INSERT INTO delivery_tokens (token, resource_id, resource_path, expires_at, used) VALUES (?, ?, ?, ?, 0)',
  )
    .bind(deliveryToken, resourceId, resource.resource_path, expiresAt)
    .run();

  return json({ verified: true, deliveryToken, expires_at: expiresAt });
}

async function paymentStatus(request, env) {
  const url = new URL(request.url);
  const txHash = url.searchParams.get('tx');
  if (!txHash) return json({ error: 'tx query parameter required' }, 400);
  const row = await env.DB.prepare('SELECT tx_hash, resource_id, status, verified_at FROM payments WHERE tx_hash = ?')
    .bind(txHash)
    .first();
  if (!row) return json({ found: false }, 404);
  return json({ found: true, ...row });
}

async function donationInfo(env) {
  const rows = await env.DB.prepare('SELECT network, token, address FROM donation_addresses').all();
  const networks = {};
  for (const row of rows.results || []) {
    networks[row.network] = networks[row.network] || { network: row.network, tokens: [] };
    networks[row.network].tokens.push({ symbol: row.token, address: row.address });
  }
  return json({
    networks: Object.values(networks),
    note: 'Donations are welcome and fund free resources. No goods or services are exchanged.',
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const ip = request.headers.get('cf-connecting-ip') || 'unknown';

    if (url.pathname === '/api/health') {
      return json({ ok: true, service: 'payment-verifier' });
    }

    try {
      if (await rateLimited(env, ip)) {
        return json({ error: 'rate limit exceeded' }, 429);
      }
    } catch {
      // Rate-limit bookkeeping failures must not block payments.
    }

    if (url.pathname === '/api/verify-payment' && request.method === 'POST') {
      return verifyPayment(request, env);
    }
    if (url.pathname === '/api/payment-status' && request.method === 'GET') {
      return paymentStatus(request, env);
    }
    if (url.pathname === '/api/donation-info' && request.method === 'GET') {
      return donationInfo(env);
    }
    return json({ error: 'not found' }, 404);
  },
};
