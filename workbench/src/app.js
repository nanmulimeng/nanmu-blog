// 工作台 Fastify 应用工厂
// 任务 1.1:骨架(/login、静态资源、错误兜底)
// 任务 1.2:口令认证+会话+防爆破+CSRF(DESIGN §3)
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs/promises';
import Fastify from 'fastify';
import {
  LoginRateLimiter,
  SessionStore,
  makePasswordVerifier,
  readSessionCookie,
  serializeSessionCookie,
} from './auth.js';
import { DraftStore, validateDraftFields, validateSlug } from './drafts.js';
import { rewriteHtml, rewriteCss } from './rewriter.js';
import { createPreviewStore } from './previews.js';
import { buildPreview } from './preview_build.js';
import crypto from 'node:crypto';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const PUBLIC_DIR = path.resolve(__dirname, '../public');
export const DEFAULT_DRAFTS_DIR = path.resolve(__dirname, '../data/drafts');
export const DEFAULT_PREVIEWS_DIR = path.resolve(__dirname, '../data/previews');

// 静态资源 MIME 白名单(工作台自有界面资源;不服务任意类型)
const MIME = {
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
};

function page(title, body) {
  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title} · nanmu 写作台</title>
<link rel="stylesheet" href="/static/workbench.css">
</head>
<body class="wb-page">
<main class="wb-card">
${body}
</main>
</body>
</html>`;
}

export function errorPage(status, brief) {
  const text = brief ?? { 404: '页面不存在', 500: '服务器内部错误' }[status] ?? '请求失败';
  return page(`${status}`, `<h1>${status}</h1><p>${text}</p><p><a href="/">返回工作台</a></p>`);
}

export function buildApp(opts = {}) {
  const now = opts.now ?? Date.now;
  const baseUrl = opts.baseUrl ?? 'http://127.0.0.1:8790';
  const cookieSecure = opts.cookieSecure ?? false;
  const verifyPassword = makePasswordVerifier(opts);

  const app = Fastify({ logger: opts.logger ?? false });
  const sessions = new SessionStore(now);
  const limiter = new LoginRateLimiter(now);
  const drafts = new DraftStore(opts.draftsDir ?? DEFAULT_DRAFTS_DIR, { now });
  const previews = opts.previewsStore ?? createPreviewStore({ previewsDir: opts.previewsDir ?? DEFAULT_PREVIEWS_DIR, now });

  // 错误兜底:404/500 一律兜底;API 返回 JSON,页面返回 HTML;500 不向客户端回传内部信息
  app.setErrorHandler((err, req, reply) => {
    const status = err.statusCode && err.statusCode >= 400 ? err.statusCode : 500;
    if (status >= 500 && app.log) {
      // 服务端日志:只留状态码、路径与异常类型(§3 脱敏)
      app.log.error({ status, url: req.raw.url, type: err.constructor?.name }, 'request error');
    }
    if (req.raw.url?.startsWith('/api/')) {
      const payload = err.wbPayload ?? { error: status === 500 ? 'internal' : 'request_failed' };
      return reply.code(status).send(payload);
    }
    reply.type('text/html; charset=utf-8');
    return reply.code(status).send(errorPage(status));
  });
  app.setNotFoundHandler((req, reply) => {
    if (req.raw.url?.startsWith('/api/')) {
      return reply.code(404).send({ error: 'not_found' });
    }
    reply.type('text/html; charset=utf-8');
    return reply.code(404).send(errorPage(404));
  });

  // 会话读取与两类前置(API 401 JSON / 页面 302 登录)
  const readSession = (req) => sessions.get(readSessionCookie(req.headers.cookie));

  const requireSessionApi = async (req, reply) => {
    if (!readSession(req)) {
      return reply.code(401).send({ error: 'unauthorized' });
    }
    return null;
  };

  // CSRF(§3):修改类 API 要求 Origin 恰为工作台域 + 自定义头;缺失/null/不匹配即 403。
  // GET 一律只读,不挂本前置。
  const requireCsrf = async (req, reply) => {
    const origin = req.headers.origin;
    const xrw = req.headers['x-requested-with'];
    if (origin !== baseUrl || xrw !== 'XMLHttpRequest') {
      return reply.code(403).send({ error: 'csrf' });
    }
    return null;
  };

  // 根路径:未登录去登录页;已登录进工作台首页(列表与编辑器在任务 1.3/1.4 接入)
  app.get('/', async (req, reply) => {
    if (!readSession(req)) {
      return reply.redirect('/login');
    }
    reply.type('text/html; charset=utf-8');
    return fs.readFile(path.join(PUBLIC_DIR, 'home.html'), 'utf8');
  });

  app.get('/login', async (req, reply) => {
    if (readSession(req)) {
      return reply.redirect('/');
    }
    reply.type('text/html; charset=utf-8');
    return fs.readFile(path.join(PUBLIC_DIR, 'login.html'), 'utf8');
  });

  // 编辑器页面(slug 段已过 validateSlug;页面 JS 以 'new' 进入新建模式)
  app.get('/edit/:slug', async (req, reply) => {
    if (!readSession(req)) {
      return reply.redirect('/login');
    }
    if (!validateSlug(req.params.slug)) {
      reply.type('text/html; charset=utf-8');
      return reply.code(404).send(errorPage(404));
    }
    reply.type('text/html; charset=utf-8');
    return fs.readFile(path.join(PUBLIC_DIR, 'editor.html'), 'utf8');
  });

  app.post('/api/login', async (req, reply) => {
    const ip = req.ip;
    if (limiter.locked(ip)) {
      if (app.log) app.log.warn({ ip, failures: limiter.count(ip) }, 'login throttled');
      return reply.code(429).send({ error: 'rate_limited' });
    }
    const pw = req.body?.password;
    let ok = false;
    if (typeof pw === 'string' && pw.length > 0) {
      ok = verifyPassword(pw);
    }
    if (!ok) {
      limiter.recordFailure(ip);
      // 登录日志只记失败次数与时间(§3),不记口令内容
      if (app.log) app.log.warn({ ip, failures: limiter.count(ip) }, 'login failed');
      return reply.code(401).send({ error: 'bad_credentials' });
    }
    limiter.reset(ip);
    const { sid, expiresAt } = sessions.create();
    reply.header('set-cookie', serializeSessionCookie(sid, { secure: cookieSecure }));
    return { ok: true, expiresAt };
  });

  app.get('/api/session', { preHandler: requireSessionApi }, async (req) => ({
    authenticated: true,
    expiresAt: sessions.get(readSessionCookie(req.headers.cookie)).expiresAt,
  }));

  app.post('/api/logout', { preHandler: [requireSessionApi, requireCsrf] }, async (req, reply) => {
    const sid = readSessionCookie(req.headers.cookie);
    sessions.delete(sid);
    reply.header('set-cookie', serializeSessionCookie('', { secure: cookieSecure, clear: true }));
    return { ok: true };
  });

  // 草稿 API(DESIGN §4.2/§5):全部会话后;写操作叠加 CSRF
  app.get('/api/drafts', { preHandler: requireSessionApi }, async () => ({
    drafts: await drafts.list(),
  }));

  app.get('/api/drafts/:slug', { preHandler: requireSessionApi }, async (req, reply) => {
    const { slug } = req.params;
    if (!validateSlug(slug)) return reply.code(400).send({ error: 'bad_slug' });
    const res = await drafts.get(slug);
    if (!res) return reply.code(404).send({ error: 'not_found' });
    if (res.corrupted) return reply.code(404).send({ error: 'corrupted' });
    return { draft: res.record, recovered: res.recovered };
  });

  app.put('/api/drafts/:slug', { preHandler: [requireSessionApi, requireCsrf] }, async (req, reply) => {
    const { slug } = req.params;
    if (!validateSlug(slug)) return reply.code(400).send({ error: 'bad_slug' });
    const rev = req.body?.rev;
    if (!Number.isInteger(rev) || rev < 0) {
      return reply.code(400).send({ error: 'bad_rev' });
    }
    const v = validateDraftFields(req.body);
    if (!v.ok) return reply.code(400).send({ error: 'bad_fields', detail: v.detail });
    const out = await drafts.save(slug, v.fields, rev); // 冲突走 409(wbPayload)
    return out;
  });

  app.delete('/api/drafts/:slug', { preHandler: [requireSessionApi, requireCsrf] }, async (req, reply) => {
    const { slug } = req.params;
    if (!validateSlug(slug)) return reply.code(400).send({ error: 'bad_slug' });
    const removed = await drafts.remove(slug);
    if (!removed) return reply.code(404).send({ error: 'not_found' });
    return { ok: true };
  });

  // ── POST /api/preview:触发真实构建并注册预览(会话+CSRF;
  // 构建配置由部署方注入 opts.preview={repoPath,branch?,buildCmd?},
  // 未配置=本服务未开预览,503)。失败不注册(预览 URL 保持 410 语义)。 ──
  const previewCfg = opts.preview ?? null;
  app.post('/api/preview', { preHandler: [requireSessionApi, requireCsrf] }, async (req, reply) => {
    if (!previewCfg) return reply.code(503).send({ error: 'preview_not_configured' });
    const { slug } = req.body ?? {};
    if (!validateSlug(slug)) return reply.code(400).send({ error: 'bad_slug' });
    const d = await drafts.get(slug);
    if (!d || d.corrupted) return reply.code(404).send({ error: 'draft_not_found' });
    const opId = `op-${Date.now().toString(36)}-${crypto.randomBytes(4).toString('hex')}`;
    const r = await buildPreview({
      repoPath: previewCfg.repoPath,
      branch: previewCfg.branch ?? 'main',
      opId,
      previewsDir: previews.previewsDir,
      buildCmd: previewCfg.buildCmd ?? 'npm ci --no-audit --no-fund && npm run build',
      draft: { slug, content: d.record.body ?? '' },
    });
    if (!r.ok) {
      return reply.code(500).send({ error: 'build_failed', reason: r.reason });
    }
    previews.register(opId);
    // 预览直达该草稿的文章详情页(站点根是整站首页,作者校对对象是这篇文章)
    return { opId, url: `/preview/${opId}/posts/${slug}/` };
  });

  // ── 预览(任务 2.3,DESIGN §4.3):HTML 走会话鉴权(401,预览不重定向)
  // + CSP sandbox + noindex + no-referrer + 横幅;子资源走短期 bearer token
  // (无 cookie;四项校验=有效/预览匹配/类别/绑定会话活跃);字体分片 ACAO:*;
  // 过期/删除/被清理一律 410(不区分,不泄露存在性)。 ──
  const PV_MIME = {
    '.css': 'text/css; charset=utf-8', '.png': 'image/png', '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.svg': 'image/svg+xml',
    '.webp': 'image/webp', '.avif': 'image/avif', '.ico': 'image/x-icon',
    '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.otf': 'font/otf',
  };
  app.get('/preview/:opId/*', async (req, reply) => {
    const { opId } = req.params;
    const sub = req.params['*'] ?? '';
    if (!previews.get(opId)) {
      return reply.code(410).type('text/html; charset=utf-8')
        .send(errorPage(410, '预览已过期或被清理,请重新生成'));
    }
    const root = path.resolve(previews.dirOf(opId));
    const rel = sub === '' || sub.endsWith('/') ? `${sub}index.html` : sub;
    const target = path.resolve(root, rel);
    const relFromRoot = path.relative(root, target);
    if (rel.startsWith('/') || rel.includes('\\') || relFromRoot.startsWith('..') || path.isAbsolute(relFromRoot)) {
      return reply.code(404).type('text/html; charset=utf-8').send(errorPage(404));
    }
    const ext = path.extname(target).toLowerCase();
    if (ext === '.html' || ext === '.htm') {
      const sid = readSessionCookie(req.headers.cookie);
      if (!sessions.get(sid)) {
        return reply.code(401).type('text/html; charset=utf-8').send(errorPage(401, '请先登录'));
      }
      let html;
      try { html = await fs.readFile(target, 'utf8'); } catch {
        return reply.code(404).type('text/html; charset=utf-8').send(errorPage(404));
      }
      const token = previews.issueToken({ sid, opId });
      html = rewriteHtml(html, { prefix: `/preview/${opId}`, token });
      const banner = '<div style="position:sticky;top:0;z-index:2147483000;background:#C2402A;'
        + 'color:#fff;font:13px/1.6 system-ui,sans-serif;padding:6px 12px;text-align:center">'
        + '草稿预览:不执行脚本、不可导航</div>';
      html = /<body[^>]*>/i.test(html)
        ? html.replace(/<body[^>]*>/i, (m) => m + banner)
        : banner + html;
      return reply.code(200).type('text/html; charset=utf-8')
        .header('content-security-policy', 'sandbox')
        .header('x-robots-tag', 'noindex')
        .header('referrer-policy', 'no-referrer')
        .send(html);
    }
    // 子资源:token 即 bearer(不带会话 cookie 是常态,opaque origin 语义)
    const t = req.query?.t;
    if (!t || typeof t !== 'string') return reply.code(401).send({ error: 'unauthorized' });
    if (previews.checkToken({ t, opId, kind: ext.slice(1) }) !== 'ok') {
      return reply.code(401).send({ error: 'unauthorized' });
    }
    if (!sessions.get(previews.tokenSid(t))) {
      return reply.code(401).send({ error: 'unauthorized' });
    }
    if (!PV_MIME[ext]) return reply.code(404).send({ error: 'not_found' });
    try {
      const body = await fs.readFile(target);
      if (ext === '.css') {
        const css = rewriteCss(body.toString('utf8'), { prefix: `/preview/${opId}`, token: t });
        return reply.type(PV_MIME['.css']).send(css);
      }
      reply.type(PV_MIME[ext]);
      if (['.woff', '.woff2', '.ttf', '.otf'].includes(ext)) {
        reply.header('access-control-allow-origin', '*');
      }
      return body;
    } catch {
      return reply.code(404).send({ error: 'not_found' });
    }
  });

  // 静态资源:仅 /static/*、MIME 白名单、路径不越出 public/static/
  app.get('/static/*', async (req, reply) => {
    // 从原始 URL 解析 pathname 再单次解码,避免路由层已解码导致的二次解码问题
    const raw = new URL(req.raw.url, 'http://localhost').pathname;
    let rel;
    try {
      rel = decodeURIComponent(raw.slice('/static/'.length));
    } catch {
      return reply.code(400).type('text/html; charset=utf-8').send(errorPage(400, '请求路径非法'));
    }
    const root = path.resolve(PUBLIC_DIR, 'static');
    const target = path.resolve(root, rel);
    const relFromRoot = path.relative(root, target);
    if (rel.startsWith('/') || rel.includes('\\') || relFromRoot.startsWith('..') || path.isAbsolute(relFromRoot)) {
      return reply.code(404).type('text/html; charset=utf-8').send(errorPage(404));
    }
    const ext = path.extname(target).toLowerCase();
    if (!MIME[ext]) {
      return reply.code(404).type('text/html; charset=utf-8').send(errorPage(404));
    }
    try {
      const body = await fs.readFile(target);
      reply.type(MIME[ext]);
      return body;
    } catch {
      return reply.code(404).type('text/html; charset=utf-8').send(errorPage(404));
    }
  });

  app.decorate('workbenchSweep', () => sessions.sweep());
  return app;
}
