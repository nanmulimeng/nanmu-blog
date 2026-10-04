import { readFileSync, existsSync, readdirSync } from 'node:fs';

const dist = new URL('../dist/', import.meta.url);
const mustExist = [
  'index.html', 'posts/index.html', 'digest/index.html',
  'about/index.html', 'rss.xml', 'digest.xml', '404.html',
];
const problems = [];
for (const f of mustExist) {
  if (!existsSync(new URL(f, dist))) problems.push(`缺失 ${f}`);
}

for (const f of ['rss.xml', 'digest.xml']) {
  if (!existsSync(new URL(f, dist))) continue;
  const xml = readFileSync(new URL(f, dist), 'utf8');
  if (!xml.includes('<rss') || !xml.includes('<channel>')) problems.push(`${f} 缺少RSS结构`);
  if (xml.includes('drafts-example')) problems.push(`草稿泄漏到 ${f}`);
}
if (existsSync(new URL('posts/drafts-example/index.html', dist))) problems.push('草稿详情泄漏');
function checkHtml(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const url = new URL(entry.name + (entry.isDirectory() ? '/' : ''), dir);
    if (entry.isDirectory()) checkHtml(url);
    else if (entry.name.endsWith('.html')) {
      const html = readFileSync(url, 'utf8');
      if (html.includes('drafts-example')) problems.push(`草稿链接泄漏: ${url.pathname}`);
      if (/<script\b/i.test(html)) problems.push(`客户端脚本: ${url.pathname}`);
    }
  }
}
if (existsSync(dist)) checkHtml(dist);

if (problems.length) {
  console.error('SMOKE FAIL:\n' + problems.join('\n'));
  process.exit(1);
}
console.log('smoke ok: 必需产物/永久草稿/零script/RSS基本结构检查通过(XML解析另验)');
