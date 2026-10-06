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

// cost_pending 期的成本标注(digest-design §3.4:列表/详情/正文三处口径
// 一致;正文标注由 engine assemble 保证,此处验渲染侧两处)
{
  const digestSrc = new URL('../src/content/digest/', import.meta.url);
  if (existsSync(digestSrc)) {
    for (const f of readdirSync(digestSrc)) {
      if (!f.endsWith('.md')) continue;
      const src = readFileSync(new URL(f, digestSrc), 'utf8');
      if (!/^cost_pending:\s*true\s*$/m.test(src)) continue;
      const id = f.replace(/\.md$/, '');
      const detail = readFileSync(new URL(`digest/${id}/index.html`, dist), 'utf8');
      if (!detail.includes('含未决预占')) problems.push(`cost_pending 期 ${id} 详情页缺成本标注`);
      const list = readFileSync(new URL('digest/index.html', dist), 'utf8');
      if (!list.includes('含未决预占')) problems.push(`cost_pending 期 ${id} 列表页缺成本标注`);
    }
  }
}

if (problems.length) {
  console.error('SMOKE FAIL:\n' + problems.join('\n'));
  process.exit(1);
}
console.log('smoke ok: 必需产物/永久草稿/零script/RSS基本结构检查通过(XML解析另验)');
