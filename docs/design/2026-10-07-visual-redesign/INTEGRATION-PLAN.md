# R6 正式接入方案(v2,2026-10-09 修订)

- 状态:执行中(批次 0–1 已完成并本地验收:批次 0 = 5aa996e,批次 1 = c743993..0562ae9 共 6 个提交;浏览器验收 34/34、verify 全绿、预算实测见 §5——**内页冷缓存实测超 §5 预算线,属预算条款修订事项,待用户裁决,未擅自放宽**;v1 为 2026-10-09 上午提案,v2 按复议指令定点修订:白名单补全、生产数据来源、预算测量、批次回退依赖)
- 对象:R6 全站统一原型(`prototypes/r6/`)→ 生产站 `site/`
- 关联:[R3-REVIEW.md](R3-REVIEW.md) · [ADR-0010](../../decisions/0010-adr0002-client-js-exceptions.md)(已接受,客户端行为以其白名单为准) · [prototypes/site/map.html](prototypes/site/map.html)

## 0. 范围与原则

接入对象:**token 与样式**(tokens6/base6/pages6)、**全站脚本**(site6.js + 首帧内联主题脚本)、**首页 3D**(boot6/scene6 + three r180 本地自托管 + poster,批次 2)、**字体分片**(serif + 改名 Plex,批次 0)。

**不进生产**:R1–R5 历史原型、lab 实验页、search-m2 概念稿、shots/rec 证据、poster-capture 调试页、页面内夹具与演示块(posts 多页夹具、digest 变体、post specimen 样张、map 总览)。历史材料永久留在设计目录。生产改造只动 `site/src` 模板层与 `site/public` 静态资产;**内容 collection、schema、校验、RSS 端点、构建流程一律不动**——不新增内容 schema,不引入数据库/后台/构建期模型调用。

## 1. 原型页 → Astro 路由映射(已实核 site/src/pages)

| 原型页(r6/) | 生产路由 | 备注 |
|---|---|---|
| index.html | `src/pages/index.astro` | 3D 批次 2;本批静态版式适配 |
| posts.html | `src/pages/posts/[...page].astro` | pageSize 10 保持;多页夹具不接 |
| post-hello.html | `src/pages/posts/[id].astro` | specimen 样张不接 |
| digest.html | `src/pages/digest/[...page].astro` | 列表夹具不接 |
| digest-2026-10-05.html | `src/pages/digest/[id].astro` | 变体夹具不接 |
| about.html | `src/pages/about.astro` | 「待填」槽=明示缺失语义,保留 |
| 404.html | `src/pages/404.astro` | 不泄露条目存在性 |
| —(订阅条) | `rss.xml.js` / `digest.xml.js` | 端点不动 |
| search-m2.html | 无路由 | M2 概念稿,不接、不进导航 |

## 2. 共用资产:原型三层 → 生产一层

- `src/styles/tokens.css` ← tokens6.css(双主题 token;`--mono` 改为改名后的 `NM Plex Mono`,见下)
- `src/styles/base.css` ← base6 与 pages6 的**并集去重**(基础排版/导航/页脚/印章/焦点/reduced-motion/VT 声明序 + 内页组件全套);夹具三件套(fixture-banner/details.fixture/page-tag)与首页专属段(场景宿主/页叠/HUD)不进;首页专属段批次 2 另立 `home.css`
- 布局:`layouts/Base.astro` 承载全站骨架(frame/header/footer/首帧内联脚本/site.js 引用/字体 link);`Header.astro` 改 R6 导航(`aria-current`:首页=精确匹配 `/`,其余前缀匹配)
- **字体进生产**:`site/public/fonts/`,由 `site/scripts/build-site-fonts.py` 从设计目录原型资产生成(可复现):**仅 Noto Serif SC 三字重 303 分片**(R6 不用 Noto Sans——tokens6 只有 serif/mono/kai,sans 三字重 303 分片不入库)+ 两份 OFL 许可证;**Plex 改名**:`fontTools` 改写 name 表为 `NM Plex Mono`(OFL RFN 义务,原文件名 `nm-plex-mono-400/500.woff2`);`public/fonts/fonts.css` 只含 serif 与改名 Plex 的 @font-face(约 305 条,未压缩约 300KB)
- **fonts.css 服务策略**:作为 public 静态文件由 `<link rel="stylesheet" href="/fonts/fonts.css">` 引入,**不走 Astro 打包**——606 分片的相对 url 交给浏览器按需取,构建零介入;代价是它本身是首个 CSS 请求,纳入 §5 预算
- 3D 资产(`public/3d/`:boot6/scene6/three×2/poster×2)**批次 2 入库**——本批首页不接 3D,提前入库即生产目录里的死资产,违反"不搬运未用资产"原则

