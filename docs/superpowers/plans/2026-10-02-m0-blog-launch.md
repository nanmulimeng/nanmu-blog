# M0 博客上线 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 nanmu-blog 的 M0——Astro 5 静态博客(手写文章 + 空置的 AI 日报栏目)+ git push 自动构建部署 + blog.nanmu.xyz 子域名上线。

**Architecture:** monorepo,`site/` 是 Astro 5 站点,`deploy/` 存服务器部署工件。写作流:本地写 markdown → `git push` main → 服务器 bare repo 的 post-receive hook 后台 flock 构建(`releases/<sha>/dist`)→ `mv -T` 原子切换 `current` symlink → Caddy 静态服务。digest collection 与 schema 契约 M0 就位但内容空置(M1 由引擎填充)。

**Tech Stack:** Astro 5(glob loader Content Layer)、@astrojs/rss、Node ≥18.17.1、Caddy 2(服务器已有)、bash git hooks。

**Spec:** `docs/superpowers/specs/2026-10-02-nanmu-blog-design.md`(本计划从 spec 立论,执行者需同时读 spec;关键依据 §2 铁律、§4/§4.1、§7、§8、§9-M0)

## Global Constraints

- Astro 5,配置文件是 `site/src/content.config.ts`(不是旧版 `src/content/config.ts`)
- **零客户端 JS**:明暗主题只用 CSS `prefers-color-scheme`,不引入任何 JS 框架/主题切换脚本(spec 铁律 6)
- 页面 UI 中文;站名 `nanmu blog`(常量放 `site/src/consts.ts`)
- 站点 URL `https://blog.nanmu.xyz`(astro.config `site`,RSS 依赖它生成绝对链接)
- posts schema:`title: string`、`pubDate: coerce.date`、`tags: string[] default []`、`draft: boolean default false`
- digest schema:`date: string`、`generated: literal true`、`ai_model: string`、`entry_count: number`、`cost_cny: number`
- **digest 栏目从 M0 起就带 AI 生成标注**(spec 铁律 7):digest 列表页显式说明本栏目内容由 AI 生成
- **服务器凭据不落盘**:123.56.223.97 的密码只允许出现在交互式命令行输入,禁止写入任何文件/脚本/配置(历史约定)
- 每次 push 到 main 必须可部署:commit 前本地 `npm run verify`(build + 冒烟)必须绿
- 保留最近 5 个 release 目录,更旧的删除;回滚 = 切 symlink
- 本计划完成后 M1/M2 各自另写 plan,不在本计划内实现任何 AI 功能

## Review Focus

spec 未显式测试、但最容易咬人的五类输入/故障,及钉住它们的任务:

1. **非法 digest frontmatter 必须让构建失败**(schema 即契约,spec §4.1)——Task 3 步骤验证"缺 generated 字段时 build FAIL"。
2. **digest collection 为空时 `/digest/` 页面与 `/digest.xml` 必须优雅空态,不能 500**(M0 上线时 digest 就是空的)——Task 5/6 的空态代码与验证;Task 7 冒烟断言两文件存在。
3. **`draft: true` 的文章必须从列表、详情页、RSS 全部排除**——Task 5 getStaticPaths/getCollection 过滤;Task 7 冒烟断言 `drafts-example` 不出现在 rss.xml。
4. **RSS 标题特殊字符(`&`、`<`)必须正确转义**——Task 6 用临时 fixture 验证输出含 `&amp;`。
5. **部署韧性:推非 main 分支不触发部署;构建失败的 commit 不切换 symlink(线上保持旧版);并发 push 由 flock 串行**——Task 8 脚本逻辑;Task 9 服务器实测(推坏 commit 后线上仍 200)。

---

### Task 1: 仓库骨架与文档基线

**Files:**
- Create: `AGENTS.md`、`README.md`、`CLAUDE.md`、`.gitignore`、`.gitattributes`

**Interfaces:**
- Consumes: 无(首任务)
- Produces: 仓库根文档三件套(后续所有任务的执行者先读 AGENTS.md);`.gitignore` 保证 node_modules/dist/.astro 不入库;`.gitattributes` 保证 hook 脚本 LF(Task 8/9 依赖)

- [ ] **Step 1: 写 .gitignore 与 .gitattributes**

`.gitignore`:
```
node_modules/
dist/
.astro/
.env
```

`.gitattributes`:
```
* text=auto
*.sh text eol=lf
deploy/post-receive text eol=lf
```

- [ ] **Step 2: 写 AGENTS.md**

```markdown
# AGENTS.md — nanmu-blog

极简静态博客(Astro 5)+ AI 引擎(Python,读 topic-digest 数据产日报)+ RAG(自用问答)。
当前阶段:M0 博客上线。完整设计与八条铁律见 `docs/superpowers/specs/2026-10-02-nanmu-blog-design.md`(§2 必读)。

## 结构
- `site/` — Astro 5 站点(手写文章 posts + AI 日报 digest)
- `engine/` — AI 引擎(M1,未创建)
- `docs/` — specs/plans/ops 文档系统
- `deploy/` — 服务器部署工件(hook 与构建脚本)

## 常用命令(在 site/ 下)
- `npm run dev` 本地开发
- `npm run build` 构建
- `npm run verify` build + 冒烟检查(commit 前必须绿)

## 部署
push 到 main → 服务器 post-receive 后台构建原子发布。Runbook:`docs/ops/deploy.md`。
回滚 = 切 `/var/www/nanmu-blog/current` symlink 到旧 release。

## 会话交接
每个开发会话结束在 `docs/sessions/` 写交接记录,格式见 spec §8.1
(objective/state/disposition/next_action/omissions,声明分级 verified|declared)。
```

