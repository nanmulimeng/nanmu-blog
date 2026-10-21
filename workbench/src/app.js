// 工作台 Fastify 应用工厂(任务 1.1:骨架;/login、静态资源、错误兜底)
// 契约:DESIGN §2.2(Fastify)/§3(错误脱敏:客户端只回状态码与路径,不回内部信息)
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs/promises';
import Fastify from 'fastify';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const PUBLIC_DIR = path.resolve(__dirname, '../public');

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
  const app = Fastify({ logger: opts.logger ?? false });

  // 错误兜底:404/500 一律 HTML;500 不向客户端回传 message/堆栈(§3 脱敏)
  app.setErrorHandler((err, req, reply) => {
    const status = err.statusCode && err.statusCode >= 400 ? err.statusCode : 500;
    if (status >= 500 && app.log) {
      // 服务端日志:只留状态码、路径与异常类型;错误详情见进程日志,不进响应
      app.log.error({ status, url: req.raw.url, type: err.constructor?.name }, 'request error');
    }
    reply.code(status).type('text/html; charset=utf-8').send(errorPage(status));
  });
  app.setNotFoundHandler((req, reply) => {
    reply.code(404).type('text/html; charset=utf-8').send(errorPage(404));
  });

  // 根路径:未认证一律去登录页(1.2 引入会话后细化已登录分支)
  app.get('/', async (_req, reply) => reply.redirect('/login'));

  app.get('/login', async (_req, reply) => {
    reply.type('text/html; charset=utf-8');
    return fs.readFile(path.join(PUBLIC_DIR, 'login.html'), 'utf8');
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

  return app;
}
