import type { CollectionEntry } from 'astro:content';

// 共享内容路径校验(Task 5 Step 0 契约):
// - 接收完整 collection(含草稿),不自行调用 getCollection
// - posts id:小写英文数字短横线、不允许嵌套(无 /)、不允许纯数字(与分页路由冲突)
// - digest id 必须与 frontmatter date 一致
// - 所有内容出口(页面/RSS)在过滤/分页前调用;错误带 entry id,抛出使构建非零

const POSTS_ID_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

export function assertPostsIds(entries: CollectionEntry<'posts'>[]): void {
  for (const entry of entries) {
    if (!POSTS_ID_RE.test(entry.id) || entry.id.includes('/')) {
      throw new Error(`[content] 非法 posts id(须为小写英文数字短横线、非嵌套、非纯数字):${entry.id}`);
    }
    if (/^\d+$/.test(entry.id)) {
      throw new Error(`[content] posts id 不能是纯数字(与分页路由冲突):${entry.id}`);
    }
  }
}

export function assertDigestIds(entries: CollectionEntry<'digest'>[]): void {
  for (const entry of entries) {
    if (entry.id !== entry.data.date) {
      throw new Error(`[content] digest id 与 date 不一致:id=${entry.id} date=${entry.data.date}`);
    }
  }
}