- [ ] **Step 3: 写 README.md 与 CLAUDE.md**

`README.md`:
```markdown
# nanmu-blog

个人博客:手写文章(Astro 5 静态站)+ AI 日报(引擎读 topic-digest 数据自动精选发布)+ RAG 知识库(自用)。

前项目结论:nanmuli-blog(废弃,过度设计教训)、topic-digest(在产,爬取试点)、AIHOT/PowerContext(借鉴对象)——见 spec §1。

## 快速开始
    cd site && npm install && npm run dev

## 部署
push main 即部署,详见 docs/ops/deploy.md。
```

`CLAUDE.md`(与 AGENTS.md 同口径):
```markdown
# nanmu-blog 项目记忆

读 `AGENTS.md`(同口径)。补充:中文回复;修改前先读相关文件;不确定即查;
服务器凭据不落盘;commit 前 `cd site && npm run verify` 必须绿。
设计文档:docs/superpowers/specs/2026-10-02-nanmu-blog-design.md。
```

- [ ] **Step 4: 验证并提交**

Run: `ls AGENTS.md README.md CLAUDE.md .gitignore .gitattributes && git status --short`
Expected: 五个文件都是 untracked/新增,无其他意外文件。

```bash
git add AGENTS.md README.md CLAUDE.md .gitignore .gitattributes
git commit -m "chore: 仓库骨架与文档基线(AGENTS/README/CLAUDE + gitignore)"
```

---

### Task 2: Astro 5 脚手架

**Files:**
- Create: `site/`(npm create astro 生成:package.json、astro.config.mjs、src/pages/index.astro、tsconfig.json 等)

**Interfaces:**
- Consumes: Task 1 的 .gitignore(排除 node_modules/dist/.astro)
- Produces: `site/` 可构建的 Astro 5 项目;`npm run build` 产出 `site/dist/`(Task 7 依赖);astro.config 的 `site` URL(Task 6 RSS 依赖)

- [ ] **Step 1: 生成最小模板**

在仓库根目录运行:
```bash
npm create astro@latest site -- --template minimal --no-install --no-git --yes
cd site && npm install && npm install @astrojs/rss
```
Expected: 无交互报错;`site/package.json` 含 astro ^5.x 与 @astrojs/rss。

- [ ] **Step 2: 配置 site URL**

`site/astro.config.mjs` 全文替换为:
```js
import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://blog.nanmu.xyz',
});
```

- [ ] **Step 3: 验证构建**

Run: `cd site && npm run build`
Expected: 结束输出 "complete";`site/dist/index.html` 存在。

- [ ] **Step 4: 提交**

```bash
git add site
git commit -m "feat: Astro 5 最小脚手架(site URL 指向 blog.nanmu.xyz)"
```

---

### Task 3: 双 content collection 与 schema 契约

**Files:**
- Create: `site/src/content.config.ts`
- Create: `site/src/content/posts/hello-nanmu-blog.md`(首篇草稿,Task 10 发布)
- Create: `site/src/content/posts/drafts-example.md`(draft 排除的永久 fixture)
- Test: 构建失败/成功验证(手工步骤,Astro 无单测框架;`npm run build` 即 schema 校验器)

**Interfaces:**
- Consumes: Task 2 的 site/ 项目
- Produces: collection `posts` 与 `digest`(字段见 Global Constraints)——Task 5/6 用 `getCollection('posts'|'digest')` 消费;digest 目录 `site/src/content/digest/`(M1 引擎写入目标,路径契约从此固定)

- [ ] **Step 1: 写 content.config.ts**

```ts
import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const posts = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/posts' }),
  schema: z.object({
    title: z.string(),
    pubDate: z.coerce.date(),
    tags: z.array(z.string()).default([]),
    draft: z.boolean().default(false),
  }),
});

const digest = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/digest' }),
  schema: z.object({
    date: z.string(),
    generated: z.literal(true),
    ai_model: z.string(),
    entry_count: z.number(),
    cost_cny: z.number(),
  }),
});

export const collections = { posts, digest };
```

- [ ] **Step 2: 建目录与首篇内容**

`mkdir -p site/src/content/digest`(空目录,M1 填充)。

`site/src/content/posts/hello-nanmu-blog.md`:
```markdown
---
title: 你好,nanmu-blog
pubDate: 2026-10-02
tags: [随笔]
draft: true
---

这个博客从三段历史里长出来:一个因过度设计而停摆的旧博客、一个在服务器上安静跑了一个月零故障的爬取试点、两个值得借鉴的开源项目。

写作在这里,AI 日报会在另一个栏目出现——那是引擎自己读数据、自己挑、自己写的。
```

`site/src/content/posts/drafts-example.md`:
```markdown
---
title: 草稿示例(不会出现在任何页面)
pubDate: 2026-10-02
draft: true
---

这是 draft 功能的永久 fixture:它必须被列表、详情页、RSS 同时排除。
```

- [ ] **Step 3: 契约验证——非法 digest frontmatter 必须让构建失败**

临时创建 `site/src/content/digest/2026-10-01.md`:
```markdown
---
date: '2026-10-01'
ai_model: deepseek-chat
entry_count: 0
cost_cny: 0
---

缺 generated 字段,构建必须失败。
```

Run: `cd site && npm run build`
Expected: **FAIL**,报错指向 digest schema(generated 字段缺失/literal 不匹配)。这是 spec §4.1"schema 即契约"的验证。

