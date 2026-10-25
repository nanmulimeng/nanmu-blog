// 任务 2.3 预览服务:TDD 先行测试(RED)
// 契约:DESIGN §4.3——HTML 会话鉴权 401(非 302)/CSP sandbox+noindex+no-referrer/
// 横幅注入/根路径前缀改写+token;子资源 token 四项校验(无 cookie,bearer 语义);
// 字体分片 ACAO:*;/api/ 与 js 不入 token 类别;410=预览删除或过期;
// 24h 存活+总量 10 上限从最旧清理;路径穿越拒绝。
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
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wbprev3-'));
  const previewsDir = path.join(dir, 'previews');
  const op = path.join(previewsDir, 'op-1');
  fs.mkdirSync(path.join(op, 'fonts'), { recursive: true });
  fs.mkdirSync(path.join(op, 'img'), { recursive: true });
  fs.mkdirSync(path.join(op, 'scripts'), { recursive: true });
  fs.writeFileSync(path.join(op, 'index.html'),
    '<html><head><link rel="stylesheet" href="/fonts/fonts.css"></head>' +
    '<body><h1>草稿标题</h1><a href="/posts/x/">站内</a><a href="#s">锚</a></body></html>');
  fs.writeFileSync(path.join(op, 'fonts', 'fonts.css'),
    '@font-face{font-family:X;src:url(/fonts/a.woff2)}');
  fs.writeFileSync(path.join(op, 'fonts', 'a.woff2'), 'woff2-bytes');
  fs.writeFileSync(path.join(op, 'img', 'p.png'), 'png-bytes');
  fs.writeFileSync(path.join(op, 'scripts', 's.js'), 'console.log(1)');
  return { dir, previewsDir };
}

function makeApp(fx, over = {}) {
  let t = 1_000_000_000;
  const now = over.now ?? (() => t);
  const store = over.store ?? createPreviewStore({ previewsDir: fx.previewsDir, now });
  store.register('op-1');
  const app = buildApp({ devPassword: PW, baseUrl: BASE, now, previewsStore: store, ...over });
  return { app, store, tick: (ms) => { t += ms; } };
}

async function loginCookie(app) {
  const res = await app.inject({ method: 'POST', url: '/api/login', payload: { password: PW } });
  const sc = res.headers['set-cookie'] ?? [];
  const c = (Array.isArray(sc) ? sc : [sc]).find((x) => x && x.startsWith('wb_session='));
  return c.split(';')[0];
}

async function firstToken(app) {
  const cookie = await loginCookie(app);
  const res = await app.inject({ method: 'GET', url: '/preview/op-1/', headers: { cookie } });
  const m = /fonts\.css\?t=([A-Za-z0-9_-]+)/.exec(res.payload);
  return { cookie, res, token: m && m[1] };
}

test('2.3 HTML 未登录 401(预览不重定向,opaque 无跳转意义)', async () => {
  const fx = fixture();
  try {
    const { app } = makeApp(fx);
    const res = await app.inject({ method: 'GET', url: '/preview/op-1/' });
    assert.equal(res.statusCode, 401);
  } finally { fs.rmSync(fx.dir, { recursive: true, force: true }); }
});

test('2.3 登录 HTML:200+CSP sandbox+noindex+no-referrer+横幅+改写注入 token', async () => {
  const fx = fixture();
  try {
    const { app } = makeApp(fx);
    const { res, token } = await firstToken(app);
    assert.equal(res.statusCode, 200);
    assert.equal(res.headers['content-security-policy'], 'sandbox');
    assert.equal(res.headers['x-robots-tag'], 'noindex');
    assert.equal(res.headers['referrer-policy'], 'no-referrer');
    assert.ok(res.payload.includes('草稿预览'), '横幅缺失');
    assert.ok(token, 'HTML 内资源未注入 token');
    assert.ok(res.payload.includes(`href="/preview/op-1/fonts/fonts.css?t=${token}"`), res.payload);
    assert.ok(res.payload.includes('<a data-wb-target="/posts/x/">'), '站内链接未收敛');
    assert.ok(res.payload.includes('<a href="#s">'), '锚点未保留');
  } finally { fs.rmSync(fx.dir, { recursive: true, force: true }); }
});

test('2.3 子资源 token:无 cookie 200(bearer);CSS 内分片同 token;woff2 带 ACAO:*', async () => {
  const fx = fixture();
  try {
    const mk = makeApp(fx);
    const { token } = await firstToken(mk.app);
    const css = await mk.app.inject({ method: 'GET', url: `/preview/op-1/fonts/fonts.css?t=${token}` });
    assert.equal(css.statusCode, 200);
    assert.match(css.headers['content-type'], /text\/css/);
    assert.ok(css.payload.includes(`url(/preview/op-1/fonts/a.woff2?t=${token})`), 'CSS 内分片未改写/未注 token');
    const woff = await mk.app.inject({ method: 'GET', url: `/preview/op-1/fonts/a.woff2?t=${token}` });
    assert.equal(woff.statusCode, 200);
    assert.equal(woff.headers['access-control-allow-origin'], '*');
    const png = await mk.app.inject({ method: 'GET', url: `/preview/op-1/img/p.png?t=${token}` });
    assert.equal(png.statusCode, 200);
  } finally { fs.rmSync(fx.dir, { recursive: true, force: true }); }
});

