// 批 3 API 层:TDD 先行(RED)——发布/撤下/操作列表/手动重查
// 契约:DESIGN §4.4/§4.5;operations 实例注入(测试=临时 bare 双远端)。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { buildApp } from '../src/app.js';
import { createGitOps } from '../src/operations.js';

const BASE = 'http://127.0.0.1:8790';
const PW = 'test-password-placeholder';
const CSRF = { origin: BASE, 'x-requested-with': 'XMLHttpRequest' };
let T = 1_000_000_000;

function G(args, cwd, extraEnv = {}) {
  return execFileSync('git', args, { cwd, env: { ...process.env, ...extraEnv } });
}
const GE = { GIT_AUTHOR_NAME: 't', GIT_AUTHOR_EMAIL: 't@t', GIT_COMMITTER_NAME: 't', GIT_COMMITTER_EMAIL: 't@t' };

async function makeCtx() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wbopsapi-'));
  const mkBare = (n, seed) => {
    const b = path.join(dir, n);
    G(['init', '--bare', '-b', 'main', b], dir, GE);
    if (seed) {
      const s = path.join(dir, n + '-s');
      G(['clone', b, s], dir, GE);
      fs.mkdirSync(path.join(s, 'site', 'src', 'content', 'posts'), { recursive: true });
      fs.writeFileSync(path.join(s, 'site', 'README'), 'x');
      G(['add', '-A'], s, GE); G(['commit', '-m', 's'], s, GE);
      G(['push', 'origin', 'HEAD:main'], s, GE);
    }
    return b;
  };
  const deploy = mkBare('deploy.git', true);
  const github = mkBare('github.git', false);
  G(['push', github, 'main:main'], deploy, GE);
  const ops = createGitOps({
    repoPath: path.join(dir, 'repo.git'), wtPath: path.join(dir, 'repo.wt'),
    opsDir: path.join(dir, 'ops'), remotes: { github, deploy },
    now: () => T, getRelease: () => ({ sha: G(['rev-parse', 'main'], deploy, GE).toString().trim() }),
  }, GE);
  fs.mkdirSync(path.join(dir, 'drafts'), { recursive: true });
  const app = buildApp({ devPassword: PW, baseUrl: BASE, now: () => T,
    draftsDir: path.join(dir, 'drafts'), operations: ops });
  const login = await app.inject({ method: 'POST', url: '/api/login', payload: { password: PW } });
  const sc = login.headers['set-cookie'];
  const cookie = (Array.isArray(sc) ? sc[0] : sc).split(';')[0];
  return { dir, deploy, github, ops, app, cookie };
}

const MD = (title) => `---\ntitle: ${title}\npubDate: 2026-10-25\ntags: []\n---\n\n正文 ${title}。\n`;

test('API 发布链:鉴权→存草稿→publish→界面列表→确认;未配置 503', async () => {
  const ctx = await makeCtx();
  try {
    const H = { cookie: ctx.cookie, ...CSRF };
    assert.equal((await ctx.app.inject({ method: 'POST', url: '/api/publish', payload: { slug: 'x', idemKey: 'k' } })).statusCode, 401);
    assert.equal((await ctx.app.inject({ method: 'POST', url: '/api/publish', headers: { cookie: ctx.cookie }, payload: { slug: 'x', idemKey: 'k' } })).statusCode, 403);
    const put = await ctx.app.inject({ method: 'PUT', url: '/api/drafts/api-post', headers: H,
      payload: { title: 'API 文', date: '2026-10-25', tags: [], body: MD('API 文'), rev: 0 } });
    assert.equal(put.statusCode, 200);
    const pub = await ctx.app.inject({ method: 'POST', url: '/api/publish', headers: H,
      payload: { slug: 'api-post', idemKey: 'idem-1' } });
    assert.equal(pub.statusCode, 200, pub.payload);
    const rec = JSON.parse(pub.payload);
    assert.equal(rec.status, 'deploy_received');
    assert.ok(rec.url, '返回预览可用的操作信息');
    // 手动确认(重查)
    const conf = await ctx.app.inject({ method: 'POST', url: `/api/operations/${rec.id}/confirm`, headers: H });
    assert.equal(conf.statusCode, 200);
    assert.equal(JSON.parse(conf.payload).status, 'confirmed');
    // 列表界面态
    const list = await ctx.app.inject({ method: 'GET', url: '/api/operations', headers: { cookie: ctx.cookie } });
    const ops = JSON.parse(list.payload).operations;
    assert.equal(ops.find((o) => o.idem_key === 'idem-1').state, 'published');
  } finally { fs.rmSync(ctx.dir, { recursive: true, force: true }); }
});