删除该临时文件,再跑 `npm run build`
Expected: PASS(两个 draft 文章存在但被排除不影响构建;此刻还没有页面消费 collection,下一任务补)。

- [ ] **Step 4: 提交**

```bash
git add site/src/content.config.ts site/src/content
git commit -m "feat: posts/digest 双 collection,schema 即契约(含 draft fixture)"
```

---

### Task 4: 基础布局与零 JS 明暗主题

**Files:**
- Create: `site/src/consts.ts`、`site/src/styles/global.css`、`site/src/layouts/Base.astro`、`site/src/components/Header.astro`

**Interfaces:**
- Consumes: Task 2 的项目
- Produces: `Base.astro`(props:`title: string`、`description?: string`)——Task 5 所有页面用它包壳;`consts.ts` 导出 `SITE_TITLE = 'nanmu blog'`、`SITE_DESC = '个人文章与 AI 日报'`(Task 6 RSS 消费);`global.css` 的 CSS 变量体系(`--bg/--fg/--muted/--link/--border/--card`)

- [ ] **Step 1: consts.ts**

```ts
export const SITE_TITLE = 'nanmu blog';
export const SITE_DESC = '个人文章与 AI 日报';
```

- [ ] **Step 2: global.css(零 JS 明暗主题)**

```css
:root {
  color-scheme: light dark;
  --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280;
  --link: #2563eb; --border: #e5e7eb; --card: #f9fafb;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f172a; --fg: #e2e8f0; --muted: #94a3b8;
    --link: #60a5fa; --border: #1e293b; --card: #1e293b;
  }
}
* { box-sizing: border-box; }
body {
  background: var(--bg); color: var(--fg); margin: 0; line-height: 1.75;
  font-family: system-ui, -apple-system, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}
main { max-width: 42rem; margin: 0 auto; padding: 1.5rem; }
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
h1, h2, h3 { line-height: 1.3; }
.muted { color: var(--muted); font-size: 0.875rem; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 0.75rem; }
article img { max-width: 100%; }
pre { overflow-x: auto; padding: 0.75rem; border-radius: 6px; background: var(--card); border: 1px solid var(--border); }
hr { border: none; border-top: 1px solid var(--border); margin: 2rem 0; }
```

- [ ] **Step 3: Header.astro**

```astro
---
const { pathname } = Astro.url;
const links = [
  { href: '/', label: '首页' },
  { href: '/posts/', label: '文章' },
  { href: '/digest/', label: '日报' },
  { href: '/about/', label: '关于' },
];
---
<header>
  <nav>
    {links.map((l) => (
      <a href={l.href} class={pathname.startsWith(l.href) && l.href !== '/' ? 'active' : ''}>{l.label}</a>
    ))}
  </nav>
</header>
<style>
  header { border-bottom: 1px solid var(--border); }
  nav { max-width: 42rem; margin: 0 auto; padding: 0.9rem 1.5rem; display: flex; gap: 1.1rem; }
  a { color: var(--muted); }
  a.active, a:hover { color: var(--fg); text-decoration: none; }
</style>
```

- [ ] **Step 4: Base.astro**

```astro
---
import Header from '../components/Header.astro';
import { SITE_TITLE, SITE_DESC } from '../consts';
import '../styles/global.css';

interface Props { title?: string; description?: string; }
const { title, description = SITE_DESC } = Astro.props;
const pageTitle = title ? `${title} · ${SITE_TITLE}` : SITE_TITLE;
---
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="description" content={description} />
    <title>{pageTitle}</title>
  </head>
  <body>
    <Header />
    <main><slot /></main>
    <footer class="muted" style="max-width:42rem;margin:0 auto;padding:1.5rem">
      © {new Date().getFullYear()} nanmu ·
      <a href="/rss.xml">文章 RSS</a> ·
      <a href="/digest.xml">日报 RSS</a>
    </footer>
  </body>
</html>
```

- [ ] **Step 5: 验证并提交**

Run: `cd site && npm run build`
Expected: PASS(布局尚未被引用,先确认无语法错误)。

```bash
git add site/src/consts.ts site/src/styles site/src/layouts site/src/components
git commit -m "feat: Base 布局与零 JS 明暗主题(prefers-color-scheme)"
```

---

### Task 5: 页面与路由(含空态与 draft 排除)

**Files:**
- Modify: `site/src/pages/index.astro`(替换模板首页)
- Create: `site/src/pages/about.astro`、`site/src/pages/404.astro`、`site/src/pages/posts/[...page].astro`、`site/src/pages/posts/[id].astro`、`site/src/pages/digest/[...page].astro`、`site/src/pages/digest/[id].astro`

**Interfaces:**
- Consumes: Task 3 的 collections(`getCollection('posts'|'digest')`,posts 字段 `title/pubDate/tags/draft`,digest 字段 `date/generated/ai_model/entry_count/cost_cny`);Task 4 的 `Base.astro`、global.css 变量
- Produces: 路由 `/`、`/about/`、`/posts/`、`/posts/{id}/`、`/digest/`、`/digest/{id}/`、`/404`(Task 7 冒烟清单依赖);条目排序契约:posts 按 pubDate 降序,digest 按 date 降序

- [ ] **Step 1: 首页 index.astro**