test('2.3 反例:无 token/坏 token/js(类别外)一律 401', async () => {
  const fx = fixture();
  try {
    const { app } = makeApp(fx);
    const { token } = await firstToken(app);
    const noTok = await app.inject({ method: 'GET', url: '/preview/op-1/fonts/fonts.css' });
    assert.equal(noTok.statusCode, 401);
    const badTok = await app.inject({ method: 'GET', url: '/preview/op-1/fonts/fonts.css?t=nope' });
    assert.equal(badTok.statusCode, 401);
    const js = await app.inject({ method: 'GET', url: `/preview/op-1/scripts/s.js?t=${token}` });
    assert.equal(js.statusCode, 401, 'js 不在 token 类别,持 token 也不得放行');
  } finally { fs.rmSync(fx.dir, { recursive: true, force: true }); }
});

test('2.3 反例:A 预览 token 请求 B 预览资源 401(凭证绑定预览)', async () => {
  const fx = fixture();
  try {
    const { app, store } = makeApp(fx);
    fs.cpSync(path.join(fx.previewsDir, 'op-1'), path.join(fx.previewsDir, 'op-2'), { recursive: true });
    store.register('op-2');
    const { token } = await firstToken(app);
    const res = await app.inject({ method: 'GET', url: `/preview/op-2/fonts/fonts.css?t=${token}` });
    assert.equal(res.statusCode, 401);
  } finally { fs.rmSync(fx.dir, { recursive: true, force: true }); }
});

test('2.3 反例:token 到期 401(可控时钟,30min)', async () => {
  const fx = fixture();
  try {
    const mk = makeApp(fx);
    const { app } = mk;
    const { token } = await firstToken(app);
    mk.tick(31 * 60 * 1000);
    const res = await app.inject({ method: 'GET', url: `/preview/op-1/fonts/fonts.css?t=${token}` });
    assert.equal(res.statusCode, 401);
  } finally { fs.rmSync(fx.dir, { recursive: true, force: true }); }
});

test('2.3 预览删除与 24h 过期:HTML/子资源均 410(未过期 token 连带失效)', async () => {
  const fx = fixture();
  try {
    const mk = makeApp(fx);
    const { app, store } = mk;
    const { token, cookie } = await firstToken(app);
    store.remove('op-1');
    const html = await app.inject({ method: 'GET', url: '/preview/op-1/', headers: { cookie } });
    assert.equal(html.statusCode, 410);
    const sub = await app.inject({ method: 'GET', url: `/preview/op-1/fonts/a.woff2?t=${token}` });
    assert.equal(sub.statusCode, 410);
    // 过期路径:重建预览,推进 25h
    store.register('op-1');
    mk.tick(25 * 3600 * 1000);
    const html2 = await app.inject({ method: 'GET', url: '/preview/op-1/', headers: { cookie } });
    assert.equal(html2.statusCode, 410);
  } finally { fs.rmSync(fx.dir, { recursive: true, force: true }); }
});

test('2.3 总量上限 10:第 11 份注册时最旧被清理(410)', async () => {
  const fx = fixture();
  try {
    const mk = makeApp(fx);
    const { app, store } = mk;
    const { cookie } = await firstToken(app);
    for (let i = 2; i <= 11; i++) {
      const p = path.join(fx.previewsDir, `op-${i}`);
      fs.mkdirSync(p, { recursive: true });
      fs.writeFileSync(path.join(p, 'index.html'), `<html>t${i}</html>`);
      store.register(`op-${i}`);
    }
    const oldest = await app.inject({ method: 'GET', url: '/preview/op-1/', headers: { cookie } });
    assert.equal(oldest.statusCode, 410, '最旧预览应被总量清理');
    const newest = await app.inject({ method: 'GET', url: '/preview/op-11/', headers: { cookie } });
    assert.equal(newest.statusCode, 200);
  } finally { fs.rmSync(fx.dir, { recursive: true, force: true }); }
});

test('2.3 路径穿越被拒绝', async () => {
  const fx = fixture();
  try {
    const { app } = makeApp(fx);
    const { token } = await firstToken(app);
    for (const u of [
      `/preview/op-1/..%2f..%2fpackage.json?t=${token}`,
      `/preview/op-1/fonts/../../package.json?t=${token}`,
    ]) {
      const res = await app.inject({ method: 'GET', url: u });
      assert.ok([400, 404].includes(res.statusCode), `${u} 不应 200,得 ${res.statusCode}`);
    }
  } finally { fs.rmSync(fx.dir, { recursive: true, force: true }); }
});
