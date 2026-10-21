// 任务 1.3 草稿保存 API:TDD 先行测试(RED)
// 契约:DESIGN §4.2 保存提交点(单记录一次替换)+§5 存储 +§3 脱敏
import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import os from 'node:os';
import fs from 'node:fs';
import { buildApp } from '../src/app.js';

const BASE = 'http://127.0.0.1:8790';
const PW = 'test-password-placeholder';
const CSRF = { origin: BASE, 'x-requested-with': 'XMLHttpRequest' };

async function makeCtx(over = {}) {
  const draftsDir = fs.mkdtempSync(path.join(os.tmpdir(), 'wb-drafts-'));
  let t = 1_000_000_000;
  const app = buildApp({
    devPassword: PW, baseUrl: BASE, now: () => t, draftsDir, ...over,
  });
  const login = await app.inject({ method: 'POST', url: '/api/login', payload: { password: PW } });
  const sc = login.headers['set-cookie'];
  const cookie = (Array.isArray(sc) ? sc[0] : sc).split(';')[0];
  return { app, draftsDir, cookie, tick: (ms) => { t += ms; } };
}

const fields = (over = {}) => ({
  title: '标题一', date: '2026-10-21', tags: ['随笔'], body: '正文 SENTINEL-BODY-TEXT', ...over,
});

async function put(ctx, slug, payload, headers = {}) {
  return ctx.app.inject({
    method: 'PUT', url: `/api/drafts/${encodeURIComponent(slug)}`,
    headers: { cookie: ctx.cookie, ...CSRF, ...headers }, payload,
  });
}

test('未登录/缺 CSRF:草稿 API 拒绝(401/403)', async () => {
  const ctx = await makeCtx();
  const noAuth = await ctx.app.inject({ method: 'GET', url: '/api/drafts/a-slug' });
  assert.equal(noAuth.statusCode, 401);
  // 缺 X-Requested-With(显式构造,避免 helper 默认头混入)
  const noCsrf = await ctx.app.inject({
    method: 'PUT', url: '/api/drafts/a-slug',
    headers: { cookie: ctx.cookie, origin: BASE },
    payload: { ...fields(), rev: 0 },
  });
  assert.equal(noCsrf.statusCode, 403);
});

test('新建保存 rev=0 → 200 rev=1;GET 返回内容与元数据一致', async () => {
  const ctx = await makeCtx();
  const save = await put(ctx, 'hello-draft', { ...fields(), rev: 0 });
  assert.equal(save.statusCode, 200);
  assert.equal(JSON.parse(save.payload).rev, 1);
  const got = await ctx.app.inject({ method: 'GET', url: '/api/drafts/hello-draft', headers: { cookie: ctx.cookie } });
  assert.equal(got.statusCode, 200);
  const { draft } = JSON.parse(got.payload);
  assert.equal(draft.slug, 'hello-draft');
  assert.equal(draft.title, '标题一');
  assert.equal(draft.date, '2026-10-21');
  assert.deepEqual(draft.tags, ['随笔']);
  assert.ok(draft.body.includes('SENTINEL-BODY-TEXT'));
  assert.equal(draft.rev, 1);
  assert.equal(draft.base, null);
});

test('slug 校验:非法 slug 一律 400,不触磁盘', async () => {
  const ctx = await makeCtx();
  for (const bad of ['Bad-Upper', 'a/b', '..', 'a/../b', '123', '-x', 'x-', 'a--', 'a_b', '']) {
    const r = await put(ctx, bad, { ...fields(), rev: 0 });
    // '..' 类会被 HTTP 层路径规范化先行拒绝(404),其余走 slug 校验(400)——两者都未触盘
    assert.ok([400, 404].includes(r.statusCode), `slug=${JSON.stringify(bad)} 应被拒绝,得 ${r.statusCode}`);
  }
  const entries = fs.readdirSync(ctx.draftsDir);
  assert.deepEqual(entries, [], '非法 slug 不应创建任何目录');
});

