// 清理本 site 的 Astro 可再生缓存目录(quality-gates「内容变更与缓存验证」,Task 8a)。
// 背景:Astro 5.18.2 持久 data-store 在目录扫描为空时不清除已删条目,删除/改名/撤回
// 内容后可能继续产出幽灵页面。构建/开发入口每次从干净 store 重建,产物即当前源文件。
// 边界:只删解析后仍位于本 site 内的 .astro/ 与 node_modules/.astro/,
// 不碰源内容、node_modules 其余部分;解析后指向外部立即失败退出。
import { existsSync, realpathSync, rmSync } from 'node:fs';
import { dirname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const siteRoot = realpathSync(resolve(dirname(fileURLToPath(import.meta.url)), '..'));
const targets = [join(siteRoot, '.astro'), join(siteRoot, 'node_modules', '.astro')];

for (const target of targets) {
  if (!existsSync(target)) continue;
  const resolved = realpathSync(target);
  if (resolved === siteRoot || !resolved.startsWith(siteRoot + sep)) {
    console.error(`[clean-astro-cache] 目标解析后不在本 site 内,拒绝删除:${resolved}`);
    process.exit(1);
  }
  rmSync(resolved, { recursive: true, force: true });
  console.log(`[clean-astro-cache] cleared ${resolved}`);
}
