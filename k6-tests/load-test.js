/**
 * KnowledgeGuard k6 load tests
 *
 * Usage:
 *   k6 run load-test.js                          # default: smoke
 *   k6 run -e SCENARIO=auth load-test.js         # auth stress (new login per VU)
 *   k6 run -e SCENARIO=upload load-test.js       # upload throughput
 *   k6 run -e SCENARIO=query load-test.js        # query latency (needs indexed docs)
 *   k6 run -e SCENARIO=full load-test.js         # all flows combined
 *   k6 run -e SCENARIO=200 load-test.js          # enterprise 200-user baseline
 *   k6 run -e BASE_URL=http://localhost:8000 -e SCENARIO=200 load-test.js
 *
 * Requirements:
 *   - API running at BASE_URL (default: http://localhost:8000)
 *   - docker compose up -d (postgres, redis, minio)
 *   - worker running: uv run arq app.workers.main.WorkerSettings
 *   - For query scenario: upload at least one doc first and wait for ACTIVE status
 *
 * Install k6: https://k6.io/docs/getting-started/installation/
 *   macOS: brew install k6
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Counter, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const SCENARIO = __ENV.SCENARIO || 'smoke';
const SESSION_COOKIE = __ENV.SESSION_COOKIE || 'kg_session_dev';

// Custom metrics
const uploadAccepted = new Counter('uploads_accepted');
const querySuccess = new Counter('queries_success');
const queryLatency = new Trend('query_latency_ms');

// ── Scenario configs ──────────────────────────────────────────────────────────

const SCENARIOS = {
  smoke: {
    executor: 'per-vu-iterations',
    vus: 1,
    iterations: 1,
  },
  auth: {
    // Stress the login endpoint — new register+login per iteration
    executor: 'ramping-vus',
    stages: [
      { duration: '1m',  target: 500 },
      { duration: '2m',  target: 500 },
      { duration: '30s', target: 0   },
    ],
  },
  upload: {
    // Concurrent uploads — 500 users
    executor: 'ramping-vus',
    stages: [
      { duration: '1m',  target: 500 },
      { duration: '2m',  target: 500 },
      { duration: '30s', target: 0   },
    ],
  },
  query: {
    // Query latency with mocked LLM
    executor: 'ramping-vus',
    stages: [
      { duration: '30s', target: 50 },
      { duration: '1m',  target: 50 },
      { duration: '20s', target: 0  },
    ],
  },
  full: {
    // Realistic mixed load — 500 users
    executor: 'ramping-vus',
    stages: [
      { duration: '1m',  target: 500 },
      { duration: '2m',  target: 500 },
      { duration: '30s', target: 0   },
    ],
  },
  200: {
    // Enterprise mid-market baseline — pre-warmed sessions, all flows
    executor: 'ramping-vus',
    stages: [
      { duration: '1m',  target: 200 },
      { duration: '2m',  target: 200 },
      { duration: '30s', target: 0   },
    ],
  },
};

export const options = {
  setupTimeout: '5m',
  scenarios: {
    main: {
      ...SCENARIOS[SCENARIO],
      exec: 'main',
    },
  },
  thresholds: {
    'http_req_duration{endpoint:health}':    ['p(95)<200'],
    'http_req_duration{endpoint:login}':     ['p(95)<500'],
    'http_req_duration{endpoint:documents}': ['p(95)<1000'],
    // Query hits LLM (mocked in load tests) — allow up to 10s p95
    'http_req_duration{endpoint:query}':     ['p(95)<10000'],
    // Less than 1% of requests should fail
    http_req_failed: ['rate<0.01'],
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function uniqueEmail(prefix) {
  return `loadtest_${prefix}_${Date.now()}_${Math.random().toString(36).slice(2)}@example.com`;
}

/** Register + login. Returns session cookie string or null. */
function createAndLoginUser(email, password) {
  http.post(
    `${BASE_URL}/auth/register`,
    JSON.stringify({ email, password }),
    { headers: { 'Content-Type': 'application/json' } },
  );

  const loginRes = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({ email, password }),
    {
      headers: { 'Content-Type': 'application/json' },
      tags: { endpoint: 'login' },
    },
  );

  if (loginRes.status !== 200) return null;

  const jar = http.cookieJar();
  const cookies = jar.cookiesForURL(BASE_URL);
  return cookies[SESSION_COOKIE] ? cookies[SESSION_COOKIE][0] : null;
}

function authHeaders(token) {
  return {
    headers: {
      'Content-Type': 'application/json',
      Cookie: `${SESSION_COOKIE}=${token}`,
    },
  };
}