## 3. 客户端行为白名单(= ADR-0010 清单;生产入口逐项)

全站仅两个脚本入口:`<head>` 内联首帧主题脚本(内容签名进 smoke 断言)+ `public/scripts/site.js`(`<script src defer>`)。smoke.mjs 由"拒绝一切 `<script>`"改为**白名单断言**:允许且仅允许这两个入口,其余任何脚本(含内联)构建失败。

| # | 行为 | 段 | 进入批次 | 无 JS / 失败时 |
|---|---|---|---|---|
| W1 | 首帧主题防闪(内联 ~3 行:读 localStorage 置 data-theme) | `<head>` 内联 | 1 | 不执行→系统色首帧(ADR-0002 原行为) |
| W2 | 主题三态切换 + `nm-theme` 事件 | site.js §1 | 1 | 不执行→跟随系统;按钮为静态 HTML,点击无效果但内容零损 |
| W3 | 移动菜单开合(Esc 收起) | site.js §2 | 1 | html.js 门控:导航平铺可点 |
| W4 | reveal 进场遮蔽 | site.js §3 | 1 | reveal-ready 门控:内容直接可见 |
| W5 | 页签目录↔3D 页叠双向联动 + 键盘漫游 | site.js §4 | 2 | 首页无 3D 时不渲染页签;HTML 面板直接可读 |
| W6 | 封面↔页头 `latest-cover` 挂名生命周期(转场配对) | site.js §4b | 2(页头侧常驻,批次 1 起存在但无配对源=无 morph) | 不挂名→普通 cross-fade |
| W7 | 朱砂装订线滚动延伸 | site.js §5 | 2 | 首页专属;不渲染即无 |
| W8 | 「这个站」三层展开 | site.js §6 | 2 | 手风琴全部展开、无隐藏内容 |
| W9 | 复制 RSS 链接盖印 | site.js §7 | 1 | 链接以 `<code>` 明文展示,可手复制 |
| W10 | 阅读进度条 + 目录书签 scrollspy | site.js §8 | 1 | 目录为构建期静态锚链接 |
| W11 | 代码块复制按钮 | site.js §9 | 1 | 按钮不生成;代码可手选 |
| W12 | 图片展开(原生 dialog) | site.js §10 | 1 | 按钮不生成;图片内联可读 |

生产适配(与原型的差异,均已在实现中落实):§4b 的回程来源正则从原型文件名 `post-*.html` 改为生产路由 `/posts/<id>/`;§10 从 `[data-zoom]` 选择器改为扫描 `.prose img`(生产 Markdown 图片没有手工挂属性的通道,说明文字取最近的 figcaption,无则省)。

**第三方表述(改正)**:零第三方**网络请求**与遥测;唯一第三方库 three r180 为本地自托管静态文件(非 npm 依赖,npm 运行时白名单仍只有 astro/@astrojs/rss)——不称"零第三方运行时"。

## 4. 生产路由下的数据与行为来源(不新增 schema)

- **转场识别**:根交叉淡化对**所有同源导航**生效(纯 CSS);`latest-cover` 配对仅发生在 首页封面卡(批次 2)↔ `/posts/<id>/` 页头 之间——页头常驻挂名自批次 1 存在,但无配对源时浏览器不生成 morph,只有普通 cross-fade,行为无害;§4b 回程补挂的来源判断用 `navigation.activation.from` 的 pathname 匹配 `/posts/`(缺省退 referrer,都读不到保守不挂)。
- **文章目录(toc)**:构建期生成——`render(post)` 返回的 `headings`(depth/slug/text)在 `[id].astro` 渲染为静态 `<nav class="toc">` 锚链接;**无标题时不渲染目录**(当前唯一真实文章为无标题三段正文,如实如此)。scrollspy 是 W10 增强。**不复制原型演示正文的 s1/s2/s3 章节结构**。
- **图片增强**:W12 扫描 `.prose img` 自动挂载;图片本体=Markdown 内容;alt 必有(作者书写),caption 取 figcaption。
- **3D 文本与链接(批次 2 策略,本批不实现)**:首页构建时把最新文章的标题/摘要/URL 与栏目链接以 `data-*` 属性或内嵌 JSON 写进场景宿主元素,scene6.js 只读 HTML 数据,JS 内不复制内容——保证 3D 与静态页面同源,内容改一处。
- **日报正文**:assemble.py 产物的 Markdown 经 Astro 默认管线渲染进 `.issue-body`;引用行为引擎输出的 `>` blockquote,CSS 以 `.issue-body > blockquote` 呈现图签注样式(原型类名 issue-note 不要求引擎配合)。
- **404/关于**:模板层;内容=现有真实文案,缺失以「待填」明示,不虚构。

