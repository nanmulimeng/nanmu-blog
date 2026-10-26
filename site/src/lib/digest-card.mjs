// digest-card:日报 markdown(引擎 assemble 产物)→ 结构化卡片数组。
// 渲染层专用(ADR-0013 aihot 式卡片流);不改产物、不改引擎。
// 格式契约与样例见 tests/digest-card.test.mjs 头注。
const SECTION_RE = /^## (.+)$/;
const HEADING_RE = /^### (.+)$/;
const LIST_RE = /^- (.+)$/;
const REASON_TAIL_RE = /(.*)\s*\[来源\]\(([^)]+)\)\(([^()·]+)·\s*展示分\s*(\d+)\)\s*$/;
const GLANCE_RE = /^\[(.+?)\]\(([^)]+)\)——(.+?)\(([^()·]+)·\s*展示分\s*(\d+)\)\s*$/;

// markdown 转义反转(产物里 "\." "\-" 等;只处理标点前反斜杠)
const unescapeMd = (s) => s.replace(/\\([.\-`*_{}[\]()#+!])/g, '$1');

/** @returns {{section:string,title:string,url:string,summary:string,reason:string|null,source:string,score:number}[]} */
export function parseDigestCards(body) {
  const lines = String(body || '').split(/\r?\n/);
  const cards = [];
  let section = null;
  let current = null; // 板块内 "### 标题" 待收条目
  let summaries = [];

  const pushCurrent = () => {
    if (current) {
      current.summary = summaries.join(' ');
      cards.push(current);
    }
    current = null;
    summaries = [];
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    let m;
    if ((m = line.match(SECTION_RE))) {          // "## 板块(门槛)"
      pushCurrent();
      section = m[1].replace(/\(.*\)$/, '').trim();
      continue;
    }
    if (section && (m = line.match(HEADING_RE))) { // "### 标题"
      pushCurrent();
      current = { section, title: unescapeMd(m[1]), url: '', summary: '',
                  reason: null, source: '', score: 0 };
      continue;
    }
    if (!section || !line.startsWith('- ')) continue;
    const item = line.slice(2);

    if (current) {                                // 头条/精选:摘要行与理由行
      const r = item.match(REASON_TAIL_RE);
      if (r) {
        current.reason = unescapeMd(r[1].trim()).replace(/\s+$/, '');
        current.url = r[2];
        current.source = r[3].trim();
        current.score = Number(r[4]);
      } else {
        summaries.push(unescapeMd(item));
      }
      continue;
    }
    const g = item.match(GLANCE_RE);              // 一瞥:"- [标题](url)——摘要(来源 · 展示分 N)"
    if (g) {
      cards.push({ section, title: unescapeMd(g[1]), url: g[2],
                   summary: unescapeMd(g[3].trim()), reason: null,
                   source: g[4].trim(), score: Number(g[5]) });
    }
  }
  pushCurrent();
  return cards;
}