test('元数据校验:空标题/非法日期/tags 非数组/rev 非整数 → 400', async () => {
  const ctx = await makeCtx();
  assert.equal((await put(ctx, 'meta-check', { ...fields(''), title: '  ', rev: 0 })).statusCode, 400);
  assert.equal((await put(ctx, 'meta-check', { ...fields(), date: '2026-13-99', rev: 0 })).statusCode, 400);
  assert.equal((await put(ctx, 'meta-check', { ...fields(), date: 'abc', rev: 0 })).statusCode, 400);
  assert.equal((await put(ctx, 'meta-check', { ...fields(), tags: 'a,b', rev: 0 })).statusCode, 400);
  assert.equal((await put(ctx, 'meta-check', { ...fields(), rev: 'x' })).statusCode, 400);
  assert.equal((await put(ctx, 'meta-check', { ...fields(), rev: -1 })).statusCode, 400);
});

test('双窗口同 rev 并发保存:恰一个 200(rev+1),另一个 409 带当前 rev;无双重写入', async () => {
  const ctx = await makeCtx();
  await put(ctx, 'race-slug', { ...fields({ body: 'v1' }), rev: 0 });
  const [a, b] = await Promise.all([
    put(ctx, 'race-slug', { ...fields({ body: '窗口A的内容' }), rev: 1 }),
    put(ctx, 'race-slug', { ...fields({ body: '窗口B的内容' }), rev: 1 }),
  ]);
  const codes = [a.statusCode, b.statusCode].sort();
  assert.deepEqual(codes, [200, 409], `应一胜一败,得 ${codes}`);
  const winner = a.statusCode === 200 ? a : b;
  const loser = a.statusCode === 200 ? b : a;
  assert.equal(JSON.parse(winner.payload).rev, 2);
  assert.equal(JSON.parse(loser.payload).error, 'conflict');
  assert.equal(JSON.parse(loser.payload).currentRev, 2);
  const got = await ctx.app.inject({ method: 'GET', url: '/api/drafts/race-slug', headers: { cookie: ctx.cookie } });
  const { draft } = JSON.parse(got.payload);
  assert.equal(draft.rev, 2);
  assert.ok(['窗口A的内容', '窗口B的内容'].includes(draft.body));
});

test('旧 rev 串行重放(非并发)同样 409', async () => {
  const ctx = await makeCtx();
  await put(ctx, 'stale-rev', { ...fields({ body: 'v1' }), rev: 0 });
  await put(ctx, 'stale-rev', { ...fields({ body: 'v2' }), rev: 1 });
  const stale = await put(ctx, 'stale-rev', { ...fields({ body: 'v1-again' }), rev: 1 });
  assert.equal(stale.statusCode, 409);
});

test('反例1:tmp 写完未替换中断 → GET 得旧完整版,tmp 被丢弃', async () => {
  const ctx = await makeCtx();
  await put(ctx, 'crash-tmp', { ...fields({ body: 'v1' }), rev: 0 });
  const dir = path.join(ctx.draftsDir, 'crash-tmp');
  fs.writeFileSync(path.join(dir, 'draft.json.tmp'), JSON.stringify({ body: 'v2-半途', rev: 2 }));
  const got = await ctx.app.inject({ method: 'GET', url: '/api/drafts/crash-tmp', headers: { cookie: ctx.cookie } });
  const { draft, recovered } = JSON.parse(got.payload);
  assert.equal(draft.body, 'v1');
  assert.equal(draft.rev, 1);
  assert.equal(recovered, null);
  assert.ok(!fs.existsSync(path.join(dir, 'draft.json.tmp')), 'tmp 应被清理');
});