## 5. 字体与资源预算(测量方法与验收口径)

- **计入预算的传输项**(冷缓存,禁 HTTP 缓存的全新 context):HTML + CSS(含 `fonts.css` 本体)+ JS + 实际命中的 woff2 分片。
- **测量方法**:`site/scripts/measure_budget.py`(Playwright 网络监听,入库可复跑):①冷缓存访问 `/posts/hello-nanmu-blog/`,记全部请求分型汇总;②同 context 顺序访问 `/` → `/about/`,记**跨页面新增分片**数与字节(验证 unicode-range 命中缓存);③`fonts.css` 记原始字节与 gzip 字节(部署层压缩口径)。Lighthouse 移动档为批次 3 复核项。
- **验收预算(v2 修订;超标=停在该项回表,不默放)**:
  - 内页:HTML+CSS+JS 冷缓存合计 ≤ 500KB(其中 JS gzip ≤ 8KB;fonts.css gzip 预期 ≤ 60KB——原始约 300KB,重复结构压缩率高,以实测为准);首访字体分片 ≤ 1.2MB,跨页新增分片以实测记录基线
  - 首页(批次 2):poster ≤ 450KB 且先于任何 3D 字节到达;3D(three+scene,gzip)≤ 220KB 且 idle 动态 import;LCP 以文档/poster 为准
- **poster/3D 真实加载策略(批次 2)**:poster 两张 PNG 以 `<img>` 首屏直载(它是 LCP 候选与 3D 失败的常驻回退,**不 lazy**;`fetchpriority="high"`,随主题切换显示对应张);boot6 探测 WebGL 后动态 `import('./scene6.js')`(module,defer 后执行),失败零请求零报错;场景就绪后 poster 淡出让位。reduced-motion:场景静态完成态。
- **预算检查在批次内的位置**:批次 1 验收=内页预算实测;批次 2 验收=poster/3D 预算实测;批次 3=全站复核与真机。
- **批次 1 实测记录(2026-10-09,measure_budget.py,本地无压缩服务)**:
  - 冷缓存 `/posts/hello-nanmu-blog/`:HTML 3954 B + CSS 321608 B + JS 7344 B + woff2 819288 B = **1125.2KB 原始字节**;按生产 Caddy gzip 口径折算(woff2 不再压缩,css/js 按实测 gzip 比)约 **920KB**——**超「≤500KB」预算线,已停在该项待裁决**(500KB 线与 CJK webfont 物理现实矛盾:仅 fonts.css gzip 92.7KB + 22 个命中分片 819KB 已超线;该线沿用无字体时代口径,修订建议=非字体资源(HTML+CSS+JS,生产 gzip)≤120KB + 字体单列沿用「首访 ≤1.2MB」)
  - fonts.css:原始 304490 B,gzip 92707 B——**超「预期 ≤60KB」**(预估 20% 压缩率,实测 30%)
  - 字体首访(四页累计新增分片):819288 + 42520 + 89784 + 74440 ≈ **1006KB ≤ 1.2MB** ✓(贴线,减字重为备选)
  - 跨页新增分片:/posts/ +1(42.5KB)、/digest/ +2(89.8KB)、/about/ +2(74.4KB)——unicode-range 按需命中,同片跨页复用成立
  - JS:7344 B 原始(gzip 约 3KB)≤ 8KB ✓
  - 附:批次 0 资产曾有一处缺陷(分片 url 前缀未剥 `fonts/`,全站 404 静默回退系统字体),由加严后的验收断言(仅计 2xx + `document.fonts.check` 实测)抓出,已在 0562ae9 修复——首次「34/34」中字体断言为假阳性的教训记录在案

