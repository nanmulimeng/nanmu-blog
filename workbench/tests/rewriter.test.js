import test from 'node:test';
import assert from 'node:assert/strict';
import { rewriteHtml, rewriteCss } from '../src/rewriter.js';

const P = { prefix: '/preview/op-9', token: 'TOK' };

test('2.2 HTML 根路径资源 → 前缀改写 + token(css/img)', () => {
  const h = rewriteHtml(
    '<link rel="stylesheet" href="/fonts/fonts.css">' +
    '<img src="/img/a.png" srcset="/img/a.png 1x, /img/b.png 2x">', P);
  assert.ok(h.includes('href="/preview/op-9/fonts/fonts.css?t=TOK"'), h);
  assert.ok(h.includes('src="/preview/op-9/img/a.png?t=TOK"'), h);
  assert.ok(h.includes('/preview/op-9/img/a.png?t=TOK 1x'), h);
  assert.ok(h.includes('/preview/op-9/img/b.png?t=TOK 2x'), h);
});

test('2.2 站内/外部 <a> 去 href,data-wb-target 承载原值;锚点保留', () => {
  const h = rewriteHtml(
    '<a href="/posts/foo/">站内</a>' +
    '<a href="https://example.com/x">外部</a>' +
    '<a href="mailto:a@b.c">信箱</a>' +
    '<a href="#sec">锚点</a>', P);
  assert.ok(!/href="\/posts\/foo\/"/.test(h), h);
  assert.ok(h.includes('<a data-wb-target="/posts/foo/">站内</a>'), h);
  assert.ok(h.includes('<a data-wb-target="https://example.com/x">外部</a>'), h);
  assert.ok(h.includes('<a data-wb-target="mailto:a@b.c">信箱</a>'), h);
  assert.ok(h.includes('<a href="#sec">锚点</a>'), h);
});

test('2.2 script src:前缀改写但不注 token(类别=css/font/img;CSP 拦执行)', () => {
  const h = rewriteHtml('<script type="module" src="/scripts/site.js"></script>', P);
  assert.ok(h.includes('src="/preview/op-9/scripts/site.js"'), h);
  assert.ok(!h.includes('site.js?t='), h);
});

test('2.2 /api/ 永不被前缀改写指向预览命名空间', () => {
  const h = rewriteHtml('<img src="/api/anything">', P);
  assert.ok(!h.includes('/preview/op-9/api/'), h);
});

test('2.2 相对路径与 data: URI 不改写', () => {
  const h = rewriteHtml('<img src="pic/rel.png"><img src="data:image/png;base64,xx">', P);
  assert.ok(h.includes('src="pic/rel.png"'), h);
  assert.ok(h.includes('src="data:image/png;base64,xx"'), h);
});

test('2.2 已带 query 的根路径:token 追加不破坏原 query', () => {
  const h = rewriteHtml('<link rel="stylesheet" href="/fonts/f.css?v=1">', P);
  assert.ok(h.includes('href="/preview/op-9/fonts/f.css?v=1&t=TOK"'), h);
});

test('2.2 CSS:根路径前缀+token;相对路径位置已对只补 token(DESIGN:分片补同 token);data: 不动;query 追加', () => {
  const c = rewriteCss(
    '@font-face{src:url(/fonts/f1.woff2)}' +
    'a{background:url(../img/rel.png)}' +
    'b{background:url(data:image/svg+xml,%3Csvg%3E)}' +
    'c{background:url(/img/q.png?v=2)}', P);
  assert.ok(c.includes('url(/preview/op-9/fonts/f1.woff2?t=TOK)'), c);
  assert.ok(c.includes('url(../img/rel.png?t=TOK)'), c);
  assert.ok(c.includes('url(data:image/svg+xml,%3Csvg%3E)'), c);
  assert.ok(c.includes('url(/preview/op-9/img/q.png?v=2&t=TOK)'), c);
});

test('2.2 单引号属性同样改写', () => {
  const h = rewriteHtml("<link rel='stylesheet' href='/fonts/fonts.css'>", P);
  assert.ok(h.includes("/preview/op-9/fonts/fonts.css?t=TOK"), h);
});

test('2.2 CSS 相对分片(真实产物形态 url(\'shards/x.woff2\')):补 token 不改路径', () => {
  const c = rewriteCss("src:url('shards/noto-400-000.woff2') format('woff2')", P);
  assert.ok(c.includes("url('shards/noto-400-000.woff2?t=TOK')"), c);
  const c2 = rewriteCss('src:url(shards/a.woff2) format("woff2")', P);
  assert.ok(c2.includes('url(shards/a.woff2?t=TOK)'), c2);
});