test('反例2:draft.json 损坏 → 回退 draft.prev.json 且标注 recovered', async () => {
  const ctx = await makeCtx();
  await put(ctx, 'corrupt-main', { ...fields({ body: 'v1' }), rev: 0 });
  await put(ctx, 'corrupt-main', { ...fields({ body: 'v2' }), rev: 1 }); // 此时 prev=v1
  const dir = path.join(ctx.draftsDir, 'corrupt-main');
  fs.writeFileSync(path.join(dir, 'draft.json'), '{"slug":"corrupt-main","rev":2,"body":"v3-半'); // 截断 JSON
  const got = await ctx.app.inject({ method: 'GET', url: '/api/drafts/corrupt-main', headers: { cookie: ctx.cookie } });
  const { draft, recovered } = JSON.parse(got.payload);
  assert.equal(recovered, 'prev');
  assert.equal(draft.body, 'v1');
  assert.equal(draft.rev, 1);
  assert.ok(Number.isInteger(draft.rev));
  // 正文与 rev 来自同一完整记录(无半新半旧):v1 对应 rev=1
  assert.ok(!(draft.body === 'v2' && draft.rev === 1));
});

test('保存成功后磁盘即有完整新记录(rename 后才返回 200)', async () => {
  const ctx = await makeCtx();
  await put(ctx, 'durable', { ...fields({ body: 'v1' }), rev: 0 });
  await put(ctx, 'durable', { ...fields({ body: 'v2 完整' }), rev: 1 });
  const raw = fs.readFileSync(path.join(ctx.draftsDir, 'durable', 'draft.json'), 'utf8');
  const rec = JSON.parse(raw);
  assert.equal(rec.body, 'v2 完整');
  assert.equal(rec.rev, 2);
  const prev = JSON.parse(fs.readFileSync(path.join(ctx.draftsDir, 'durable', 'draft.prev.json'), 'utf8'));
  assert.equal(prev.body, 'v1', '上一版进 prev 兜底');
});

test('保存失败(目录被文件占用)→ 500 通用错误,响应无内部细节,既有草稿不受影响', async () => {
  const ctx = await makeCtx();
  await put(ctx, 'good-draft', { ...fields({ body: 'keep' }), rev: 0 });
  fs.writeFileSync(path.join(ctx.draftsDir, 'blocked'), '我是一个文件,挡住同名目录');
  const r = await put(ctx, 'blocked', { ...fields(), rev: 0 });
  assert.equal(r.statusCode, 500);
  assert.ok(!r.payload.includes('EEXIST') && !r.payload.includes('ENOTDIR'), r.payload);
  const got = await ctx.app.inject({ method: 'GET', url: '/api/drafts/good-draft', headers: { cookie: ctx.cookie } });
  assert.equal(JSON.parse(got.payload).draft.body, 'keep');
});

test('DELETE:删除草稿后 GET 404;不存在 → 404;缺 CSRF → 403', async () => {
  const ctx = await makeCtx();
  await put(ctx, 'del-me', { ...fields(), rev: 0 });
  const del = await ctx.app.inject({
    method: 'DELETE', url: '/api/drafts/del-me', headers: { cookie: ctx.cookie, ...CSRF },
  });
  assert.equal(del.statusCode, 200);
  assert.ok(!fs.existsSync(path.join(ctx.draftsDir, 'del-me')));
  const gone = await ctx.app.inject({ method: 'GET', url: '/api/drafts/del-me', headers: { cookie: ctx.cookie } });
  assert.equal(gone.statusCode, 404);
  const again = await ctx.app.inject({
    method: 'DELETE', url: '/api/drafts/del-me', headers: { cookie: ctx.cookie, ...CSRF },
  });
  assert.equal(again.statusCode, 404);
  const noCsrf = await ctx.app.inject({ method: 'DELETE', url: '/api/drafts/x', headers: { cookie: ctx.cookie } });
  assert.equal(noCsrf.statusCode, 403);
});

