// 任务 1.2 口令认证+会话:TDD 先行测试(RED)
// 契约:DESIGN §3——argon2id 比对、会话 12h(HttpOnly+SameSite=Strict)、
// 防爆破 5 次/15min、修改类 API CSRF(Origin+X-Requested-With)、日志脱敏
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildApp } from '../src/app.js';

const BASE = 'http://127.0.0.1:8790';
const PW = 'test-password-placeholder';
const CSRF = { origin: BASE, 'x-requested-with': 'XMLHttpRequest' };

function makeApp(over = {}) {
  let t = 1_000_000_000;
  const now = over.now ?? (() => t);
  const app = buildApp({ devPassword: PW, baseUrl: BASE, now, ...over });
  return { app, tick: (ms) => { t += ms; } };
}

async function login(app, password, headers = {}) {
  return app.inject({
    method: 'POST', url: '/api/login', headers,
    payload: { password },
  });
}

function cookies(res) {
  const sc = res.headers['set-cookie'] ?? [];
  return (Array.isArray(sc) ? sc : [sc]).filter((c) => c && c.startsWith('wb_session='));
}

test('正确口令登录 200,签发会话 cookie(HttpOnly/SameSite=Strict/12h)', async () => {
  const { app } = makeApp();
  const res = await login(app, PW);
  assert.equal(res.statusCode, 200);
  const c = cookies(res);
  assert.equal(c.length, 1);
  assert.match(c[0], /HttpOnly/);
  assert.match(c[0], /SameSite=Strict/);
  assert.match(c[0], /Max-Age=43200/);
  assert.ok(!/Secure/.test(c[0]), '本地 http 默认不带 Secure(部署时经 env 开启)');
  const { app: app2 } = makeApp({ cookieSecure: true });
  const res2 = await login(app2, PW);
  assert.match(cookies(res2)[0], /Secure/);
});

test('错误口令 401,不签发 cookie;响应不回传内部细节', async () => {
  const { app } = makeApp();
  const res = await login(app, 'wrong-password');
  assert.equal(res.statusCode, 401);
  assert.equal(cookies(res).length, 0);
  assert.ok(!res.payload.includes('hash'), res.payload);
});

test('GET /api/session:带有效会话 200;无会话 401', async () => {
  const { app } = makeApp();
  const res = await login(app, PW);
  const sid = cookies(res)[0].split(';')[0];
  const ok = await app.inject({ method: 'GET', url: '/api/session', headers: { cookie: sid } });
  assert.equal(ok.statusCode, 200);
  assert.equal(JSON.parse(ok.payload).authenticated, true);
  const no = await app.inject({ method: 'GET', url: '/api/session' });
  assert.equal(no.statusCode, 401);
});

test('会话 12h 过期后失效(可控时钟)', async () => {
  const ctx = makeApp();
  const res = await login(ctx.app, PW);
  const sid = cookies(res)[0].split(';')[0];
  ctx.tick(12 * 3600_000 + 1000);
  const r = await ctx.app.inject({ method: 'GET', url: '/api/session', headers: { cookie: sid } });
  assert.equal(r.statusCode, 401);
});

test('服务重启(新实例)后会话表为空,旧 sid 失效', async () => {
  const a = makeApp();
  const res = await login(a.app, PW);
  const sid = cookies(res)[0].split(';')[0];
  const b = makeApp(); // 模拟重启:内存会话表自然清空
  const r = await b.app.inject({ method: 'GET', url: '/api/session', headers: { cookie: sid } });
  assert.equal(r.statusCode, 401);
});

test('登出:带会话+CSRF 200,清 cookie,旧 sid 立即失效', async () => {
  const { app } = makeApp();
  const res = await login(app, PW);
  const sid = cookies(res)[0].split(';')[0];
  const out = await app.inject({
    method: 'POST', url: '/api/logout', headers: { cookie: sid, ...CSRF },
  });
  assert.equal(out.statusCode, 200);
  assert.match(cookies(out)[0], /Max-Age=0/);
  const r = await app.inject({ method: 'GET', url: '/api/session', headers: { cookie: sid } });
  assert.equal(r.statusCode, 401);
});

test('CSRF:修改类 API 四路拒绝(缺 Origin/不匹配/null Origin/缺 X-Requested-With)', async () => {
  const { app } = makeApp();
  const res = await login(app, PW);
  const sid = cookies(res)[0].split(';')[0];
  const cases = [
    { cookie: sid, 'x-requested-with': 'XMLHttpRequest' }, // 缺 Origin
    { cookie: sid, origin: 'https://evil.example', 'x-requested-with': 'XMLHttpRequest' }, // 不匹配
    { cookie: sid, origin: 'null', 'x-requested-with': 'XMLHttpRequest' }, // null Origin(沙盒/直连)
    { cookie: sid, origin: BASE }, // 缺自定义头
  ];
  for (const headers of cases) {
    const r = await app.inject({ method: 'POST', url: '/api/logout', headers });
    assert.equal(r.statusCode, 403, JSON.stringify(headers));
  }
  // 无会话:即使 CSRF 头齐全也是 401(身份在前)
  const noSess = await app.inject({ method: 'POST', url: '/api/logout', headers: { ...CSRF } });
  assert.equal(noSess.statusCode, 401);
});

test('防爆破:同一 IP 5 次失败后锁定 429(正确口令也被拒),15min 后解除', async () => {
  const ctx = makeApp();
  for (let i = 0; i < 5; i++) {
    assert.equal((await login(ctx.app, 'wrong')).statusCode, 401, `第${i + 1}次失败应 401`);
  }
  assert.equal((await login(ctx.app, PW)).statusCode, 429, '锁定期间正确口令也应 429');
  ctx.tick(15 * 60_000 + 1000);
  assert.equal((await login(ctx.app, PW)).statusCode, 200, '窗口过后恢复');
});

test('成功登录清空失败计数(自己的失败不长期累计)', async () => {
  const ctx = makeApp();
  for (let i = 0; i < 3; i++) await login(ctx.app, 'wrong');
  assert.equal((await login(ctx.app, PW)).statusCode, 200);
  for (let i = 0; i < 5; i++) {
    const r = await login(ctx.app, 'wrong');
    assert.equal(r.statusCode, 401, '计数已清零,前 5 次失败仍应 401');
  }
  assert.equal((await login(ctx.app, 'wrong')).statusCode, 429);
});

test('生产模式未配置口令哈希则拒绝启动(防弱口令/空口令上线)', () => {
  assert.throws(() => buildApp({ production: true, baseUrl: BASE }), /WORKBENCH_PASSWORD_HASH/);
});

test('日志脱敏:登录成功与失败的日志均不含口令内容', async () => {
  const lines = [];
  const stream = { write: (s) => lines.push(s) };
  const app = buildApp({
    devPassword: PW, baseUrl: BASE, logger: { level: 'info', stream },
  });
  await login(app, 'wrong-secret-xyz');
  await login(app, PW);
  const all = lines.join('');
  assert.ok(!all.includes('wrong-secret-xyz'));
  assert.ok(!all.includes(PW));
});
