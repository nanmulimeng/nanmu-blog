# M0 博客上线 实施计划

> 执行方式:Native,按任务顺序推进,遵守 docs/development/workflow.md。环境有 executing-plans 可使用;缺少该skill不影响按本计划执行,不要求子代理。勾选只代表实际完成,本轮文档修订不勾选未来任务。

**Goal:** 搭建 nanmu-blog 的 M0——Astro 5 静态博客(手写文章 + 空置的 AI 日报栏目)+ git push 自动构建部署 + blog.nanmu.xyz 子域名上线。

**Architecture:** monorepo,`site/` 是 Astro 5 站点,`deploy/` 存服务器部署工件。写作流:本地写 markdown → `git push` main → 服务器 bare repo 的 post-receive hook 后台有界等待锁后构建(`releases/<sha>/dist`)→ `mv -T` 原子切换 `current` symlink → Caddy 静态服务。digest collection 与 schema 契约 M0 就位但内容空置(M1 由引擎填充)。

**Tech Stack:** Astro 5(glob loader Content Layer)、@astrojs/rss、Node 版本符合实际锁定 Astro 5 包的 engines(实施时核对)、Caddy 2(服务器已有)、bash git hooks。

**Spec:** `docs/superpowers/specs/2026-10-02-nanmu-blog-design.md`(本计划从 spec 立论,执行者需同时读 spec;关键依据 §2 铁律、§4/§4.1、§7、§8、§9-M0)

**执行状态(2026-10-04):** Task1-8原范围已实施,已有本地构建/冒烟证据;审查新增的Task8a(原始内容路径与缓存边界)尚未实施,须先完成再进入Task9-10服务器与上线验收。已勾选的历史步骤不代表覆盖后来发现的边界。开发顺序与M1/M2启动条件统一见spec §9.1;本轮文档修订不算实现验收。

## Global Constraints

- Astro 5,配置文件是 `site/src/content.config.ts`(不是旧版 `src/content/config.ts`)
- **零客户端 JS**:明暗主题只用 CSS `prefers-color-scheme`,不引入任何 JS 框架/主题切换脚本(spec 铁律 6)
- 页面 UI 中文;站名 `nanmu blog`(常量放 `site/src/consts.ts`)
- 站点 URL `https://blog.nanmu.xyz`(astro.config `site`,RSS 依赖它生成绝对链接)
- posts schema:`title: 非空string`、`pubDate: coerce.date`、`tags: string[] default []`、`draft: boolean default false`
- digest schema:`date: 有效YYYY-MM-DD`、`generated: literal true`、`ai_model: 非空string`、`entry_count: 非负整数`、`cost_cny: 非负有限数值`
- **digest 栏目从 M0 起就带 AI 生成标注**(spec 铁律 7):digest 列表页显式说明本栏目内容由 AI 生成
- **服务器凭据不落盘**:123.56.223.97 的密码只允许出现在交互式命令行输入,禁止写入任何文件/脚本/配置(历史约定)
- 生产main保持可部署:Task 2-6提交前build绿,Task 7起verify绿;纯文档按文档门禁。故障注入只在独立验收仓库/目录
- 保留最近 5 个 release 目录,更旧的删除;回滚 = 切 symlink
- 本计划完成后 M1/M2 各自另写 plan,不在本计划内实现任何 AI 功能

## 命令执行约定

除明确写“服务器”或部署脚本工件外,本计划命令均在本机Git Bash的仓库根执行。开发/安装需要切换目录时使用子shell,结束后仍在仓库根。Run中的npm统一用--prefix site;dist检查显式写site/dist。预期FAIL的负例单独执行并记录非零退出,还原后必须重新通过验证。

提交块先检查已有暂存,不得混入其他工作;git add仅含列出的本任务文件。验证结果必须对应拟提交版本,不能借未提交的依赖修改让本地构建变绿。阶段适用验证失败时停止,不继续commit/push;每块都不能以最后一条命令成功掩盖前面的失败。

## Review Focus

spec 未显式测试、但最容易咬人的五类输入/故障,及钉住它们的任务:

1. **非法 digest frontmatter 必须让构建失败**(schema 即契约,spec §4.1)——Task 3 步骤验证"缺 generated 字段时 build FAIL"。
2. **digest collection 为空时 `/digest/` 页面与 `/digest.xml` 必须优雅空态,不能 500**(M0 上线时 digest 就是空的)——Task 5/6 的空态代码与验证;Task 7 冒烟断言两文件存在。
3. **`draft: true` 的文章必须从列表、详情页、RSS 全部排除**——Task 5 getStaticPaths/getCollection 过滤;Task 7 冒烟断言 `drafts-example` 不出现在 rss.xml。
4. **RSS 标题特殊字符(`&`、`<`)必须正确转义**——Task 6 用临时 fixture 验证输出含 `&amp;`。
5. **部署韧性:推非 main 分支不触发部署;构建失败的 commit 不切换 symlink(线上保持旧版);并发push后台有界等待,最后成功发布最新main;超时有日志和重跑路径**——Task 8 脚本逻辑;Task 9独立验收目标实测(坏commit不切换已有release),不推坏生产main。

---

### Task 1: 仓库骨架与文档基线

已完成,证据提交`c0e8a84`。当前根文档已扩充,以现文件为准,不保留会覆盖新内容的旧模板。

- [x] Step1:建立.gitignore与.gitattributes。
- [x] Step2:建立AGENTS.md。
- [x] Step3:建立README.md与CLAUDE.md。
- [x] Step4:核对文件并提交。