```astro
---
import { getCollection } from 'astro:content';
import Base from '../layouts/Base.astro';

const posts = (await getCollection('posts', ({ data }) => !data.draft))
  .sort((a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf())
  .slice(0, 5);
const digests = (await getCollection('digest'))
  .sort((a, b) => (a.data.date < b.data.date ? 1 : -1));
---
<Base>
  <h1>最新文章</h1>
  {posts.map((p) => (
    <div class="card">
      <a href={`/posts/${p.id}/`}><strong>{p.data.title}</strong></a>
      <div class="muted">{p.data.pubDate.toLocaleDateString('zh-CN')} · {p.data.tags.join(' / ')}</div>
    </div>
  ))}
  <h2 style="margin-top:2.5rem">AI 日报</h2>
  {digests.length === 0 ? (
    <p class="muted">日报尚未开始——本栏目内容由 AI 自动生成与筛选(M1 上线后每日一期),每期标注生成模型与成本。</p>
  ) : (
    digests.slice(0, 3).map((d) => (
      <div class="card">
        <a href={`/digest/${d.id}/`}><strong>{d.data.date} 日报</strong></a>
        <div class="muted">{d.data.entry_count} 条 · 由 {d.data.ai_model} 生成</div>
      </div>
    ))
  )}
</Base>
```

- [ ] **Step 2: 文章列表(分页)posts/[...page].astro**

```astro
---
import { getCollection } from 'astro:content';
import Base from '../../layouts/Base.astro';

export async function getStaticPaths({ paginate }) {
  const posts = (await getCollection('posts', ({ data }) => !data.draft))
    .sort((a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf());
  return paginate(posts, { pageSize: 10 });
}
const { page } = Astro.props;
---
<Base title="文章">
  <h1>文章</h1>
  {page.data.map((p) => (
    <div class="card">
      <a href={`/posts/${p.id}/`}><strong>{p.data.title}</strong></a>
      <div class="muted">{p.data.pubDate.toLocaleDateString('zh-CN')} · {p.data.tags.join(' / ')}</div>
    </div>
  ))}
  {page.url.prev && <a href={page.url.prev}>← 上一页</a>}
  {page.url.next && <a href={page.url.next}>下一页 →</a>}
</Base>
```

- [ ] **Step 3: 文章详情 posts/[id].astro**

```astro
---
import { getCollection } from 'astro:content';
import Base from '../../layouts/Base.astro';

export async function getStaticPaths() {
  const posts = await getCollection('posts', ({ data }) => !data.draft);
  return posts.map((p) => ({ params: { id: p.id }, props: { post: p } }));
}
const { post } = Astro.props;
const { Content } = await post.render();
---
<Base title={post.data.title} description={post.data.title}>
  <h1>{post.data.title}</h1>
  <p class="muted">{post.data.pubDate.toLocaleDateString('zh-CN')} · {post.data.tags.join(' / ')}</p>
  <hr />
  <article><Content /></article>
</Base>
```

- [ ] **Step 4: 日报列表(分页 + 空态 + AI 标注)digest/[...page].astro**

```astro
---
import { getCollection } from 'astro:content';
import Base from '../../layouts/Base.astro';

export async function getStaticPaths({ paginate }) {
  const digests = (await getCollection('digest'))
    .sort((a, b) => (a.data.date < b.data.date ? 1 : -1));
  return paginate(digests, { pageSize: 10 });
}
const { page } = Astro.props;
---
<Base title="AI 日报">
  <h1>AI 日报</h1>
  <p class="muted">本栏目由 AI 引擎自动生成:读取聚合数据、评分精选、撰写摘要。每期标注生成模型与成本。</p>
  {page.data.length === 0 ? (
    <p class="muted">尚未发布任何日报(M1 上线后每日一期)。</p>
  ) : (
    page.data.map((d) => (
      <div class="card">
        <a href={`/digest/${d.id}/`}><strong>{d.data.date} 日报</strong></a>
        <div class="muted">{d.data.entry_count} 条 · 由 {d.data.ai_model} 生成 · 成本 ¥{d.data.cost_cny}</div>
      </div>
    ))
  )}
  {page.url.prev && <a href={page.url.prev}>← 上一页</a>}
  {page.url.next && <a href={page.url.next}>下一页 →</a>}
</Base>
```

- [ ] **Step 5: 日报详情 digest/[id].astro**

```astro
---
import { getCollection } from 'astro:content';
import Base from '../../layouts/Base.astro';

export async function getStaticPaths() {
  const digests = await getCollection('digest');
  return digests.map((d) => ({ params: { id: d.id }, props: { digest: d } }));
}
const { digest } = Astro.props;
const { Content } = await digest.render();
---
<Base title={`${digest.data.date} 日报`} description={`AI 生成 · ${digest.data.entry_count} 条`}>
  <h1>{digest.data.date} 日报</h1>
  <p class="muted">AI 生成({digest.data.ai_model})· {digest.data.entry_count} 条 · 成本 ¥{digest.data.cost_cny}</p>
  <hr />
  <article><Content /></article>
</Base>
```

- [ ] **Step 6: about.astro 与 404.astro**

`site/src/pages/about.astro`:
```astro
---
import Base from '../layouts/Base.astro';
---
<Base title="关于">
  <h1>关于</h1>
  <p>这里是 nanmu 的个人博客:左边是我写的,右边是 AI 挑的。</p>
  <p class="muted">本站由 Astro 静态构建;"日报"栏目内容由 AI 引擎自动生成并标注模型与成本。</p>
</Base>
```

`site/src/pages/404.astro`:
```astro
---
import Base from '../layouts/Base.astro';
---
<Base title="404">
  <h1>404</h1>
  <p class="muted">页面不存在。<a href="/">回首页</a></p>
</Base>
```

- [ ] **Step 7: 验证 draft 排除与空态**

