import type { CollectionEntry } from 'astro:content';
import { readdirSync } from 'node:fs';
import { resolve } from 'node:path';

// 共享内容校验(Task 5 Step 0 契约;Task 8a 补原始路径/slug/重复 id 边界):
// - 接收完整 collection(含草稿),不自行调用 getCollection
// - 两层校验:源文件扫描(原始文件名,在 Astro id 清洗/slug 改写之前)+ entry.id 复核
// - posts:单层、小写英文数字短横线、非纯数字;digest:文件名即有效 YYYY-MM-DD 且与 date 一致
// - 禁 frontmatter slug:由 content.config.ts 的 schema .strict() 在内容入库前拒绝
// - 源文件数与条目数必须一致:重复最终 id 会在内容 store 内静默覆盖,这里在出口侧拦截
// - 所有内容出口(页面/RSS)在过滤/分页前调用;错误带文件名/id,抛出使构建非零

const POSTS_ID_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const DIGEST_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function isRealDate(value: string): boolean {
  return Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
}

// 扫描 collection 源目录:不允许子目录;返回 .md 文件名(非 .md 文件与 loader 一样忽略)
function scanSourceDir(kind: string, relDir: string): string[] {
  const names = readdirSync(resolve(process.cwd(), relDir), { withFileTypes: true });
  const files: string[] = [];
  for (const item of names) {
    if (item.isDirectory()) {
      throw new Error(`[content] ${kind} 不允许子目录(文件须单层放置):${item.name}/`);
    }
    if (item.isFile() && item.name.endsWith('.md')) {
      files.push(item.name);
    }
  }
  return files;
}

function assertCountMatches(kind: string, files: string[], entries: unknown[]): void {
  if (files.length !== entries.length) {
    throw new Error(`[content] ${kind} 源文件数(${files.length})与加载条目数(${entries.length})不一致:存在重复最终 id 或未被加载的文件`);
  }
}

export function assertPostsIds(entries: CollectionEntry<'posts'>[]): void {
  const files = scanSourceDir('posts', 'src/content/posts');
  for (const name of files) {
    const id = name.slice(0, -3);
    if (!POSTS_ID_RE.test(id)) {
      throw new Error(`[content] 非法 posts 文件名(须单层小写英文数字短横线,不可用 slug/自动清洗规避):${name}`);
    }
    if (/^\d+$/.test(id)) {
      throw new Error(`[content] posts 文件名不能是纯数字(与分页路由冲突):${name}`);
    }
  }
  assertCountMatches('posts', files, entries);
  for (const entry of entries) {
    if (!POSTS_ID_RE.test(entry.id) || entry.id.includes('/')) {
      throw new Error(`[content] 非法 posts id:${entry.id}`);
    }
    if (/^\d+$/.test(entry.id)) {
      throw new Error(`[content] posts id 不能是纯数字:${entry.id}`);
    }
  }
}

export function assertDigestIds(entries: CollectionEntry<'digest'>[]): void {
  const files = scanSourceDir('digest', 'src/content/digest');
  for (const name of files) {
    const id = name.slice(0, -3);
    if (!DIGEST_DATE_RE.test(id) || !isRealDate(id)) {
      throw new Error(`[content] 非法 digest 文件名(须为有效 YYYY-MM-DD.md,不可用 slug 规避):${name}`);
    }
  }
  assertCountMatches('digest', files, entries);
  for (const entry of entries) {
    if (entry.id !== entry.data.date) {
      throw new Error(`[content] digest id 与 date 不一致:id=${entry.id} date=${entry.data.date}`);
    }
  }
}