test('日志脱敏:保存/读取/冲突全程日志不含草稿正文标记', async () => {
  const lines = [];
  const ctx = await makeCtx({ logger: { level: 'info', stream: { write: (s) => lines.push(s) } } });
  await put(ctx, 'quiet-log', { ...fields({ body: 'LOG-SENTINEL-SECRET' }), rev: 0 });
  await ctx.app.inject({ method: 'GET', url: '/api/drafts/quiet-log', headers: { cookie: ctx.cookie } });
  await put(ctx, 'quiet-log', { ...fields({ body: 'LOG-SENTINEL-SECRET' }), rev: 5 }); // 触发 409
  const all = lines.join('');
  assert.ok(!all.includes('LOG-SENTINEL-SECRET'), '日志不得含草稿正文');
});

test('重复保存:prev 只留一份,rev 单调递增', async () => {
  const ctx = await makeCtx();
  const dir = path.join(ctx.draftsDir, 'chain');
  for (let rev = 0; rev < 4; rev++) {
    const r = await put(ctx, 'chain', { ...fields({ body: `v${rev + 1}` }), rev });
    assert.equal(r.statusCode, 200);
  }
  const prev = JSON.parse(fs.readFileSync(path.join(dir, 'draft.prev.json'), 'utf8'));
  assert.equal(prev.body, 'v3', 'prev 仅保留上一版,不是历史');
  assert.ok(!fs.existsSync(path.join(dir, 'draft.prev.1.json')));
});

test('回归:列表读取不得干扰进行中的保存(并发 list 删活动 tmp → ENOENT 缺陷)', async () => {
  const ctx = await makeCtx();
  await put(ctx, 'race-list', { ...fields({ body: 'v1' }), rev: 0 });
  const tmp = path.join(ctx.draftsDir, 'race-list', 'draft.json.tmp');

  // 同步屏障一:拦截 rename,把 save 停在「tmp 已写完+fsync、rename 未执行」处
  // 同步屏障二:监听 rm 对该 tmp 的删除(旧实现 list 不排队,会在 rename 前删掉它)
  const fsp = fs.promises;
  const origRename = fsp.rename;
  const origRm = fsp.rm;
  let releaseRename;
  const atRename = new Promise((r) => { releaseRename = r; });
  let renameArrived = false;
  let rmTmpDone;
  const rmTmpSignal = new Promise((r) => { rmTmpDone = r; });
  fsp.rename = async (...a) => { renameArrived = true; await atRename; return origRename(...a); };
  fsp.rm = async (p, o) => {
    const r_ = await origRm(p, o);
    // 仅统计 rename 屏障期间的 tmp 删除(=list 干扰);save 自身在写 tmp 前的
    // 残留清理 rm(此时 tmp 尚不存在)不得误触发信号
    if (String(p) === tmp && renameArrived) rmTmpDone();
    return r_;
  };
  try {
    // save(rev 2)发起,推进到 rename 屏障(拦截器同步置位,setImmediate 轮询等待)
    const saving = put(ctx, 'race-list', { ...fields({ body: 'v2-新' }), rev: 1 });
    await new Promise((r) => setImmediate(function poll() { renameArrived ? r() : setImmediate(poll); }));
    // 并发发起列表读取:旧实现直接 #readCurrent(先 rm tmp);修正后应排队等 save 完成
    const listing = ctx.app.inject({ method: 'GET', url: '/api/drafts', headers: { cookie: ctx.cookie } });
    // 观测窗:等「tmp 已被删」信号,或 1s 确认无并发删除(修正后语义上不可能在 save 完成前删)
    await Promise.race([rmTmpSignal, new Promise((r) => setTimeout(r, 1000))]);
    releaseRename();
    const [saveRes, listRes] = await Promise.all([saving, listing]);
    assert.equal(saveRes.statusCode, 200, `保存应成功,得 ${saveRes.statusCode} ${saveRes.payload}`);
    assert.equal(JSON.parse(saveRes.payload).rev, 2);
    const got = await ctx.app.inject({ method: 'GET', url: '/api/drafts/race-list', headers: { cookie: ctx.cookie } });
    const { draft } = JSON.parse(got.payload);
    assert.equal(draft.body, 'v2-新');
    assert.equal(draft.rev, 2);
    assert.equal(listRes.statusCode, 200);
    const row = JSON.parse(listRes.payload).drafts.find((d) => d.slug === 'race-list');
    assert.ok(row && row.rev === 2, `列表应反映保存后状态:${JSON.stringify(row)}`);
  } finally {
    fsp.rename = origRename;
    fsp.rm = origRm;
  }
});