Run: `cd site && npm run build`
Expected: PASS。检查产物:
```bash
ls dist/posts/         # 只有 hello-nanmu-blog(无 drafts-example)
grep -c drafts-example dist/index.html dist/posts/index.html || true   # 都是 0
grep -o "尚未发布任何日报" dist/digest/index.html   # 空态文案存在
```
Expected: `dist/posts/` 下无 drafts-example 页面;两个 grep 计数为 0;digest 空态文案命中。

- [ ] **Step 8: 提交**

```bash
git add site/src/pages
git commit -m "feat: 全部页面路由——首页/文章/日报/关于/404,空态与 draft 排除"
```

---

### Task 6: RSS 双出口

**Files:**
- Create: `site/src/pages/rss.xml.js`、`site/src/pages/digest.xml.js`

**Interfaces:**
- Consumes: Task 3 collections、Task 4 `consts.ts`(`SITE_TITLE/SITE_DESC`)、Task 2 astro.config `site`(经 `context.site`)
- Produces: `/rss.xml`(文章)与 `/digest.xml`(日报)endpoint——Task 7 冒烟依赖;路由契约固定,M1 日报发布后自动进 digest.xml,无需改动

- [ ] **Step 1: rss.xml.js**

```js
import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import { SITE_TITLE, SITE_DESC } from '../consts';

export async function GET(context) {
  const posts = (await getCollection('posts', ({ data }) => !data.draft))
    .sort((a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf());
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
```

- [ ] **Step 2: digest.xml.js(空 feed 也合法)**

```js
import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import { SITE_TITLE } from '../consts';

export async function GET(context) {
  const digests = (await getCollection('digest'))
    .sort((a, b) => (a.data.date < b.data.date ? 1 : -1));
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
```

- [ ] **Step 3: 验证——空 feed 合法、draft 排除、转义**

Run: `cd site && npm run build`
```bash
head -3 dist/rss.xml dist/digest.xml
grep -c drafts-example dist/rss.xml || true   # 0
```
Expected: 两个文件首行均为 `<?xml version="1.0"` 且含 `<rss`;rss.xml 中 drafts-example 计数 0;digest.xml 是合法空 channel(M0 的正常状态)。

转义验证(Review Focus 4):临时把 `hello-nanmu-blog.md` 的 title 改为 `你好,nanmu-blog & <重启>`,先把 frontmatter 的 `draft: true` 改为 `false`,build 后:
```bash
grep -o "nanmu-blog &amp; &lt;重启&gt;" dist/rss.xml
```
Expected: 命中(`&` 与 `<>` 均已转义)。验证后**还原**:title 改回 `你好,nanmu-blog`,`draft` 改回 `true`,重新 build 确认 PASS。

- [ ] **Step 4: 提交**

```bash
git add site/src/pages/rss.xml.js site/src/pages/digest.xml.js
git commit -m "feat: /rss.xml 与 /digest.xml 双 RSS 出口,空 feed 合法"
```

---

### Task 7: 冒烟脚本与一键验证

**Files:**
- Create: `site/scripts/smoke.mjs`
- Modify: `site/package.json`(scripts 加 `verify`)

**Interfaces:**
- Consumes: Task 2 build、Task 5 路由产物、Task 6 RSS 文件(路径契约:`dist/index.html`、`dist/posts/index.html`、`dist/digest/index.html`、`dist/about/index.html`、`dist/rss.xml`、`dist/digest.xml`、`dist/404.html`)
- Produces: `npm run verify`(build + 冒烟)——Global Constraints 规定的 commit 前门槛;M1 引擎的 CI/回滚流程复用同一脚本

- [ ] **Step 1: smoke.mjs**

```js
import { readFileSync, existsSync } from 'node:fs';

const dist = new URL('../dist/', import.meta.url);
const mustExist = [
  'index.html', 'posts/index.html', 'digest/index.html',
  'about/index.html', 'rss.xml', 'digest.xml', '404.html',
];
const problems = [];
for (const f of mustExist) {
  if (!existsSync(new URL(f, dist))) problems.push(`缺失 ${f}`);
}

const rss = readFileSync(new URL('rss.xml', dist), 'utf8');
if (!rss.includes('<rss')) problems.push('rss.xml 不是 RSS');
if (rss.includes('drafts-example')) problems.push('draft 文章泄漏进 rss.xml');

const dxml = readFileSync(new URL('digest.xml', dist), 'utf8');
if (!dxml.includes('<rss')) problems.push('digest.xml 不是 RSS');

if (problems.length) {
  console.error('SMOKE FAIL:\n' + problems.join('\n'));
  process.exit(1);
}
console.log('smoke ok: 7 个必需产物齐全,draft 未泄漏,RSS 合法');
```

- [ ] **Step 2: package.json 加 verify script**

在 `site/package.json` 的 `scripts` 中加入:
```json
"verify": "astro build && node scripts/smoke.mjs"
```

- [ ] **Step 3: 验证**

Run: `cd site && npm run verify`
Expected: build complete 后输出 `smoke ok: ...`。

人为破坏验证(确认脚本真的会拦):临时把 `digest.xml.js` 的 items 改成 `undefined`,重跑
Expected: `SMOKE FAIL` 且退出码非 0。还原后再跑一次确认 `smoke ok`。

- [ ] **Step 4: 提交**

```bash
git add site/scripts/smoke.mjs site/package.json
git commit -m "feat: npm run verify——build+冒烟,commit 前门槛"
```

---

### Task 8: 部署工件与运维文档

**Files:**
- Create: `deploy/post-receive`、`deploy/deploy.sh`、`deploy/Caddyfile.snippet`
- Create: `docs/ops/deploy.md`(runbook,Task 9 逐字执行它)、`docs/architecture.md`