---

### Task 2: Astro 5 脚手架

**Files:**
- Create: `site/package.json`、`site/package-lock.json`、`site/astro.config.mjs`、`site/src/pages/index.astro`、`site/tsconfig.json`

**Interfaces:**
- Consumes: Task 1 的 .gitignore(排除 node_modules/dist/.astro)
- Produces: `site/` 可构建的 Astro 5 项目;`npm run build` 产出 `site/dist/`(Task 7 依赖);astro.config 的 `site` URL(Task 6 RSS 依赖)

- [x] **Step 1: 创建明确主版本的最小项目**

不要用create-astro@latest推断会得到Astro 5。先核对开发机Node与拟安装Astro 5包的engines;服务器在Task 9单独核对。Astro 5不同小版本要求可能不同。

```bash
(
  set -euo pipefail
  mkdir -p site/src/pages
  cd site
  npm init -y
  npm pkg set type=module scripts.dev="astro dev" scripts.build="astro build" scripts.preview="astro preview"
  npm install --save-exact astro@5 @astrojs/rss@4
  node -p "JSON.stringify({astro:require('./node_modules/astro/package.json').version,engines:require('./node_modules/astro/package.json').engines,rss:require('./node_modules/@astrojs/rss/package.json').version})"
)
```

记录精确版本与Node版本到session,提交package-lock.json。发现engines不符先选择兼容运行时,不忽略警告继续;不擅自升级同机公共Node。

`site/tsconfig.json`:
```json
{"extends":"astro/tsconfigs/strict"}
```

`site/src/pages/index.astro`:
```astro
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8" /><title>nanmu blog</title></head><body><h1>nanmu blog</h1></body></html>
```

