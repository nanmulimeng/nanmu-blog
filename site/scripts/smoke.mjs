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
// 客户端脚本白名单(ADR-0010):全站页允许且仅允许 /scripts/site.js 与
// Base.astro 的首帧内联主题脚本(内容逐字比对,防白名单内夹带);
// 首页(dist 根 index.html)额外允许 /scripts/home.js(W5-W8 页面侧)
// 与 /3d/boot6.js(module 场景加载器,批次 2)——其余任何页出现即
// 失败(页面范围限定)
const INLINE_THEME = "try{var m=localStorage.getItem('nm-theme');if(m==='light'||m==='dark')document.documentElement.dataset.theme=m}catch(e){}";
function checkScripts(html, pathname, extraSrcs = []) {
  const allowed = new Set(['/scripts/site.js', ...extraSrcs]);
  const tags = html.match(/<script\b[\s\S]*?<\/script>/gi) || [];
  for (const tag of tags) {
    const src = (tag.match(/\ssrc=["']([^"']+)["']/) || [])[1];
    if (src !== undefined) {
      if (!allowed.has(src)) problems.push(`非白名单脚本 src=${src}: ${pathname}`);
      continue;
    }
    const body = tag.replace(/^<script\b[^>]*>/i, '').replace(/<\/script>\s*$/i, '').trim();
    if (body !== INLINE_THEME) problems.push(`非白名单内联脚本: ${pathname}`);
  }
}
function checkHtml(dir, atDistRoot) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const url = new URL(entry.name + (entry.isDirectory() ? '/' : ''), dir);
    if (entry.isDirectory()) checkHtml(url, false);
    else if (entry.name.endsWith('.html')) {
      const html = readFileSync(url, 'utf8');
      if (html.includes('drafts-example')) problems.push(`草稿链接泄漏: ${url.pathname}`);
      const isIndex = atDistRoot && entry.name === 'index.html';
      checkScripts(html, url.pathname, isIndex ? ['/scripts/home.js', '/3d/boot6.js'] : []);
    }
  }
}
if (existsSync(dist)) checkHtml(dist, true);

// 夹具泄漏检查(审计 P1-8):tests/fixtures 中的同名 .md 出现在生产源
// 目录 = 正常构建会把夹具公开为正式日报页+RSS;夹具只允许经
// verify-fixture.mjs 的临时构建副本验证(临时副本注入夹具是预期行为,
// 该上下文置 NANMU_FIXTURE_BUILD=1 跳过本检查)
if (!process.env.NANMU_FIXTURE_BUILD) {
  const fixtures = new URL('../tests/fixtures/', import.meta.url);
  if (existsSync(fixtures)) {
    const names = new Set(readdirSync(fixtures).filter((f) => f.endsWith('.md')));
    const digestSrc = new URL('../src/content/digest/', import.meta.url);
    if (existsSync(digestSrc)) {
      for (const f of readdirSync(digestSrc)) {
        if (names.has(f)) problems.push(`夹具泄漏进生产源目录: ${f}`);
      }
    }
  }
}

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
      const detailUrl = new URL(`digest/${id}/index.html`, dist);
      if (!existsSync(detailUrl)) {
        problems.push(`cost_pending 期 ${id} 无详情页(dist 与源目录不一致)`);
        continue;
      }
      const detail = readFileSync(detailUrl, 'utf8');
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
console.log('smoke ok: 必需产物/永久草稿/脚本白名单/RSS基本结构检查通过(XML解析另验)');