/** Small plain-text file content for upload tests. */
function makeTextFile(label) {
  const unique = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `This is a load test document (${label} / ${unique}).

KnowledgeGuard load testing content. This document contains information about
enterprise knowledge management, document retrieval, and AI-powered search.

Section 1: Overview
Organizations need fast, accurate access to internal knowledge. This system
provides semantic search over uploaded documents using vector embeddings.

Section 2: Features
- Document upload with automatic processing
- Hybrid search (vector + full-text)
- Role-based access control
- Audit logging

Section 3: Usage
Upload documents via the web interface or API. Query using natural language.
Results include citations with source document and version references.
`;
}

// ── Setup — pre-create session pool for non-auth scenarios ────────────────────
//
// Runs once before VUs start. Creates a pool of real user sessions so VUs
// reuse existing sessions rather than hammering bcrypt on every iteration.
// Auth scenario skips this — it intentionally tests register+login throughput.

export function setup() {
  if (SCENARIO === 'auth') return { users: [] };

  const maxVUs = SCENARIOS[SCENARIO]
    ? Math.max(...(SCENARIOS[SCENARIO].stages || [{ target: 1 }]).map((s) => s.target))
    : 1;

  // Create a shared session pool. VUs rotate through it — sessions last 24h
  // so multiple VUs sharing one session is fine.
  const count = Math.min(maxVUs, 50);
  const password = 'Password123!';
  const users = [];

  console.log(`setup: pre-creating ${count} user sessions...`);

  for (let i = 0; i < count; i++) {
    const email = uniqueEmail(`pre${i}`);
    const token = createAndLoginUser(email, password);
    if (token) {
      users.push(token);
    }
  }

  console.log(`setup: ${users.length}/${count} sessions ready`);
  return { users };
}

// ── Main scenario function ────────────────────────────────────────────────────

export function main(data) {
  // Auth scenario: create fresh user each iteration to stress bcrypt/login
  // All other scenarios: reuse a pre-warmed session from the pool
  const usePrewarmed = SCENARIO !== 'auth' && data.users && data.users.length > 0;
  const prewarmedToken = usePrewarmed ? data.users[(__VU - 1) % data.users.length] : null;

  // ── Health check ─────────────────────────────────────────────────────────
  group('health', () => {
    const res = http.get(`${BASE_URL}/health`, { tags: { endpoint: 'health' } });
    check(res, { 'health 200': (r) => r.status === 200 });
  });

  // ── Auth flow ─────────────────────────────────────────────────────────────
  let token = prewarmedToken;
  if (!usePrewarmed) {
    group('auth', () => {
      const email = uniqueEmail(`vu${__VU}`);
      token = createAndLoginUser(email, 'Password123!');
    });
  }

  if (!token) {
    console.error('No session token — skipping authenticated flows');
    return;
  }

  sleep(0.5);

  // ── List documents ────────────────────────────────────────────────────────
  group('list_documents', () => {
    const res = http.get(`${BASE_URL}/documents`, {
      ...authHeaders(token),
      tags: { endpoint: 'documents' },
    });
    check(res, { 'list docs 200': (r) => r.status === 200 });
  });

  // ── Upload (all scenarios except auth-only) ───────────────────────────────
  if (SCENARIO !== 'auth') {
    group('upload', () => {
      const fileContent = makeTextFile(`VU-${__VU}-iter-${__ITER}`);
      const formData = {
        file: http.file(fileContent, 'loadtest.txt', 'text/plain'),
        title: `Load Test Doc ${__VU}-${__ITER}`,
        sensitivity: 'STANDARD',
      };

      const res = http.post(`${BASE_URL}/documents`, formData, {
        headers: { Cookie: `${SESSION_COOKIE}=${token}` },
        tags: { endpoint: 'upload' },
        timeout: '30s',
      });

      const ok = check(res, { 'upload 202': (r) => r.status === 202 });
      if (ok) uploadAccepted.add(1);
    });

    sleep(1);
  }

  // ── Query (query, full, smoke, 200 scenarios) ─────────────────────────────
  const runQuery = ['query', 'full', 'smoke', '200'].includes(SCENARIO);
  if (runQuery) {
    group('query', () => {
      const questions = [
        'What is the purpose of this system?',
        'How does document processing work?',
        'What file types are supported?',
        'Explain the role-based access control.',
        'How are search results ranked?',
      ];
      const question = questions[Math.floor(Math.random() * questions.length)];

      const start = Date.now();
      const res = http.post(
        `${BASE_URL}/query`,
        JSON.stringify({ question, mode: 'current' }),
        {
          ...authHeaders(token),
          tags: { endpoint: 'query' },
          timeout: '30s',
        },
      );
      const elapsed = Date.now() - start;

      const ok = check(res, {
        'query 200': (r) => r.status === 200,
        'query has answer': (r) => {
          try {
            return JSON.parse(r.body).answer !== undefined;
          } catch {
            return false;
          }
        },
      });

      if (ok) {
        querySuccess.add(1);
        queryLatency.add(elapsed);
      }
    });

    sleep(2);
  }

  sleep(0.5);
}
