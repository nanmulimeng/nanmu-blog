import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const posts = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/posts' }),
  schema: z
    .object({
      title: z.string().trim().min(1),
      pubDate: z.coerce.date(),
      tags: z.array(z.string()).default([]),
      draft: z.boolean().default(false),
    })
    // strict:未知键(含 slug)在内容入库前直接构建失败,不允许用 slug 改写最终 id(Task 8a)
    .strict(),
});

const digest = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/digest' }),
  schema: z
    .object({
      date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine((value) => Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value, '日期必须是有效的YYYY-MM-DD'),
      generated: z.literal(true),
      ai_model: z.string().trim().min(1),
      entry_count: z.number().int().nonnegative(),
      cost_cny: z.number().finite().nonnegative(),
      // 未决预占标注(digest-design §3.4 三处口径一致);default(false)
      // 仅为旧文件兼容——新生成文件必须显式写布尔值由 engine 组装断言
      // (Task 16:assemble 产物总含显式 cost_pending),两职责不混在 schema
      cost_pending: z.boolean().default(false),
    })
    // strict:同 posts,未知键(含 slug)入库前拒绝(Task 8a)
    .strict(),
});

export const collections = { posts, digest };
