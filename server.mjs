// Stand-in local server.
// Serves index.html and runs the synthetic participants through Claude with the official Anthropic SDK.
//
// Sign in once, then start it:
//   ant auth login        (OAuth through your Anthropic Console account; the SDK picks the login up by itself)
//   npm install && npm start
// An ANTHROPIC_API_KEY in the environment also works, and wins over the login if both are present.
//
// Everything spent is priced and added to .standin/usage.json; finished runs are saved in .standin/results/.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Anthropic from '@anthropic-ai/sdk';

const here = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT) || 5174;
const HOST = '127.0.0.1';
const DATA = process.env.STANDIN_DATA || path.join(here, '.standin');
const RESULTS = path.join(DATA, 'results');
const USAGE = path.join(DATA, 'usage.json');
fs.mkdirSync(RESULTS, { recursive: true });

/* Dollars per million tokens, Anthropic API list prices. Haiku 5.5 costs more once a prompt passes 100K tokens.
   Sonnet 5.5 and Opus 5.5 get the server-side refusal fallback, which Haiku 5.5 does not have. */
const MODELS = {
  'claude-haiku-5-5': { name: 'Haiku 5.5', in: 0.10, out: 0.50, longIn: 0.50, longOut: 2.50 },
  'claude-sonnet-5-5': { name: 'Sonnet 5.5', in: 2, out: 10, fallbacks: true },
  'claude-opus-5-5': { name: 'Opus 5.5', in: 4, out: 20, fallbacks: true }
};
const EFFORTS = ['low', 'medium', 'high'];

function price(id, u) {
  const p = MODELS[id] || MODELS['claude-haiku-5-5'];
  const write = u.cache_creation_input_tokens || 0, read = u.cache_read_input_tokens || 0, input = u.input_tokens || 0;
  const long = p.longIn && input + write + read > 100000, inR = long ? p.longIn : p.in, outR = long ? p.longOut : p.out;
  /* this app sends no cache_control, so the cache terms stay at zero; they are priced at the standard multipliers in case */
  return (input * inR + write * inR * 1.25 + read * inR * 0.1 + (u.output_tokens || 0) * outR) / 1e6;
}

/* ---------- spend tracker ---------- */
const fresh = () => ({ since: new Date().toISOString(), calls: 0, input: 0, output: 0, cost: 0, byModel: {} });
let totals = fresh();
try { totals = { ...fresh(), ...JSON.parse(fs.readFileSync(USAGE, 'utf8')) }; } catch { /* first run */ }
let saveTimer = null;
const saveTotals = () => { clearTimeout(saveTimer); saveTimer = setTimeout(() => fs.writeFile(USAGE, JSON.stringify(totals, null, 2), () => {}), 400); };
function record(model, u, cost, calls) {
  const m = totals.byModel[model] ??= { calls: 0, input: 0, output: 0, cost: 0 };
  for (const t of [totals, m]) {
    t.calls += calls;
    t.input += (u.input_tokens || 0) + (u.cache_creation_input_tokens || 0) + (u.cache_read_input_tokens || 0);
    t.output += u.output_tokens || 0;
    t.cost += cost;
  }
  saveTotals();
}

/* ---------- the Anthropic client ---------- */
let client = null;
let conn = { connected: false, auth: '', error: '', checked: 0 };
const authSource = () => process.env.ANTHROPIC_API_KEY ? 'API key (ANTHROPIC_API_KEY)'
  : process.env.ANTHROPIC_AUTH_TOKEN ? 'auth token (ANTHROPIC_AUTH_TOKEN)' : 'your Anthropic login (ant auth login)';
async function connect() {
  try {
    client = new Anthropic(); /* resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, then the `ant auth login` profile */
    await client.models.retrieve('claude-haiku-5-5');
    conn = { connected: true, auth: authSource(), error: '', checked: Date.now() };
  } catch (e) {
    client = null;
    conn = { connected: false, auth: authSource(), error: friendly(e), checked: Date.now() };
  }
  return conn;
}
function friendly(e) {
  if (e instanceof Anthropic.AuthenticationError || e instanceof Anthropic.PermissionDeniedError) return 'Your login was not accepted. Run ant auth login again.';
  if (e instanceof Anthropic.RateLimitError) return 'Rate limited by the API. Slowing down.';
  if (e instanceof Anthropic.APIConnectionError) return 'Could not reach the Anthropic API.';
  if (e instanceof Anthropic.APIError) return e.message;
  const msg = (e && e.message) || String(e);
  return /auth|api.?key|credential/i.test(msg) ? 'Not signed in. Run ant auth login (or set ANTHROPIC_API_KEY), then check again.' : msg;
}

/* One conversation: each turn is a user message answered as JSON that matches its schema.
   The full assistant content, thinking blocks included, goes back unchanged before the next turn. */