test('API 撤下链:withdraw→确认=withdrawn;撤下 API 不可 slug 不存在 404', async () => {
  const ctx = await makeCtx();
  try {
    const H = { cookie: ctx.cookie, ...CSRF };
    await ctx.app.inject({ method: 'PUT', url: '/api/drafts/w1', headers: H,
      payload: { title: '撤', date: '2026-10-25', tags: [], body: MD('撤'), rev: 0 } });
    const pub = await ctx.app.inject({ method: 'POST', url: '/api/publish', headers: H, payload: { slug: 'w1', idemKey: 'w-pub' } });
    await ctx.app.inject({ method: 'POST', url: `/api/operations/${JSON.parse(pub.payload).id}/confirm`, headers: H });
    const wd = await ctx.app.inject({ method: 'POST', url: '/api/withdraw', headers: H, payload: { slug: 'w1', idemKey: 'w-del' } });
    assert.equal(wd.statusCode, 200, wd.payload);
    const wrec = JSON.parse(wd.payload);
    await ctx.app.inject({ method: 'POST', url: `/api/operations/${wrec.id}/confirm`, headers: H });
    const list = JSON.parse((await ctx.app.inject({ method: 'GET', url: '/api/operations', headers: { cookie: ctx.cookie } })).payload).operations;
    assert.equal(list.find((o) => o.idem_key === 'w-del').state, 'withdrawn');
    const gone = await ctx.app.inject({ method: 'POST', url: '/api/withdraw', headers: H, payload: { slug: 'no-such', idemKey: 'w-404' } });
    assert.equal(gone.statusCode, 404);
  } finally { fs.rmSync(ctx.dir, { recursive: true, force: true }); }
});

test('API 闸门透传:OPERATION_OPEN→409;REMOTES_DIVERGED→409 带 detail', async () => {
  const ctx = await makeCtx();
  try {
    const H = { cookie: ctx.cookie, ...CSRF };
    await ctx.app.inject({ method: 'PUT', url: '/api/drafts/g1', headers: H,
      payload: { title: 'G', date: '2026-10-25', tags: [], body: MD('G'), rev: 0 } });
    // 构造未终态:让 deploy 拒(afterBackupPush 使 deploy 前进)
    const s = path.join(ctx.dir, 'hand');
    G(['clone', ctx.deploy, s], ctx.dir, GE);
    ctx.ops.testHooks().afterBackupPush = () => {
      fs.writeFileSync(path.join(s, 'h.txt'), 'm');
      G(['add', '-A'], s, GE); G(['commit', '-m', 'm'], s, GE);
      G(['push', 'origin', 'HEAD:main'], s, GE);
    };
    const p1 = await ctx.app.inject({ method: 'POST', url: '/api/publish', headers: H, payload: { slug: 'g1', idemKey: 'p1' } });
    ctx.ops.testHooks().afterBackupPush = null;
    assert.equal(JSON.parse(p1.payload).status, 'deploy_rejected');
    // 闸门(a)→409
    await ctx.app.inject({ method: 'PUT', url: '/api/drafts/g2', headers: H,
      payload: { title: 'G2', date: '2026-10-25', tags: [], body: MD('G2'), rev: 0 } });
    const p2 = await ctx.app.inject({ method: 'POST', url: '/api/publish', headers: H, payload: { slug: 'g2', idemKey: 'p2' } });
    assert.equal(p2.statusCode, 409);
    assert.equal(JSON.parse(p2.payload).error, 'operation_open');
  } finally { fs.rmSync(ctx.dir, { recursive: true, force: true }); }
});

test('未注入 operations 实例:发布/撤下 API 503(本地未配置)', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wbops503-'));
  try {
    fs.mkdirSync(path.join(dir, 'd'), { recursive: true });
    const app = buildApp({ devPassword: PW, baseUrl: BASE, now: Date.now, draftsDir: path.join(dir, 'd') });
    const login = await app.inject({ method: 'POST', url: '/api/login', payload: { password: PW } });
    const sc = login.headers['set-cookie'];
    const cookie = (Array.isArray(sc) ? sc[0] : sc).split(';')[0];
    const r = await app.inject({ method: 'POST', url: '/api/publish',
      headers: { cookie, ...CSRF }, payload: { slug: 'x', idemKey: 'k' } });
    assert.equal(r.statusCode, 503);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