Expected:package.json显式锁定5.x与RSS4.x,无engines冲突。依据:[Astro5官方迁移文档](https://docs.astro.build/en/guides/upgrade-to/v5/),版本最终以本次安装结果为准。

- [x] **Step 2: 配置 site URL**

`site/astro.config.mjs` 全文替换为:
```js
import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://blog.nanmu.xyz',
});
```

- [x] **Step 3: 验证构建**

Run: `npm --prefix site run build`
Expected: 结束输出 "complete";`site/dist/index.html` 存在。

- [x] **Step 4: 提交**

```bash
(
  set -euo pipefail
  git diff --cached --quiet || { echo "已有暂存内容,先核对归属"; exit 1; }
  git add site
  git commit -m "feat: Astro 5 最小脚手架(site URL 指向 blog.nanmu.xyz)"
)
nb_step_status=$?
[ "$nb_step_status" -eq 0 ] || exit "$nb_step_status"
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

- [x] **Step 1: 写 content.config.ts**

```ts
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
```

- [x] **Step 2: 建目录与首篇内容**

`mkdir -p site/src/content/digest`并创建空`.gitkeep`(glob只读md);Git不跟踪空目录,M1后填充内容。M0的posts文件暂约束为单层小写短横线文件名,避开纯数字ID与分页路由冲突。

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

- [x] **Step 3: 契约验证——非法 digest frontmatter 必须让构建失败**

临时创建 `site/src/content/digest/2026-10-01.md`:
```markdown
---
date: '2026-10-01'
ai_model: example-model-id
entry_count: 0
cost_cny: 0
---

缺 generated 字段,构建必须失败。
```

Run: `npm --prefix site run build`
Expected: **FAIL**,报错指向 digest schema(generated 字段缺失/literal 不匹配)。这是 spec §4.1"schema 即契约"的验证。

删除该临时文件,按quality-gates的“内容变更与缓存验证”还原缓存与内容状态,再跑 `npm --prefix site run build`。Task8a将这一已知边界纳入正式入口和回归;不能仅因源文件已删除就假定产物没有残留。
Expected:PASS。补临时负例:空标题、generated=false、非法日历日期、负成本、非整数条数均失败;有效字段恢复后成功。fixture不提交。

- [x] **Step 4: 提交**

```bash
(
  set -euo pipefail
  git diff --cached --quiet || { echo "已有暂存内容,先核对归属"; exit 1; }
  git add site/src/content.config.ts site/src/content
  git commit -m "feat: posts/digest 双 collection,schema 即契约(含 draft fixture)"
)
nb_step_status=$?
[ "$nb_step_status" -eq 0 ] || exit "$nb_step_status"
```

---

### Task 4: 基础布局与零 JS 明暗主题

**Files:**
- Create: `site/src/consts.ts`、`site/src/styles/global.css`、`site/src/layouts/Base.astro`、`site/src/components/Header.astro`

**Interfaces:**
- Consumes: Task 2 的项目
- Produces: `Base.astro`(props:`title: string`、`description?: string`)——Task 5 所有页面用它包壳;`consts.ts` 导出 `SITE_TITLE = 'nanmu blog'`、`SITE_DESC = '个人文章与 AI 日报'`(Task 6 RSS 消费);`global.css` 的 CSS 变量体系(`--bg/--fg/--muted/--link/--border/--card`)

- [x] **Step 1: consts.ts**

```ts
export const SITE_TITLE = 'nanmu blog';
export const SITE_DESC = '个人文章与 AI 日报';
```

- [x] **Step 2: global.css(零 JS 明暗主题)**

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

- [x] **Step 3: Header.astro**

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

- [x] **Step 4: Base.astro**

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

- [x] **Step 5: 验证并提交**

Run: `npm --prefix site run build`
Expected:现有路由构建PASS;尚未引用的布局/组件不据此宣称已验证。Task5引用后才验收实际渲染与样式。Astro build不做TypeScript类型检查,strict tsconfig也不是类型检查命令;本阶段门禁仍为构建+产物验证,如引入独立astro check需记录开发依赖和适用范围。依据:[官方类型检查说明](https://docs.astro.build/en/guides/typescript/#type-checking)。

```bash
(
  set -euo pipefail
  git diff --cached --quiet || { echo "已有暂存内容,先核对归属"; exit 1; }
  git add site/src/consts.ts site/src/styles site/src/layouts site/src/components
  git commit -m "feat: Base 布局与零 JS 明暗主题(prefers-color-scheme)"
)
nb_step_status=$?
[ "$nb_step_status" -eq 0 ] || exit "$nb_step_status"
```

---

### Task 5: 页面与路由(含空态与 draft 排除)

**Files:**
- Modify: `site/src/pages/index.astro`(替换模板首页)
- Create: `site/src/lib/content.ts`(共享内容路径校验,不在组件内抓取数据)
- Create: `site/src/pages/about.astro`、`site/src/pages/404.astro`、`site/src/pages/posts/[...page].astro`、`site/src/pages/posts/[id].astro`、`site/src/pages/digest/[...page].astro`、`site/src/pages/digest/[id].astro`

**Interfaces:**
- Consumes: Task 3 的 collections(`getCollection('posts'|'digest')`,posts 字段 `title/pubDate/tags/draft`,digest 字段 `date/generated/ai_model/entry_count/cost_cny`);Task 4 的 `Base.astro`、global.css 变量
- Produces: 路由 `/`、`/about/`、`/posts/`、`/posts/{id}/`、`/digest/`、`/digest/{id}/`、`/404`(Task 7 冒烟清单依赖);条目排序契约:posts 按 pubDate 降序,digest 按 date 降序

- [x] **Step 0: 共享内容路径校验**

建立`src/lib/content.ts`的内容校验函数,接收页面/RSS读取的完整collection(含草稿),不自行调用getCollection。拒绝嵌套或非小写英文数字短横线的posts id、纯数字posts id,并核对digest id与date一致。所有内容出口在过滤/分页前调用,错误带entry id并使构建非零;后续页面片段展示渲染主体,实施时必须接入此校验。Task6两个RSS同样接入。Task5 Step7负例验证此入口,不依赖Zod字段schema获取文件名。

2026-10-04补验说明:上述已实现的是最终entry.id检查,无法证明原始文件名合规;frontmatter slug与框架清洗能绕过。原始路径、禁slug、入store前冲突检查及缓存失效统一由Task8a补齐,不得把本步骤历史勾选当成这些新用例通过。

- [x] **Step 1: 首页 index.astro**

```astro
---
import { getCollection } from 'astro:content';
import Base from '../layouts/Base.astro';

const posts = (await getCollection('posts', ({ data }) => !data.draft))
  .sort((a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf() || a.id.localeCompare(b.id))
  .slice(0, 5);
const digests = (await getCollection('digest'))
  .sort((a, b) => (a.data.date === b.data.date ? a.id.localeCompare(b.id) : a.data.date < b.data.date ? 1 : -1));
---
<Base>
  <h1>最新文章</h1>
  {posts.length === 0 && <p class="muted">尚未发布文章。</p>}
  {posts.map((p) => (
    <div class="card">
      <a href={`/posts/${p.id}/`}><strong>{p.data.title}</strong></a>
      <div class="muted">{p.data.pubDate.toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' })} · {p.data.tags.join(' / ')}</div>
    </div>
  ))}
  <h2 style="margin-top:2.5rem">AI 日报</h2>
  {digests.length === 0 ? (
    <p class="muted">日报尚未发布。本栏目由AI生成与筛选,每期标注生成模型与成本。</p>
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

- [x] **Step 2: 文章列表(分页)posts/[...page].astro**

```astro
---
import { getCollection } from 'astro:content';
import Base from '../../layouts/Base.astro';

export async function getStaticPaths({ paginate }) {
  const posts = (await getCollection('posts', ({ data }) => !data.draft))
    .sort((a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf() || a.id.localeCompare(b.id));
  return paginate(posts, { pageSize: 10 });
}
const { page } = Astro.props;
---
<Base title="文章">
  <h1>文章</h1>
  {page.data.length === 0 && <p class="muted">尚未发布文章。</p>}
  {page.data.map((p) => (
    <div class="card">
      <a href={`/posts/${p.id}/`}><strong>{p.data.title}</strong></a>
      <div class="muted">{p.data.pubDate.toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' })} · {p.data.tags.join(' / ')}</div>
    </div>
  ))}
  {page.url.prev && <a href={page.url.prev}>← 上一页</a>}
  {page.url.next && <a href={page.url.next}>下一页 →</a>}
</Base>
```

- [x] **Step 3: 文章详情 posts/[id].astro**

```astro
---
import { getCollection, render } from 'astro:content';
import Base from '../../layouts/Base.astro';

export async function getStaticPaths() {
  const posts = await getCollection('posts', ({ data }) => !data.draft);
  return posts.map((p) => ({ params: { id: p.id }, props: { post: p } }));
}
const { post } = Astro.props;
const { Content } = await render(post);
---
<Base title={post.data.title} description={post.data.title}>
  <h1>{post.data.title}</h1>
  <p class="muted">{post.data.pubDate.toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' })} · {post.data.tags.join(' / ')}</p>
  <hr />
  <article><Content /></article>
</Base>
```

- [x] **Step 4: 日报列表(分页 + 空态 + AI 标注)digest/[...page].astro**

```astro
---
import { getCollection } from 'astro:content';
import Base from '../../layouts/Base.astro';

export async function getStaticPaths({ paginate }) {
  const digests = (await getCollection('digest'))
    .sort((a, b) => (a.data.date === b.data.date ? a.id.localeCompare(b.id) : a.data.date < b.data.date ? 1 : -1));
  return paginate(digests, { pageSize: 10 });
}
const { page } = Astro.props;
---
<Base title="AI 日报">
  <h1>AI 日报</h1>
  <p class="muted">本栏目由 AI 引擎自动生成:读取聚合数据、评分精选、撰写摘要。每期标注生成模型与成本。</p>
  {page.data.length === 0 ? (
    <p class="muted">尚未发布任何日报。</p>
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

- [x] **Step 5: 日报详情 digest/[id].astro**

```astro
---
import { getCollection, render } from 'astro:content';
import Base from '../../layouts/Base.astro';

export async function getStaticPaths() {
  const digests = await getCollection('digest');
  return digests.map((d) => ({ params: { id: d.id }, props: { digest: d } }));
}
const { digest } = Astro.props;
const { Content } = await render(digest);
---
<Base title={`${digest.data.date} 日报`} description={`AI 生成 · ${digest.data.entry_count} 条`}>
  <h1>{digest.data.date} 日报</h1>
  <p class="muted">AI 生成({digest.data.ai_model})· {digest.data.entry_count} 条 · 成本 ¥{digest.data.cost_cny}</p>
  <hr />
  <article><Content /></article>
</Base>
```

- [x] **Step 6: about.astro 与 404.astro**

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

- [x] **Step 7: 验证 draft 排除与空态**

Run: `npm --prefix site run build`
Expected: PASS。检查产物:
```bash
ls site/dist/posts/         # 只有列表index.html;两篇都还是draft,无详情目录
grep -c drafts-example site/dist/index.html site/dist/posts/index.html || true   # 都是 0
grep -o "尚未发布任何日报" site/dist/digest/index.html   # 空态文案存在
```
Expected: `dist/posts/` 下无hello-nanmu-blog和drafts-example详情;两个grep计数为0;posts/digest空态文案命中。Astro5.13.2官方paginate实现为空数组保留一页,实际安装版本仍以此构建验证为准。

追加有限边界验收:用临时公开fixture超过10篇验证第二页与前后翻页链接,同日期按id稳定排序;验证纯数字/嵌套posts与日报文件名不匹配date会被内容检查明确拒绝。文件名约束不是当前Zod字段schema自动完成的:Task5实现一个共享内容校验入口,页面/构建消费它,禁止让重复路由靠框架优先级静默覆盖。验证后移除临时fixture并还原空态,不新增长期测试框架。

- [x] **Step 8: 提交**

```bash
(
  set -euo pipefail
  git diff --cached --quiet || { echo "已有暂存内容,先核对归属"; exit 1; }
  git add site/src/pages site/src/lib/content.ts
  git commit -m "feat: 全部页面路由——首页/文章/日报/关于/404,空态与 draft 排除"
)
nb_step_status=$?
[ "$nb_step_status" -eq 0 ] || exit "$nb_step_status"
```

---

### Task 6: RSS 双出口

**Files:**
- Create: `site/src/pages/rss.xml.js`、`site/src/pages/digest.xml.js`

**Interfaces:**
- Consumes: Task 3 collections、Task 4 `consts.ts`(`SITE_TITLE/SITE_DESC`)、Task 2 astro.config `site`(经 `context.site`)
- Produces: `/rss.xml`(文章)与 `/digest.xml`(日报)endpoint——Task 7 冒烟依赖;路由契约固定,M1 日报发布后自动进 digest.xml,无需改动

- [x] **Step 1: rss.xml.js**

```js
import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import { SITE_TITLE, SITE_DESC } from '../consts';

export async function GET(context) {
  const posts = (await getCollection('posts', ({ data }) => !data.draft))
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
```

- [x] **Step 2: digest.xml.js(空 feed 也合法)**

```js
import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import { SITE_TITLE } from '../consts';

export async function GET(context) {
  const digests = (await getCollection('digest'))
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
```

- [x] **Step 3: 验证——空 feed 合法、draft 排除、转义**

Run: `npm --prefix site run build`
```bash
head -3 site/dist/rss.xml site/dist/digest.xml
grep -c drafts-example site/dist/rss.xml || true   # 0
```
Expected:两个文件含rss/channel且无草稿。不能只看字符串就宣称XML合法;用标准解析器验证(开发机Python已有):
```bash
python -c "import xml.etree.ElementTree as E; [E.parse(p) for p in ['site/dist/rss.xml','site/dist/digest.xml']]; print('RSS XML parse OK')"
```
两个空feed均能解析是M0验收项。

转义验证(Review Focus 4):临时把 `hello-nanmu-blog.md` 的 title 改为 `你好,nanmu-blog & <重启>`,先把 frontmatter 的 `draft: true` 改为 `false`,build 后:
```bash
grep -o "nanmu-blog &amp; &lt;重启&gt;" site/dist/rss.xml
```
Expected: 命中(`&` 与 `<>` 均已转义)。验证后**还原**:title 改回 `你好,nanmu-blog`,`draft` 改回 `true`,重新 build 确认 PASS。

- [x] **Step 4: 提交**

```bash
(
  set -euo pipefail
  git diff --cached --quiet || { echo "已有暂存内容,先核对归属"; exit 1; }
  git add site/src/pages/rss.xml.js site/src/pages/digest.xml.js
  git commit -m "feat: /rss.xml 与 /digest.xml 双 RSS 出口,空 feed 合法"
)
nb_step_status=$?
[ "$nb_step_status" -eq 0 ] || exit "$nb_step_status"
```

---

### Task 7: 冒烟脚本与一键验证

**Files:**
- Create: `site/scripts/smoke.mjs`
- Modify: `site/package.json`(scripts 加 `verify`)

**Interfaces:**
- Consumes: Task 2 build、Task 5 路由产物、Task 6 RSS 文件(路径契约:`dist/index.html`、`dist/posts/index.html`、`dist/digest/index.html`、`dist/about/index.html`、`dist/rss.xml`、`dist/digest.xml`、`dist/404.html`)
- Produces: `npm run verify`(build + 冒烟)——Global Constraints 规定的 commit 前门槛;M1 引擎的 CI/回滚流程复用同一脚本

- [x] **Step 1: smoke.mjs**

```js
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
```

- [x] **Step 2: package.json 加 verify script**

在 `site/package.json` 的 `scripts` 中加入:
```json
"verify": "astro build && node scripts/smoke.mjs"
```

- [x] **Step 3: 验证**

Run: `npm --prefix site run verify`
Expected: build complete 后输出 `smoke ok: ...`。

负例验证:先build,把site/dist/digest.xml移到临时备份,单独运行 `node site/scripts/smoke.mjs`,应SMOKE FAIL且非零;恢复后verify通过。再用Task3非法frontmatter fixture运行verify,应在build阶段非零(不要求一定打印SMOKE FAIL)。所有负例只在临时文件/验收目录,提交前还原并verify。

- [x] **Step 4: 提交**

```bash
(
  set -euo pipefail
  git diff --cached --quiet || { echo "已有暂存内容,先核对归属"; exit 1; }
  git add site/scripts/smoke.mjs site/package.json
  git commit -m "feat: npm run verify——build+冒烟,commit 前门槛"
)
nb_step_status=$?
[ "$nb_step_status" -eq 0 ] || exit "$nb_step_status"
```

---

### Task 8: 部署工件与运维文档

**Files:**
- Create: `deploy/post-receive`、`deploy/deploy.sh`、`deploy/Caddyfile.snippet`
- Modify: `docs/ops/deploy.md`(准备版已建立;Task8核对脚本与现场前置条件)
- Modify: `docs/architecture.md`(已存在,仅同步部署事实,不得用摘要覆盖全文)

**Interfaces:**
- Consumes: Task 7 的 `npm run verify`;仓库结构(site/ 子目录)
- Produces: 服务器工件的标准来源(Task 9 把它们安装到 `/opt/git/nanmu-blog.git/hooks/` 与 Caddy);runbook 是唯一部署真相源,回滚/故障处理写在里面

- [x] **Step 1: deploy/post-receive**

```bash
#!/bin/bash
# 只认main;后台任务等待锁,超过期限留日志;所有stdio脱离push连接
set -eu
NULL_SHA=0000000000000000000000000000000000000000
found=0
while read -r oldrev newrev refname; do
  if [ "$refname" = refs/heads/main ] && [ "$newrev" != "$NULL_SHA" ]; then found=1; fi
done
[ "$found" = 1 ] || exit 0
export NB_REPO="${NB_REPO:-/opt/git/nanmu-blog.git}"
export NB_ROOT="${NB_ROOT:-/var/www/nanmu-blog}"
LOG="${NB_LOG:-/var/www/nanmu-blog/deploy.log}"
nohup bash -c '
  if flock -E 75 -w 900 "$NB_ROOT/build.lock" timeout -k 30s 900s "$NB_REPO/hooks/deploy.sh"; then
    exit 0
  else
    code=$?
    printf "%s build failed or lock timed out, exit=%s; manual retry required\n" "$(date -Is)" "$code"
    exit "$code"
  fi
' >> "$LOG" 2>&1 </dev/null &
printf 'build scheduled; inspect %s and /release.txt for result\n' "$LOG"
```

- [x] **Step 2: deploy/deploy.sh(构建失败不切换 symlink = 线上保持旧版)**

```bash
#!/bin/bash
# 只能由已持有NB_ROOT/build.lock的调用者运行;手动重跑也要flock
set -euo pipefail
umask 022
if [ -f "$HOME/.nvm/nvm.sh" ]; then . "$HOME/.nvm/nvm.sh"; fi
REPO="${NB_REPO:-/opt/git/nanmu-blog.git}"
ROOT="${NB_ROOT:-/var/www/nanmu-blog}"
RELEASES="$ROOT/releases"
unset GIT_WORK_TREE GIT_INDEX_FILE
export GIT_DIR="$REPO"
SHA=$(git rev-parse refs/heads/main)
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || exit 1
DEST="$RELEASES/$SHA"
WORK=$(mktemp -d)
STAGE=""
cleanup() {
  rm -rf -- "$WORK"
  if [ -n "$STAGE" ]; then rm -rf -- "$STAGE"; fi
}
trap cleanup EXIT
if [ -f "$DEST/.complete" ] && [ "$(cat "$DEST/.complete")" = "$SHA" ]; then
  [ "$(cat "$DEST/dist/release.txt")" = "$SHA" ] || exit 1
else
  if [ -e "$DEST" ]; then
    printf 'incomplete release requires inspection: %s\n' "$DEST" >&2
    exit 1
  fi
  git archive "$SHA" | tar -x -C "$WORK"
  cd "$WORK/site"
  npm ci --prefer-offline --cache /opt/git/nanmu-blog-npm-cache
  npm run verify
  printf '%s\n' "$SHA" > dist/release.txt
  STAGE=$(mktemp -d "$RELEASES/.build.XXXXXX")
  cp -a dist "$STAGE/dist"
  chmod 755 "$STAGE"
  chmod -R a+rX "$STAGE/dist"
  printf '%s\n' "$SHA" > "$STAGE/.complete"
  mv -T "$STAGE" "$DEST"
  STAGE=""
fi
ln -sfn "$DEST" "$ROOT/current.tmp"
mv -T "$ROOT/current.tmp" "$ROOT/current"
printf '%s deployed %s\n' "$(date -Is)" "$SHA"

# 只清理该根下的完整SHA版本,当前版永不删除;共保留当前+最近4个旧版
kept=1
mapfile -t candidates < <(find "$RELEASES" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-)
for candidate in "${candidates[@]}"; do
  name="${candidate##*/}"
  [[ "$name" =~ ^[0-9a-f]{40}$ ]] || continue
  [ "$candidate" != "$DEST" ] || continue
  [ -f "$candidate/.complete" ] || continue
  if [ "$kept" -lt 5 ]; then kept=$((kept + 1)); continue; fi
  rm -rf -- "$candidate" || printf 'warning: old release cleanup failed: %s\n' "$candidate" >&2
done
```

- [x] **Step 3: deploy/Caddyfile.snippet**

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

- [x] **Step4: 核对部署手册**

按 [ops/deploy.md](../../ops/deploy.md) 检查脚本路径、专用npm缓存、日志、权限、SSH/DNS、候选Caddy配置、发布确认和回滚。它是唯一操作手册;发现与工件不符先同步,不在本计划复制第二份。

- [x] **Step5: 同步架构与状态**

同步已有architecture.md、环境文档和session,保留证据等级。此时只能称工件已落盘,不能将部署手册改成已验收。

- [x] **Step 6: 语法检查并提交**

Run: `bash -n deploy/post-receive && bash -n deploy/deploy.sh && git status --short`
Expected: 两个脚本语法OK(bash -n无输出即通过);这不代表Linux运行/权限/并发已验收,Task9必须实测。

```bash
(
  set -euo pipefail
  git diff --cached --quiet || { echo "已有暂存内容,先核对归属"; exit 1; }
  git add deploy docs/ops docs/architecture.md
  git commit -m "feat: 部署工件(post-receive/deploy.sh/Caddyfile)与运维 runbook"
)
nb_step_status=$?
[ "$nb_step_status" -eq 0 ] || exit "$nb_step_status"
```

---

### Task 8a: 内容路径与缓存边界修复(上线前)

**状态:** 待实施。来自2026-10-04审查的两个可复现缺口,是M0原有内容契约的补全,不新增产品功能。

**Files/入口:** `site/src/content.config.ts`、`site/src/lib/content.ts`、`site/package.json`及必要的最小验证脚本;页面/RSS消费方按引用核对。选择loader层校验或构建前校验时,须覆盖dev与build,禁止只加一个手动脚本后仍允许正式入口绕过。实现后同步spec、quality-gates和writing中的待修复状态。

- [ ] **Step 1: 在独立临时副本复现并记录负例。** 包含嵌套posts加合法slug、错误digest文件名加日期slug、与文件名相同的slug、大写/空格/下划线等可被清洗的路径、纯数字posts、重复最终id。所有posts草稿同样受约束。记录当前错误被接受的例子,不把坏fixture放进生产main。
- [ ] **Step 2: 校验原始输入再入store。** 原始相对路径符合spec §4.1、所有内容禁slug、最终id不冲突;digest文件名与date一致。不能仅对被Astro重写过的id检查,也不能等重复id覆盖后再查。错误指向具体源文件并使构建非零;合法单层文章、日期日报、现有两篇草稿保持可构建。
- [ ] **Step 3: 修复持久缓存失效。** 用唯一公开posts/digest各做“添加→构建→删除→同一副本再次构建”,选择最小可靠的loader失效或正式构建入口清理方案。若清理缓存,限定本站可再生目录并验证解析路径;不删除源文件/整个依赖树,不新增缓存服务。verify与实际部署调用的构建入口保持一致,dev中的删除也应及时反映。
- [ ] **Step 4: 验收真实产物。** 合法内容正常显示;所有非法路径/slug/collision负例在覆盖前失败。删除最后一篇、改名、draft撤回后,首页/分页/详情/RSS无旧项,空collection仍正常;测试不预先手工清缓存来掩盖缺陷。fixture清理后再用正式verify入口确认仓库恢复空态,不遗留公开测试内容。
- [ ] **Step 5: 更新文档与交接。** 记录实际命令、正反例结果及实现取舍,更新相关状态入口;适用文档检查与`npm --prefix site run verify`通过。仅在步骤1-4确有证据后勾选;提交按当前授权,未提交如实记录。

**完成边界:** 不改路由/文章字段语义,不升级Astro或引入测试框架来回避根因;如必须变更版本,先证明原因与回归范围。Task8a不替代服务器韧性与首篇文章验收。

---

### Task 9: 服务器开通与首次部署(含韧性实测)

**Files:**
- 无仓库内新文件(服务器操作 + 验证;runbook 即 docs/ops/deploy.md)

**Interfaces:**
- Consumes: Task8全部工件与runbook、Task8a实际通过的路径/缓存验收、Task1-7的可部署main分支
- Produces: 线上 `https://blog.nanmu.xyz`(Task 10 的验收基础);`server` git remote

- [ ] **Step 1: 按 runbook §0-§2 开通服务器**

核对现场后执行 `docs/ops/deploy.md` §0-§2:前置检查(node版本)→ 目录/bare repo/专用npm缓存 → 安装hook并chmod +x;现场与手册不符先修正文档。
Expected: `ssh nanmu@123.56.223.97 'ls -la /opt/git/nanmu-blog.git/hooks/post-receive /opt/git/nanmu-blog.git/hooks/deploy.sh'` 两个文件存在且带 x 权限。

- [ ] **Step 2: SSH 免密(runbook §3)**

按 runbook §3 配置公钥。验证:`ssh -o BatchMode=yes -o ConnectTimeout=10 nanmu@123.56.223.97 true; echo $?`
Expected: `0`(免密成功;密码只在首次配置时交互输入,不落盘)。

若非 0,按序排查(**历史教训:topic-digest 当年 remote 直连失败未诊断,退化成手工 bundle 同步——这次把原因查清**):
1. `ssh -v nanmu@123.56.223.97 true 2>&1 | tail -20`——看 offered public key 是否被服务器拒收
2. 服务器端 `sudo tail -20 /var/log/secure`(或 `sudo journalctl -u sshd -n 20`)看拒绝原因(常见:`~/.ssh/authorized_keys` 权限非 600、`~/.ssh` 非 700、home 目录组可写)
3. 修复后重试;**30 分钟内仍不通 → 降级为 git bundle 同步**(topic-digest 模式:`git bundle create "${TMPDIR:-/tmp}/nb.bundle" main` → scp → 服务器bare repo `git fetch /tmp/nb.bundle main:main` 再按runbook带锁运行deploy.sh(直接调用无stdin的hook不会触发部署)),并把"免密未通+根因"写入 session 的 omissions

- [ ] **Step 3: DNS 与 Caddy(runbook §4-§5)**

提醒用户在域名控制台加 A 记录(这是用户手动操作,等确认)。然后按runbook §5准备并validate候选Caddy配置;先在Step4生成可读current再加载博客站点块。
Expected:DNS核对正确,候选配置validate通过,原Caddy服务保持现状。

- [ ] **Step 4: 首次部署(runbook §6)**

按部署手册§3核对已有server remote,再按§6推送并观察构建;不要重复添加同名remote。
等待构建成功并核对Caddy用户可读(包含release根755权限),再按runbook §5加载候选配置。随后验证:
```bash
curl -sI https://blog.nanmu.xyz                          # HTTP/2 200
curl -s https://blog.nanmu.xyz/rss.xml | head -5         # <?xml ... <rss
curl -s https://blog.nanmu.xyz/digest/ | grep -o "尚未发布任何日报"
```
Expected: 三条全部命中且release.txt与期望SHA一致。仅代表首次部署通过,M0仍需Task10完整验收。

- [ ] **Step 5: 独立验收目标的韧性实测(Review Focus 5)**

不得提交坏生产main。先核对并建立独立目标:`/opt/git/nanmu-blog-acceptance.git`、`/var/www/nanmu-blog-acceptance`、独立日志。复制同一版本hook/deploy脚本;在验收hook的set -eu后设置NB_REPO/NB_ROOT/NB_LOG指向上述目标,绝不沿用生产默认值。本地使用临时clone和专属remote,不修改主工作区历史。记录目标清单后再执行。

在验收目标按顺序验证并保存日志/退出码/readlink/release.txt:

1. 推好版本,确认current指向完整release,`.complete`及release.txt等于已接收SHA。
2. 推非main分支,确认无构建;删除临时分支不触发发布。
3. 在验收clone的main加入Task3非法digest并push;确认有构建错误,current及已发布内容保持好版本,坏SHA没有.complete。移除坏文件后提交,push应恢复。
4. 阻塞第一次构建或短暂持有验收锁,连续push两个不同提交;释放锁后最后线上标记必须包含第二个main提交,不能静默丢弃后到者。记录push返回时间证明hook没有等待整个构建。
5. 模拟构建中断/半成品;重试同一SHA不得把部分dist当成功缓存。验证超时可观测,再带锁手动重跑成功。

验收目录不配置公网Caddy入口,用文件标记/readlink确认原子发布。生产端同时抽查博客与skills入口基线;生产首篇发布/HTTP/回滚由Task10验证。验收结束保留证据,列出临时目录后按用户授权清理,不使用宽泛rm。

- [ ] **Step 6: 提交验证记录**

把独立目标韧性实测结果及生产冒烟(时间点、SHA、退出码、HTTP输出摘要)记入实际执行日期的session(格式按spec §8.1:objective/state[verified]/disposition/next_action/omissions)。先确定文件名,再使用模板填写证据,不要预写“通过”:

```bash
deploy_session="docs/sessions/$(date +%F)-m0-deploy.md"
```

填写完成、适用检查通过后提交:

```bash
(
  set -euo pipefail
  git diff --cached --quiet || { echo "已有暂存内容,先核对归属"; exit 1; }
  git add "$deploy_session"
  git commit -m "docs: M0 部署与会话交接记录(韧性实测通过)"
  git push server main
)
nb_step_status=$?
[ "$nb_step_status" -eq 0 ] || exit "$nb_step_status"
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
(
  set -euo pipefail
  git diff --cached --quiet || { echo "已有暂存内容,先核对归属"; exit 1; }
  npm --prefix site run verify
  git add site/src/content/posts/hello-nanmu-blog.md
  git commit -m "feat: 首篇文章——你好,nanmu-blog"
)
nb_step_status=$?
[ "$nb_step_status" -eq 0 ] || exit "$nb_step_status"
test "$(git branch --show-current)" = main || exit 1
start=$(date +%s)   # 同一shell中的验收轮询复用,包含push耗时
git push server main || exit 1
```

- [ ] **Step 3: 验收(spec §9 M0 标准)**

循环检查直到出现(总耗时应 ≤180 秒):
```bash
: "${start:?先记录push前时间}"
expected=$(git rev-parse refs/heads/main)
nb_step_status=$?
[ "$nb_step_status" -eq 0 ] || exit "$nb_step_status"
ok=0
while [ $(( $(date +%s) - start )) -lt 180 ]; do
  if [ "$(curl --fail --silent --max-time 10 https://blog.nanmu.xyz/release.txt)" = "$expected" ] && curl --fail --silent --max-time 10 https://blog.nanmu.xyz/rss.xml | grep -q "你好,nanmu-blog"; then
    ok=1; break
  fi
  sleep 5
done
echo "elapsed=$(( $(date +%s) - start ))s"
[ "$ok" = 1 ] && [ $(( $(date +%s) - start )) -le 180 ] || { echo 'publish timeout'; exit 1; }
```
三条验收(除RSS标题外,必须直接访问`/posts/hello-nanmu-blog/`,核对200与一段本次正文;随机不存在URL为真实404):
1. push 后 3 分钟内线上可见(两个时间戳之差 ≤180s)
2. 两条RSS用XML解析器验证,文章feed含本次标题/链接,并用实际阅读器或订阅客户端完成一次订阅;grep只作辅助
3. 明暗主题正常:浏览器 DevTools Rendering → Emulate CSS prefers-color-scheme 切换 dark/light,配色切换、无 JS(人工确认)

- [ ] **Step 3b: 回滚演练(runbook §7 实操一次)**

此刻releases里已有首篇文章版与上一版。按[部署手册](../../ops/deploy.md)§7选择完整旧SHA,暂停新push并取得同一build.lock,回滚后确认旧内容与旧release.txt,再切回新版本。

Expected:两次切换均秒级生效、首页始终200、release.txt命中各目标SHA;记录结果到session。运维回滚不删除任何原文/费用记录。

- [ ] **Step 4: 打 tag 并收尾**

```bash
git tag -a m0 -m 'M0 博客上线验收通过' && git push server m0
```
用实际执行日期写验收交接(验收证据、M1启动提示:M1 plan待写),同时更新README/AGENTS/文档索引状态并通过文档检查:

```bash
acceptance_session="docs/sessions/$(date +%F)-m0-acceptance.md"
```

填写完成后:

```bash
(
  set -euo pipefail
  git diff --cached --quiet || { echo "已有暂存内容,先核对归属"; exit 1; }
  git add "$acceptance_session" README.md AGENTS.md docs/README.md
  git commit -m "docs: M0 验收通过,tag m0"
  git push server main && git push server m0
)
nb_step_status=$?
[ "$nb_step_status" -eq 0 ] || exit "$nb_step_status"
```

---

## 自审记录(writing-plans Self-Review)

1. **Spec 覆盖**:spec §4(站点/collection/页面/RSS)= Task 2-7;§4.1 schema 契约 = Task 3;§7 部署(runbook 全节)= Task 8-9;§8 文档系统(AGENTS/README/architecture/ops/deploy + §8.1 sessions)= Task 1/8/9/10;§9 M0 验收三条 = Task 10 步骤 3。spec §5/§6 属 M1/M2,不在本计划(见 Global Constraints 最后一条)。
2. **占位符扫描**:无 TBD/TODO;代码步骤给实施基线;部署流程统一在ops/deploy.md,先决条件和现场差异必须核对。
3. **类型一致性**:collections 名(posts/digest)与字段在 Task 3 定义、Task 5/6/7 消费一致;`SITE_TITLE/SITE_DESC` 在 Task 4 定义、Task 6 消费;路由产物清单在 Task 5 产出、Task 7 冒烟清单一致;hook 路径 `/opt/git/nanmu-blog.git/hooks/` 在 Task 8/9 一致。
4. **Review Focus 五条**均已钉到任务步骤(见每条括号内任务号)。

## 文档审查修订

早期依据见[文档审查记录](../../reviews/2026-10-02-documentation-audit.md),当前缺口与推进策略见[技术契约交接](../../sessions/2026-10-04-technical-direction.md)。Task1-8工件已存在,以实际文件和对应实施证据为准;本计划保留示例帮助理解任务,不允许重新照抄覆盖后续修订。Task8a与Task9-10仍待实际执行,不因本轮文档检查通过而勾选。

2026-10-04补充:命令上下文与失败停止、暂存保护、分页/内容路径边界、详情与RSS订阅验收。工件仍待Task2-10实际实现,不把文档片段当现存应用。