**Interfaces:**
- Consumes: Task 7 的 `npm run build`;仓库结构(site/ 子目录)
- Produces: 服务器工件的标准来源(Task 9 把它们安装到 `/opt/git/nanmu-blog.git/hooks/` 与 Caddy);runbook 是唯一部署真相源,回滚/故障处理写在里面

- [ ] **Step 1: deploy/post-receive**

```bash
#!/bin/bash
# /opt/git/nanmu-blog.git/hooks/post-receive — 只部署 main,后台 flock 构建,立即返回
set -u
NULL_SHA=0000000000000000000000000000000000000000
DEPLOY_BRANCH=refs/heads/main
found=0
while read -r oldrev newrev refname; do
  if [ "$refname" = "$DEPLOY_BRANCH" ] && [ "$newrev" != "$NULL_SHA" ]; then
    found=1
  fi
done
[ "$found" = "1" ] || exit 0
LOG=/opt/git/nanmu-blog-deploy.log
if flock -n /tmp/nanmu-blog-build.lock -c "/opt/git/nanmu-blog.git/hooks/deploy.sh >> $LOG 2>&1"; then
  echo "build queued: $(date -Is)"
else
  echo "$(date -Is) another build in progress, skipped" | tee -a "$LOG"
fi
```

- [ ] **Step 2: deploy/deploy.sh(构建失败不切换 symlink = 线上保持旧版)**

```bash
#!/bin/bash
# /opt/git/nanmu-blog.git/hooks/deploy.sh — 构建到 releases/<sha>,mv -T 原子切换 current
set -euo pipefail

# 服务器 node 可能装在 nvm 下,hook 的非登录 shell 里没有 PATH
if [ -f "$HOME/.nvm/nvm.sh" ]; then . "$HOME/.nvm/nvm.sh"; fi

export GIT_DIR=/opt/git/nanmu-blog.git
RELEASES=/var/www/nanmu-blog/releases
SHA=$(git rev-parse main)
DEST="$RELEASES/$SHA"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

if [ -d "$DEST/dist" ]; then
  echo "$(date -Is) release $SHA already built, skip build"
else
  mkdir -p "$DEST"
  GIT_WORK_TREE="$WORK" git checkout -f main
  cd "$WORK/site"
  npm ci --prefer-offline --cache /opt/git/npm-cache
  npm run build -- --outDir "$DEST/dist"
fi

# 原子切换:先建临时软链再 mv -T(ln -f 有 unlink 窗口,不可用)
ln -sfn "$DEST" /var/www/nanmu-blog/current.tmp
mv -T /var/www/nanmu-blog/current.tmp /var/www/nanmu-blog/current

# 只保留最近 5 个 release
ls -1dt "$RELEASES"/*/ | tail -n +6 | xargs -r rm -rf
echo "$(date -Is) deployed $SHA"
```

- [ ] **Step 3: deploy/Caddyfile.snippet**

```caddyfile
blog.nanmu.xyz {
    root * /var/www/nanmu-blog/current/dist
    encode gzip
    file_server
    handle_errors {
        rewrite * /404.html
        file_server
    }
}
```

(404 用 `handle_errors` 返回真 404 状态码;`try_files` 回退是软 404,不采用。)

- [ ] **Step 4: docs/ops/deploy.md(runbook,Task 9 逐字执行)**

```markdown
# nanmu-blog 部署 runbook

服务器:123.56.223.97(user nanmu,sudo NOPASSWD)。凭据不落盘:密码只在交互输入。

## 0. 前置检查
    ssh nanmu@123.56.223.97 'node -v && which node && ls /opt/git/'
node ≥18.17.1(Astro 5 要求)。若 node 在 nvm 下,记下路径(deploy.sh 已做 nvm 兼容)。

## 1. 目录与 bare repo
    ssh nanmu@123.56.223.97
    sudo mkdir -p /var/www/nanmu-blog/releases && sudo chown -R nanmu:nanmu /var/www/nanmu-blog
    git init --bare /opt/git/nanmu-blog.git
    mkdir -p /opt/git/npm-cache

## 2. 安装 hook 工件(本机仓库根目录执行)
    scp deploy/post-receive deploy/deploy.sh nanmu@123.56.223.97:/opt/git/nanmu-blog.git/hooks/
    ssh nanmu@123.56.223.97 'chmod +x /opt/git/nanmu-blog.git/hooks/post-receive /opt/git/nanmu-blog.git/hooks/deploy.sh'

## 3. SSH 免密(本机;若无 key 先 ssh-keygen -t ed25519)
    type %USERPROFILE%\.ssh\id_ed25519.pub | ssh nanmu@123.56.223.97 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
    ssh nanmu@123.56.223.97 true   # 验证免密

## 4. DNS(用户在域名控制台操作)
添加 A 记录:blog.nanmu.xyz → 123.56.223.97。验证:nslookup blog.nanmu.xyz

## 5. Caddy(先 validate 再 reload——坏配置会连累同机 skills.nanmu.xyz)
    scp deploy/Caddyfile.snippet nanmu@123.56.223.97:/tmp/blog.caddy
    ssh nanmu@123.56.223.97 'sudo sh -c "cat /tmp/blog.caddy >> /etc/caddy/Caddyfile && caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile"'
    # validate 失败:从 /etc/caddy/Caddyfile 删掉刚追加的块,绝不 reload
    ssh nanmu@123.56.223.97 'sudo systemctl reload caddy && sleep 3 && systemctl is-active caddy'
Caddy 自动签 TLS(DNS 生效后)。验证:curl -sI https://blog.nanmu.xyz;同时确认 https://skills.nanmu.xyz 仍 200

## 6. 首次部署与验收
    git remote add server nanmu@123.56.223.97:/opt/git/nanmu-blog.git
    git push server main
    sleep 60 && ssh nanmu@123.56.223.97 'tail -20 /opt/git/nanmu-blog-deploy.log'
    curl -sI https://blog.nanmu.xyz          # 200
    curl -s https://blog.nanmu.xyz/rss.xml | head -5
    curl -s https://blog.nanmu.xyz/digest/ | grep -o "尚未发布任何日报"

## 7. 回滚
    ssh nanmu@123.56.223.97 'ls -1dt /var/www/nanmu-blog/releases/*'
    ssh nanmu@123.56.223.97 'ln -sfn /var/www/nanmu-blog/releases/<旧sha> /var/www/nanmu-blog/current.tmp && mv -T /var/www/nanmu-blog/current.tmp /var/www/nanmu-blog/current'

## 8. 故障
- 构建失败:看 /opt/git/nanmu-blog-deploy.log;线上仍是旧 release(current 未切换),修好后重新 push。
- 并发 push:flock 自动跳过后到者,等先到者完成再推或手动重跑 deploy.sh。
```

