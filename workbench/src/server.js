// 工作台服务入口:仅监听 127.0.0.1(本地可用;生产由 Caddy 反代,批 4 部署)
// 口令配置(DESIGN §3):生产 WORKBENCH_PASSWORD_HASH(服务器 env);本地占位口令可 env 覆盖,不落盘
import { buildApp } from './app.js';

const PORT = Number(process.env.PORT || 8790);
const HOST = process.env.HOST || '127.0.0.1';
const production = process.env.NODE_ENV === 'production';

const app = buildApp({
  logger: true,
  production,
  passwordHash: process.env.WORKBENCH_PASSWORD_HASH,
  devPassword: process.env.WB_DEV_PASSWORD, // 缺省用进程内占位符 'dev-placeholder',非真实凭据
  baseUrl: process.env.WB_BASE_URL || `http://127.0.0.1:${PORT}`,
  // 生产(Caddy TLS)必须 Secure;本地 http://127.0.0.1 下浏览器不存 Secure cookie,默认关闭、env 可强制
  cookieSecure: process.env.WB_COOKIE_SECURE === '1' || production,
  now: Date.now,
});

// 定期清理过期会话(内存表防泄漏;重启即清空是既定行为)
const sweepTimer = setInterval(() => app.workbenchSweep(), 60 * 1000);
sweepTimer.unref();

app.listen({ port: PORT, host: HOST }).catch((err) => {
  app.log.error(err);
  process.exit(1);
});

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    app.close().then(() => process.exit(0));
  });
}
