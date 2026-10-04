import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import { SITE_TITLE, SITE_DESC } from '../consts';
import { assertPostsIds } from '../lib/content';

export async function GET(context) {
  const all = await getCollection('posts');
  assertPostsIds(all);
  const posts = all
    .filter(({ data }) => !data.draft)
    .sort((a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf() || a.id.localeCompare(b.id));
  return rss({
    title: SITE_TITLE,
    description: SITE_DESC,
    site: context.site,
    items: posts.map((p) => ({
      title: p.data.title,
      pubDate: p.data.pubDate,
      link: `/posts/${p.id}/`,
    })),
  });
}
