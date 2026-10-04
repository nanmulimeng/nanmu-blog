import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import { SITE_TITLE } from '../consts';
import { assertDigestIds } from '../lib/content';

export async function GET(context) {
  const all = await getCollection('digest');
  assertDigestIds(all);
  const digests = all
    .sort((a, b) => (a.data.date === b.data.date ? a.id.localeCompare(b.id) : a.data.date < b.data.date ? 1 : -1));
  return rss({
    title: `${SITE_TITLE} · AI 日报`,
    description: 'AI 引擎自动生成与精选的每日日报',
    site: context.site,
    items: digests.map((d) => ({
      title: `${d.data.date} 日报`,
      pubDate: new Date(`${d.data.date}T08:30:00+08:00`),
      link: `/digest/${d.id}/`,
    })),
  });
}