## 6. 内容契约保留(逐项核对,模板层不碰数据流)

| 契约 | 生产现状 | 接入后 |
|---|---|---|
| 草稿隔离 | 每出口 `filter(!data.draft)`;drafts-example 永不发布 | 查询逻辑一行不动;只换渲染模板 |
| RSS | `rss.xml.js`/`digest.xml.js` 独立端点 | 端点与字段不动;订阅条 URL 指向同两端点 |
| 404 语义 | 极简页,不泄露撤回内容存在性 | 原型同语义(缺页意象无条目信息) |
| AI 标注/模型/费用 | 列表行与详情页头渲染 `ai_model`/`entry_count`/`cost_cny` | 图签(titleblock)数据源=同一 frontmatter;**列表与详情两处 `含未决预占` 文案保留原句**(smoke 断言此串) |
| cost_pending | `(含未决预占,为保守上界)` 两态 | 按 schema 布尔渲染同句 |
| 构建校验 | `assertPostsIds`/`assertDigestIds` 全出口 | 调用点保持;新模板不绕过 getCollection |
| 零模型调用 | 页面与构建不调 LLM(铁律 6) | 不变 |
| smoke 强制 | 拒绝一切 `<script>` 等 | 脚本检查改 ADR-0010 白名单断言;其余检查(产物存在/草稿泄漏/夹具泄漏/cost_pending 标注)原样保留 |

## 7. 接入批次与回退依赖(v2 修订)

| 批 | 内容 | 验收 | 回退 |
|---|---|---|---|
| 0 资产入库 ✅ 5aa996e(+0562ae9 url 修复) | fonts(serif+改名 Plex+fonts.css,经 build-site-fonts.py)+ tokens.css/base.css(未被引用) | `npm run verify` 绿(页面仍旧版式);脚本重跑幂等 | revert 单提交,零影响 |
| 1 公共布局与内页 ✅ c743993..e91d7c5 | Base/Header/site.js(W1-W4,W9-W12)/smoke 白名单/posts+post/digest 列表+详情/about/404/index 静态适配 | verify + `verify_browser.py`(昼/夜/手机 390/无 JS/键盘/直接访问与返回/reduced)+ 夹具构建浏览器抽验 + 预算实测(34/34;预算偏差见 §5,待裁决) | 见下方回退依赖 |
| 2 首页 3D | home.css + public/3d 入库 + boot/scene + W5-W8 + 封面卡 | 同矩阵 + WebGL 降级 + r6 回归移植 | 3D 段独立 revert,静态首页保留 |
| 3 测量收尾 | Lighthouse 复核、真机补测、预算回填 | 实测值回表 | 文档修正 |

**回退依赖(提交序)**:批次 1 内按 C2 布局(Base/Header/site.js/smoke,global.css 暂与新样式并存兜住未迁移页)→ C3 posts 两页 → C4 digest 两页 → C5 about+404+index 适配并移除 global.css。每提交点 `npm run verify` 绿、站点完整可用;**revert C2 必须先 revert C3–C5**(页面模板依赖新布局类);C3/C4/C5 可单页 revert。验收脚本(verify_browser.py/measure_budget.py)独立提交于 C1,先于实现入库(RED 证据在 session 记录)。

## 8. 已知风险与待裁决

- VT 跨页在旧浏览器退化为普通导航(无破坏);Safari/Firefox 未测(Chromium-only 验收,已标)。
- three 720KB 未压缩(备选:移动端仅 poster,批次 2 实测后裁决)。
- 字体首访 ~1MB(备选:减字重);fonts.css 原始 ~300KB 依赖部署层压缩(gzip 口径见 §5 实测)。
- **批次 1 实测暴露**:§5「内页冷缓存 ≤500KB」与「fonts.css gzip ≤60KB」两条均被实测打破(920KB / 92.7KB,见 §5 实测记录)——预算条款与 CJK webfont 方案内在矛盾,修订待用户裁决,本批不擅自放宽也不删减字重(那会改变 R6 版式)。
- 移动端 390 布局与真机触摸未实测(模拟器证据 only)。