async function chat(body) {
  const model = Object.hasOwn(MODELS, body.model) ? body.model : null;
  if (!model) throw Object.assign(new Error('Unknown model'), { status: 400 });
  const effort = EFFORTS.includes(body.effort) ? body.effort : 'medium';
  const turns = Array.isArray(body.turns) ? body.turns.slice(0, 3) : [];
  if (!turns.length || turns.some(t => !t || typeof t.content !== 'string' || !t.schema)) throw Object.assign(new Error('Each turn needs content and a schema'), { status: 400 });
  if (!client) await connect();
  if (!client) throw Object.assign(new Error(conn.error), { status: 401 });

  const messages = [], outputs = [], used = { input_tokens: 0, output_tokens: 0, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 };
  let cost = 0, calls = 0;
  try {
    for (const t of turns) {
      messages.push({ role: 'user', content: t.content });
      const params = {
        model,
        max_tokens: Math.min(16000, Math.max(1024, Number(t.max_tokens) || 8000)),
        ...(body.system ? { system: String(body.system) } : {}),
        messages,
        thinking: { type: 'adaptive' },
        output_config: { effort, format: { type: 'json_schema', schema: t.schema } }
      };
      const res = MODELS[model].fallbacks
        ? await client.beta.messages.create({ ...params, betas: ['server-side-fallback-2026-07-01'], fallbacks: 'default' }, { maxRetries: 5 })
        : await client.messages.create(params, { maxRetries: 5 });
      calls++;
      const u = res.usage || {};
      for (const k of Object.keys(used)) used[k] += u[k] || 0;
      cost += price(Object.hasOwn(MODELS, res.model) ? res.model : model, u);
      if (res.stop_reason === 'refusal' || res.stop_reason === 'max_tokens') { outputs.push(null); break; }
      const text = res.content.filter(b => b.type === 'text').map(b => b.text).join('');
      let json = null;
      try { json = JSON.parse(text); } catch { /* left as null */ }
      outputs.push(json);
      if (!json) break;
      messages.push({ role: 'assistant', content: res.content });
    }
  } finally {
    if (calls) record(model, used, cost, calls); /* what was spent counts even if a later turn failed */
  }
  return { outputs, usage: used, cost, totals };
}

/* ---------- saved results ---------- */
function loadResults() {
  const out = {};
  for (const f of fs.readdirSync(RESULTS)) {
    if (!f.endsWith('.json')) continue;
    try { out[f.slice(0, -5)] = JSON.parse(fs.readFileSync(path.join(RESULTS, f), 'utf8')); } catch { /* skip a broken file */ }
  }
  return out;
}

/* ---------- http ---------- */
function send(res, status, data, type) {
  res.writeHead(status, { 'content-type': type, 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' });
  res.end(data);
}
const json = (res, status, obj) => send(res, status, JSON.stringify(obj), 'application/json; charset=utf-8');
function readJson(req, limit = 2e6) {
  return new Promise((resolve, reject) => {
    let size = 0; const parts = [];
    req.on('data', c => { size += c.length; if (size > limit) { reject(Object.assign(new Error('Request too large'), { status: 413 })); req.destroy(); } else parts.push(c); });
    req.on('end', () => { try { resolve(JSON.parse(Buffer.concat(parts).toString('utf8') || '{}')); } catch { reject(Object.assign(new Error('Bad JSON'), { status: 400 })); } });
    req.on('error', reject);
  });
}
/* only this page may spend your tokens: other sites and rebound host names are turned away */
const SELF = new Set([`127.0.0.1:${PORT}`, `localhost:${PORT}`]);
function allowed(req) {
  if (!SELF.has(req.headers.host)) return false;
  const origin = req.headers.origin;
  if (origin && !SELF.has(origin.replace(/^https?:\/\//, ''))) return false;
  return req.method === 'GET' || /^application\/json\b/.test(req.headers['content-type'] || '');
}

const server = http.createServer(async (req, res) => {
  try {
    if (!allowed(req)) return json(res, 403, { error: 'Forbidden' });
    const { pathname } = new URL(req.url, `http://${req.headers.host}`);
    if (req.method === 'GET' && (pathname === '/' || pathname === '/index.html')) return send(res, 200, fs.readFileSync(path.join(here, 'index.html')), 'text/html; charset=utf-8');
    if (req.method === 'GET' && pathname === '/api/status') {
      if (!conn.connected && Date.now() - conn.checked > 2000) await connect();
      return json(res, 200, { ...conn, models: MODELS, totals });
    }
    if (req.method === 'POST' && pathname === '/api/recheck') return json(res, 200, { ...(await connect()), models: MODELS, totals });
    if (req.method === 'POST' && pathname === '/api/chat') return json(res, 200, await chat(await readJson(req)));
    if (req.method === 'POST' && pathname === '/api/usage/reset') { totals = fresh(); saveTotals(); return json(res, 200, { totals }); }
    if (req.method === 'GET' && pathname === '/api/results') return json(res, 200, loadResults());
    const m = /^\/api\/results\/([a-z0-9_-]{1,40})(\/clear)?$/i.exec(pathname);
    if (req.method === 'POST' && m) {
      const file = path.join(RESULTS, m[1] + '.json');
      if (m[2]) fs.rmSync(file, { force: true }); /* the run went back to demo data */
      else fs.writeFileSync(file, JSON.stringify(await readJson(req, 60e6)));
      return json(res, 200, { ok: true });
    }
    json(res, 404, { error: 'Not found' });
  } catch (e) {
    /* 504: the API could not be reached even after the SDK's own retries, so the page stops instead of retrying again */
    const status = e instanceof Anthropic.APIConnectionError ? 504 : Number.isInteger(e.status) && e.status >= 400 && e.status < 600 ? e.status : 500;
    json(res, status, { error: friendly(e), status });
  }
});

server.listen(PORT, HOST, async () => {
  const c = await connect();
  console.log(`Stand-in: http://${HOST}:${PORT}`);
  console.log(c.connected ? `Connected to the Anthropic API through ${c.auth}.` : `Not connected yet: ${c.error}`);
});
