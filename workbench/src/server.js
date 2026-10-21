// 工作台服务入口:仅监听 127.0.0.1(本地可用;生产由 Caddy 反代同端口面,批 4 部署)
import { buildApp } from './app.js';

const PORT = Number(process.env.PORT || 8790);
const HOST = process.env.HOST || '127.0.0.1';

const app = buildApp({ logger: true });

app.listen({ port: PORT, host: HOST }).catch((err) => {
  app.log.error(err);
  process.exit(1);
});

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    app.close().then(() => process.exit(0));
  });
}
