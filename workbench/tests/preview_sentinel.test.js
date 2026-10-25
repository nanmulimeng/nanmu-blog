// 任务 2.4 双预览互不串 + 哨兵验收:TDD 先行测试(RED)
// 契约:DESIGN §4.3 哨兵——①预览产物哨兵应当出现(草稿被真实渲染,
// 不是缓存/错页);②双预览各自哨兵互不出现;③公开面零命中。
// 哨兵串仅由验收夹具注入,正常草稿不注入。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { buildApp } from '../src/app.js';
import { createPreviewStore } from '../src/previews.js';

const BASE = 'http://127.0.0.1:8790';
const PW = 'test-password-placeholder';

function fixture() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wbsent-'));
  const previewsDir = path.join(dir, 'previews');
  // 双预览:各带独立哨兵与独立资源(同名字体文件内容不同)
  for (const [op, sent] of [['opA', '__sentinel_A1__'], ['opB', '__sentinel_B2__']]) {
    const p = path.join(previewsDir, op);
    fs.mkdirSync(path.join(p, 'fonts'), { recursive: true });
    fs.writeFileSync(path.join(p, 'index.html'),
      `<html><head><link rel="stylesheet" href="/fonts/fonts.css"></head>` +
      `<body><article>正文 ${sent} 哨兵</article></body></html>`);
    fs.writeFileSync(path.join(p, 'fonts', 'fonts.css'),
      `@font-face{font-family:X;src:url(/fonts/${sent}.woff2)}`);
  }
  // fixture 级「公开面」:不含任何哨兵
  fs.mkdirSync(path.join(dir, 'public-dist'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'public-dist', 'index.html'), '<html>公开</html>');
  return { dir, previewsDir, sentinels: { opA: '__sentinel_A1__', opB: '__sentinel_B2__' } };
}

function makeApp(fx) {
  const now = Date.now;
  const store = createPreviewStore({ previewsDir: fx.previewsDir, now });
  store.register('opA');
  store.register('opB');
  const app = buildApp({ devPassword: PW, baseUrl: BASE, now, previewsStore: store });
  return { app, store };
}

async function cookieOf(app) {
  const res = await app.inject({ method: 'POST', url: '/api/login', payload: { password: PW } });
  const sc = res.headers['set-cookie'] ?? [];
  const c = (Array.isArray(sc) ? sc : [sc]).find((x) => x && x.startsWith('wb_session='));
  return c.split(';')[0];
}

test('2.4 双预览各自哨兵出现、互不串(HTML 与 CSS 资源两层)', async () => {
  const fx = fixture();
  try {
    const { app } = makeApp(fx);
    const cookie = await cookieOf(app);
    const a = await app.inject({ method: 'GET', url: '/preview/opA/', headers: { cookie } });
    const b = await app.inject({ method: 'GET', url: '/preview/opB/', headers: { cookie } });
    assert.equal(a.statusCode, 200);
    assert.equal(b.statusCode, 200);
    assert.ok(a.payload.includes('__sentinel_A1__'), 'A 预览缺 A 哨兵');
    assert.ok(b.payload.includes('__sentinel_B2__'), 'B 预览缺 B 哨兵');
    assert.ok(!a.payload.includes('__sentinel_B2__'), 'A 预览串入 B 哨兵');
    assert.ok(!b.payload.includes('__sentinel_A1__'), 'B 预览串入 A 哨兵');
    // 资源层:各自 token 取各自 CSS,CSS 内容互不串
    const ta = /fonts\.css\?t=([A-Za-z0-9_-]+)/.exec(a.payload)[1];
    const tb = /fonts\.css\?t=([A-Za-z0-9_-]+)/.exec(b.payload)[1];
    assert.notEqual(ta, tb, '双预览不得共享同一 token');
    const cssA = await app.inject({ method: 'GET', url: `/preview/opA/fonts/fonts.css?t=${ta}` });
    const cssB = await app.inject({ method: 'GET', url: `/preview/opB/fonts/fonts.css?t=${tb}` });
    assert.ok(cssA.payload.includes('__sentinel_A1__') && !cssA.payload.includes('__sentinel_B2__'));
    assert.ok(cssB.payload.includes('__sentinel_B2__') && !cssB.payload.includes('__sentinel_A1__'));
    // A token 取 B 资源:401(2.3 已测,此处组合复核)
    const cross = await app.inject({ method: 'GET', url: `/preview/opB/fonts/fonts.css?t=${ta}` });
    assert.equal(cross.statusCode, 401);
  } finally { fs.rmSync(fx.dir, { recursive: true, force: true }); }
});

test('2.4 哨兵只存在于预览命名空间,公开面零命中', async () => {
  const fx = fixture();
  try {
    const { app } = makeApp(fx);
    const cookie = await cookieOf(app);
    const a = await app.inject({ method: 'GET', url: '/preview/opA/', headers: { cookie } });
    assert.ok(a.payload.includes('__sentinel_A1__'));
    // 公开面(fixture 级):任何哨兵零命中
    const pub = fs.readFileSync(path.join(fx.dir, 'public-dist', 'index.html'), 'utf8');
    assert.ok(!pub.includes('__sentinel_'), '公开面出现哨兵');
    // 预览目录外的服务路径不暴露哨兵:公开工作台首页不含
    const home = await app.inject({ method: 'GET', url: '/', headers: { cookie } });
    assert.ok(!home.payload.includes('__sentinel_'), '工作台页面出现哨兵');
  } finally { fs.rmSync(fx.dir, { recursive: true, force: true }); }
});