- [ ] **Step 5: docs/architecture.md(从 spec §3 摘要)**

```markdown
# nanmu-blog 架构

三件套:site(Astro 5 静态站,git 即 CMS)/ engine(M1,读 topic-digest SQLite 产日报)/ rag(M2,自用问答)。

数据流:
1. 写作流:人写 markdown → git push → post-receive 后台 flock 构建 → releases/<sha> + mv -T 原子 symlink → Caddy
2. AI 流(M1):engine 定时读 topic-digest → 评分精选 → 摘要 → digest markdown 入库 git → 同一构建链
3. RAG 流(M2):engine 建向量索引 → FastAPI /ask(basicauth)

铁律与详设:docs/superpowers/specs/2026-10-02-nanmu-blog-design.md
```

- [ ] **Step 6: 语法检查并提交**

Run: `bash -n deploy/post-receive && bash -n deploy/deploy.sh && git status --short`
Expected: 两个脚本语法 OK(bash -n 无输出即通过)。

```bash
git add deploy docs/ops docs/architecture.md
git commit -m "feat: 部署工件(post-receive/deploy.sh/Caddyfile)与运维 runbook"
```

---

### Task 9: 服务器开通与首次部署(含韧性实测)

**Files:**
- 无仓库内新文件(服务器操作 + 验证;runbook 即 docs/ops/deploy.md)

**Interfaces:**
- Consumes: Task 8 的全部工件与 runbook;Task 1-7 的可部署 main 分支
- Produces: 线上 `https://blog.nanmu.xyz`(Task 10 的验收基础);`server` git remote

- [ ] **Step 1: 按 runbook §0-§2 开通服务器**

逐字执行 `docs/ops/deploy.md` §0-§2:前置检查(node 版本)→ 目录/bare repo/npm-cache → 安装 hook 并 chmod +x。
Expected: `ssh nanmu@123.56.223.97 'ls -la /opt/git/nanmu-blog.git/hooks/post-receive /opt/git/nanmu-blog.git/hooks/deploy.sh'` 两个文件存在且带 x 权限。

- [ ] **Step 2: SSH 免密(runbook §3)**

按 runbook §3 配置公钥。验证:`ssh nanmu@123.56.223.97 true; echo $?`
Expected: `0`(免密成功;密码只在首次配置时交互输入,不落盘)。

若非 0,按序排查(**历史教训:topic-digest 当年 remote 直连失败未诊断,退化成手工 bundle 同步——这次把原因查清**):
1. `ssh -v nanmu@123.56.223.97 true 2>&1 | tail -20`——看 offered public key 是否被服务器拒收
2. 服务器端 `sudo tail -20 /var/log/secure`(或 `sudo journalctl -u sshd -n 20`)看拒绝原因(常见:`~/.ssh/authorized_keys` 权限非 600、`~/.ssh` 非 700、home 目录组可写)
3. 修复后重试;**30 分钟内仍不通 → 降级为 git bundle 同步**(topic-digest 模式:`git bundle create /tmp/nb.bundle main` → scp → 服务器 bare repo `git fetch /tmp/nb.bundle main:main` 再手动触发 hook),并把"免密未通+根因"写入 session 的 omissions

- [ ] **Step 3: DNS 与 Caddy(runbook §4-§5)**

提醒用户在域名控制台加 A 记录(这是用户手动操作,等确认)。然后执行 runbook §5 装 Caddy 块并 reload。
Expected: `nslookup blog.nanmu.xyz` 解析到 123.56.223.97;Caddy reload 无报错。

- [ ] **Step 4: 首次部署(runbook §6)**

```bash
git remote add server nanmu@123.56.223.97:/opt/git/nanmu-blog.git
git push server main
```
等待约 60-120 秒(npm ci 首次无缓存会慢),然后验证:
```bash
curl -sI https://blog.nanmu.xyz                          # HTTP/2 200
curl -s https://blog.nanmu.xyz/rss.xml | head -5         # <?xml ... <rss
curl -s https://blog.nanmu.xyz/digest/ | grep -o "尚未发布任何日报"
```
Expected: 三条全部命中。M0 站点上线。

- [ ] **Step 5: 韧性实测(Review Focus 5)**

