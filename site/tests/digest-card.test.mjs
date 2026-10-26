// digest-card(ADR-0013 渲染层):日报 markdown → 结构化卡片。
// 契约=engine assemble 产物格式(见 site/src/content/digest/*.md):
//   "## 板块(门槛)" 分节;"### 标题" 后跟 "- 摘要" 与 "- 理由 [来源](url)(src · 展示分 N)";
//   一瞥节为 "- [标题](url)——摘要(src · 展示分 N)"。
// markdown 转义(标题中 "K3\.1")提取时反转义为 "K3.1"。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseDigestCards } from '../src/lib/digest-card.mjs';

const BODY = `## 头条(展示分 ≥ 80)

### 月之暗面发布 Kimi K3\\.1 Pro,上下文窗口达 100 万 token

- 月之暗面推出 Kimi K3\\.1 系列首个模型,为 3T 级开放权重模型。
- 了解开放权重大模型的最新进展。[来源](https://aihot.news/items/aaa)(AIHOT · 展示分 83)

## 精选(75-79)

### MiniMax 开放 M3.1 Flash 权重

- 总参数 428B、每 token 激活 23B。
- 可获取开放权重模型。[来源](https://aihot.news/items/bbb)(Techmeme · 展示分 75)

## 值得一瞥(压线入选)

- [AISI 报告分析 Mythos 5 对齐失败](https://aihot.news/items/ccc)——英国 AISI 发布技术报告,分析对齐成因。(AIHOT · 展示分 72)
`;

test('解析三板块与条目字段', () => {
  const cards = parseDigestCards(BODY);
  assert.equal(cards.length, 3);
  const [head, feat, glance] = cards;
  assert.equal(head.section, '头条');
  assert.equal(head.title, '月之暗面发布 Kimi K3.1 Pro,上下文窗口达 100 万 token');
  assert.equal(head.url, 'https://aihot.news/items/aaa');
  assert.match(head.summary, /3T 级开放权重模型/);
  assert.equal(head.reason, '了解开放权重大模型的最新进展。');
  assert.equal(head.source, 'AIHOT');
  assert.equal(head.score, 83);
  assert.equal(feat.section, '精选');
  assert.equal(feat.source, 'Techmeme');
  assert.equal(glance.section, '值得一瞥');
  assert.equal(glance.title, 'AISI 报告分析 Mythos 5 对齐失败');
  assert.equal(glance.url, 'https://aihot.news/items/ccc');
  assert.match(glance.summary, /英国 AISI 发布技术报告/);
  assert.equal(glance.reason, null, '一瞥无独立理由行');
  assert.equal(glance.score, 72);
});

test('引言块与空输入', () => {
  assert.deepEqual(parseDigestCards(''), []);
  const onlyQuote = parseDigestCards('> AI 生成与精选 · 模型 deepseek-flash');
  assert.deepEqual(onlyQuote, []);
});

test('标题内联链接不误判为一瞥', () => {
  const tricky = parseDigestCards(`## 头条(展示分 ≥ 80)

### 标题甲

- 摘要甲,含 [某站](https://x.example) 链接的句子。
- 理由甲。[来源](https://aihot.news/items/ddd)(AIHOT · 展示分 81)
`);
  assert.equal(tricky.length, 1);
  assert.equal(tricky[0].url, 'https://aihot.news/items/ddd', '来源链接以理由行为准');
  assert.match(tricky[0].summary, /某站/);
});
