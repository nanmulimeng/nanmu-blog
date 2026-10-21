// 任务 1.1 服务骨架:TDD 先行测试(RED)
// 断言对象:/login 页、根路径重定向、静态资源、404/500 错误兜底
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildApp } from '../src/app.js';

test('GET /login 返回 200 HTML 登录页(含表单)', async () => {
  const app = buildApp();
  const res = await app.inject({ method: 'GET', url: '/login' });
  assert.equal(res.statusCode, 200);
  assert.match(res.headers['content-type'], /text\/html/);
  assert.match(res.payload, /<form/);
  assert.match(res.payload, /type="password"/);
});

test('GET / 未登录重定向到 /login', async () => {
  const app = buildApp();
  const res = await app.inject({ method: 'GET', url: '/' });
  assert.equal(res.statusCode, 302);
  assert.equal(res.headers.location, '/login');
});

test('静态资源 css 可服务且 content-type 正确', async () => {
  const app = buildApp();
  const res = await app.inject({ method: 'GET', url: '/static/workbench.css' });
  assert.equal(res.statusCode, 200);
  assert.match(res.headers['content-type'], /text\/css/);
});

test('静态资源路径穿越被拒绝(不越出 public/)', async () => {
  const app = buildApp();
  const res = await app.inject({ method: 'GET', url: '/static/../package.json' });
  assert.ok([400, 404].includes(res.statusCode), `不应 200,得 ${res.statusCode}`);
  const res2 = await app.inject({ method: 'GET', url: '/static/%2e%2e/package.json' });
  assert.ok([400, 404].includes(res2.statusCode), `编码穿越不应 200,得 ${res2.statusCode}`);
});

test('未知路径返回 404 HTML(错误兜底,非裸 JSON)', async () => {
  const app = buildApp();
  const res = await app.inject({ method: 'GET', url: '/no-such-page' });
  assert.equal(res.statusCode, 404);
  assert.match(res.headers['content-type'], /text\/html/);
});

test('处理异常返回 500 且不向客户端泄漏内部信息', async () => {
  const app = buildApp();
  app.get('/boom', async () => {
    throw new Error('secret internals');
  });
  const res = await app.inject({ method: 'GET', url: '/boom' });
  assert.equal(res.statusCode, 500);
  assert.ok(!res.payload.includes('secret internals'));
  assert.ok(!res.payload.includes('\n    at '));
});