推一个构建必失败的 commit(schema 违约):
```bash
printf -- "---\ntitle: 坏条目\ndate: '2026-10-02'\n---\n缺 generated 字段\n" > site/src/content/digest/bad.md
git add site/src/content/digest/bad.md && git commit -m "test: 故意构建失败(部署韧性验证,随后回滚)"
git push server main && sleep 90
```
验证线上未受影响:
```bash
curl -sI https://blog.nanmu.xyz        # 仍然 200(旧 release)
ssh nanmu@123.56.223.97 'tail -5 /opt/git/nanmu-blog-deploy.log'   # 有构建失败记录
```
清理:
```bash
git rm site/src/content/digest/bad.md
git commit -m "revert: 移除韧性验证的坏条目"
git push server main && sleep 60
curl -s https://blog.nanmu.xyz/digest/ | grep -o "尚未发布任何日报"   # 恢复正常
```
Expected: 坏 commit 线上仍 200;修复后正常。证明"构建失败不切换 symlink"。

- [ ] **Step 6: 提交验证记录**

把韧性实测结果(时间点、curl 输出摘要)记入 `docs/sessions/2026-10-02-m0-deploy.md`(格式按 spec §8.1:objective/state[verified]/disposition/next_action/omissions)。

```bash
git add docs/sessions/2026-10-02-m0-deploy.md
git commit -m "docs: M0 部署与会话交接记录(韧性实测通过)"
git push server main
```

---

### Task 10: 首篇真实文章走完整链路 + tag m0

**Files:**
- Modify: `site/src/content/posts/hello-nanmu-blog.md`(去掉 draft,成稿)

**Interfaces:**
- Consumes: Task 9 的线上站点与 server remote
- Produces: M0 验收完成(spec §9:M0 三条验收标准全部证据化);tag `m0`

- [ ] **Step 1: 成稿首篇文章**

编辑 `site/src/content/posts/hello-nanmu-blog.md`:正文扩写为真实内容(项目从三段历史中重启的故事,可引用 spec §1 的三项目结论表),frontmatter 改为:
```yaml
---
title: 你好,nanmu-blog
pubDate: 2026-10-02
tags: [随笔, 建站]
draft: false
---
```

- [ ] **Step 2: 本地验证并计时发布**

```bash
cd site && npm run verify && cd ..
git add site/src/content/posts/hello-nanmu-blog.md
git commit -m "feat: 首篇文章——你好,nanmu-blog"
date +%s   # 记下推送前时间戳
git push server main
```

- [ ] **Step 3: 验收(spec §9 M0 标准)**

循环检查直到出现(总耗时应 ≤180 秒):
```bash
until curl -s https://blog.nanmu.xyz/rss.xml | grep -q "你好,nanmu-blog"; do sleep 10; done; date +%s
```
三条验收:
1. push 后 3 分钟内线上可见(两个时间戳之差 ≤180s)
2. RSS 可订阅:`curl -s https://blog.nanmu.xyz/rss.xml | grep 你好` 命中
3. 明暗主题正常:浏览器 DevTools Rendering → Emulate CSS prefers-color-scheme 切换 dark/light,配色切换、无 JS(人工确认)

- [ ] **Step 3b: 回滚演练(runbook §7 实操一次)**

此刻 releases/ 里已有两个版本(首篇文章 + 上一版),把回滚路径真实走一遍:

```bash
ssh nanmu@123.56.223.97 'ls -1dt /var/www/nanmu-blog/releases/*'
# 取较旧的一个目录作为 <旧sha>,切换过去:
ssh nanmu@123.56.223.97 'ln -sfn /var/www/nanmu-blog/releases/<旧sha> /var/www/nanmu-blog/current.tmp && mv -T /var/www/nanmu-blog/current.tmp /var/www/nanmu-blog/current'
curl -s https://blog.nanmu.xyz/ | grep -c '你好'      # 0——旧版没有首篇文章
# 再切回最新版本(重跑上一条,sha 换回最新):
curl -s https://blog.nanmu.xyz/ | grep -c '你好'      # ≥1——恢复
```
Expected: 两次切换均秒级生效、线上始终 200。回滚不是纸上流程,是实测可用的。

- [ ] **Step 4: 打 tag 并收尾**

```bash
git tag m0 && git push server m0
```
写 `docs/sessions/2026-10-02-m0-acceptance.md` 交接记录(验收证据、M1 启动提示:M1 plan 待写)。

```bash
git add docs/sessions/2026-10-02-m0-acceptance.md
git commit -m "docs: M0 验收通过,tag m0"
git push server main && git push server m0
```

---

## 自审记录(writing-plans Self-Review)

1. **Spec 覆盖**:spec §4(站点/collection/页面/RSS)= Task 2-7;§4.1 schema 契约 = Task 3;§7 部署(runbook 全节)= Task 8-9;§8 文档系统(AGENTS/README/architecture/ops/deploy + §8.1 sessions)= Task 1/8/9/10;§9 M0 验收三条 = Task 10 步骤 3。spec §5/§6 属 M1/M2,不在本计划(见 Global Constraints 最后一条)。
2. **占位符扫描**:无 TBD/TODO;所有代码步骤含完整代码;服务器步骤含完整命令。
3. **类型一致性**:collections 名(posts/digest)与字段在 Task 3 定义、Task 5/6/7 消费一致;`SITE_TITLE/SITE_DESC` 在 Task 4 定义、Task 6 消费;路由产物清单在 Task 5 产出、Task 7 冒烟清单一致;hook 路径 `/opt/git/nanmu-blog.git/hooks/` 在 Task 8/9 一致。
4. **Review Focus 五条**均已钉到任务步骤(见每条括号内任务号)。
