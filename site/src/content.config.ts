import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const posts = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/posts' }),
  schema: z.object({
    title: z.string().trim().min(1),
    pubDate: z.coerce.date(),
    tags: z.array(z.string()).default([]),
    draft: z.boolean().default(false),
  }),
});

const digest = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/digest' }),
  schema: z.object({
    date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine((value) => Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value, '日期必须是有效的YYYY-MM-DD'),
    generated: z.literal(true),
    ai_model: z.string().trim().min(1),
    entry_count: z.number().int().nonnegative(),
    cost_cny: z.number().finite().nonnegative(),
  }),
});

export const collections = { posts, digest };