test('句柄释放:保存全程打开的句柄在正常路径与 sync 异常路径下均显式关闭', async () => {
  const ctx = await makeCtx();
  const fsp = fs.promises;
  const dirPath = path.join(ctx.draftsDir, 'handle-check');
  const origOpen = fsp.open;
  const handles = [];
  let injectFileSync = false;
  fsp.open = async (...a) => {
    const h = await origOpen(...a);
    handles.push(h);
    // 注入一:目录句柄 sync 抛错(Windows 实况复现;Linux 上模拟不支持)
    if (String(a[0]) === dirPath) {
      h.sync = async () => { throw new Error('EINJ: directory fsync unsupported'); };
    }
    // 注入二(段3开启):tmp 文件句柄 sync 抛错 → 保存失败路径
    if (injectFileSync && String(a[0]).endsWith('draft.json.tmp') && a[1] === 'r+') {
      h.sync = async () => { throw new Error('EINJ: file fsync fail'); };
    }
    return h;
  };
  try {
    // 段1/2:目录 fsync 异常被「尽力而为」吞掉,保存仍成功
    assert.equal((await put(ctx, 'handle-check', { ...fields({ body: 'v1' }), rev: 0 })).statusCode, 200);
    assert.equal((await put(ctx, 'handle-check', { ...fields({ body: 'v2' }), rev: 1 })).statusCode, 200);
    const got = await ctx.app.inject({ method: 'GET', url: '/api/drafts/handle-check', headers: { cookie: ctx.cookie } });
    assert.equal(JSON.parse(got.payload).draft.body, 'v2');
    // 段3:文件 sync 异常 → 保存 500(失败如实),既有记录不破坏
    injectFileSync = true;
    const r3 = await put(ctx, 'handle-check', { ...fields({ body: 'v3' }), rev: 2 });
    injectFileSync = false;
    assert.equal(r3.statusCode, 500);
    const after = await ctx.app.inject({ method: 'GET', url: '/api/drafts/handle-check', headers: { cookie: ctx.cookie } });
    assert.equal(JSON.parse(after.payload).draft.body, 'v2');
    // 核心断言:成功与失败路径打开过的每个句柄都已显式 close。
    // Node 22 的 FileHandle 无 closed 属性,判据=close() 完成后 fd 置 -1
    const leaked = handles.filter((h) => h.fd !== -1);
    assert.equal(leaked.length, 0, `有句柄未关闭:fd=${leaked.map((h) => h.fd).join(',')}`);
  } finally {
    fsp.open = origOpen;
  }
});

test('列表:返回全部草稿摘要(按 savedAt 倒序),未登录 401(任务 1.4)', async () => {
  const ctx = await makeCtx();
  const noAuth = await ctx.app.inject({ method: 'GET', url: '/api/drafts' });
  assert.equal(noAuth.statusCode, 401);
  await put(ctx, 'list-a', { ...fields({ title: 'A', body: 'aaa' }), rev: 0 });
  ctx.tick(5_000);
  await put(ctx, 'list-b', { ...fields({ title: 'B', body: 'bbbb' }), rev: 0 });
  const res = await ctx.app.inject({ method: 'GET', url: '/api/drafts', headers: { cookie: ctx.cookie } });
  assert.equal(res.statusCode, 200);
  const { drafts } = JSON.parse(res.payload);
  assert.equal(drafts.length, 2);
  assert.equal(drafts[0].slug, 'list-b', '最近保存在前');
  assert.equal(drafts[1].title, 'A');
  assert.equal(drafts[1].charCount, 3);
  assert.ok(Number.isInteger(drafts[0].rev));
});
