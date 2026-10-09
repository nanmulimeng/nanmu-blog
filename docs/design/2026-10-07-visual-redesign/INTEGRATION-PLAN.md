# R6 正式接入方案(v2,2026-10-09 修订)

- 状态:执行中(批次 0–1 已完成并本地验收:批次 0 = 5aa996e,批次 1 = c743993..0562ae9 共 6 个提交;2026-10-09 审计收口 = 2c52c34..1f25d9a——预算口径勘误、测量工具修正、fonts.css 交错优化,内页预算全部在线内;**批次 2 首页 3D 已完成并本地验收(2026-10-09)= 72a4c42 验收工具 + a498f05 静态首页 + ffffd6e 3D 接入**:浏览器验收 73/73、E1/E2 预算全过、手机三宽视检,两提交可独立回退;**批次 2 定点修正轮已完成(2026-10-09,审计后)= 手机交接区单格化+失败清理、就绪前主题切换不丢、日报/站点状态同源接线、排队反例入验收、文档口径校正与证据归档(shots/r6-b2-*)**,验收扩至 74/74、夹具三态、预算复测通过;**批次 3 进行中(2026-10-09 复核通过后启动)**:开头三项收尾已完成——①修正轮反例固化入库(verify_browser P 段:交接高度+失败清理,验收 76/76;scripts/verify_digest_states.py:三态 3/3)②本文件 poster 请求/呈现与昼/夜口径原条款校正 ③回退路径隔离检出实测(§7 2R 行);Lighthouse/Firefox/真机/Caddy 基线测量待做;v1 为 2026-10-09 上午提案,v2 按复议指令定点修订:白名单补全、生产数据来源、预算测量、批次回退依赖)
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
- **字体进生产**:`site/public/fonts/`,由 `site/scripts/build-site-fonts.py` 从设计目录原型资产生成(可复现):**仅 Noto Serif SC 三字重 303 分片**(R6 不用 Noto Sans——tokens6 只有 serif/mono/kai,sans 三字重 303 分片不入库)+ 两份 OFL 许可证;**Plex 改名**:`fontTools` 改写 name 表为 `NM Plex Mono`(OFL RFN 义务,原文件名 `nm-plex-mono-400/500.woff2`;`recalcTimestamp=False` 钉死 head.modified,重跑字节级幂等);`public/fonts/fonts.css` 只含 serif 与改名 Plex 的 @font-face(305 条,未压缩 304185 B/行尾 LF;serif 段按分片×字重交错排列以利 gzip,见 §5)
- **fonts.css 服务策略**:作为 public 静态文件由 `<link rel="stylesheet" href="/fonts/fonts.css">` 引入,**不走 Astro 打包**——606 分片的相对 url 交给浏览器按需取,构建零介入;代价是它本身是首个 CSS 请求,纳入 §5 预算
- 3D 资产(`public/3d/`:boot6/scene6/three×2/poster×2)**批次 2 入库**——本批首页不接 3D,提前入库即生产目录里的死资产,违反"不搬运未用资产"原则

## 3. 客户端行为白名单(= ADR-0010 清单;生产入口逐项)

全站脚本入口(批次 2 起):`<head>` 内联首帧主题脚本(内容签名进 smoke 断言)+ `public/scripts/site.js`(`<script src defer>`,W2-W4、W9-W12,全站);**首页额外两个**——`public/scripts/home.js`(`<script src defer>`,仅 `index.astro` 引用,W5-W8 页面侧)+ `public/3d/boot6.js`(`<script type="module">`,场景加载器)。smoke.mjs 为**白名单断言**:全站页仅允许前两者;`index.html` 额外允许 home.js 与 boot6.js 两个入口且**限定页面范围**(其余任何页出现即构建失败)。

| # | 行为 | 段 | 进入批次 | 无 JS / 失败时 |
|---|---|---|---|---|
| W1 | 首帧主题防闪(内联 ~3 行:读 localStorage 置 data-theme) | `<head>` 内联 | 1 | 不执行→系统色首帧(ADR-0002 原行为) |
| W2 | 主题三态切换 + `nm-theme` 事件 | site.js §1 | 1 | 不执行→跟随系统;按钮为静态 HTML,点击无效果但内容零损 |
| W3 | 移动菜单开合(Esc 收起) | site.js §2 | 1 | html.js 门控:导航平铺可点 |
| W4 | reveal 进场遮蔽 | site.js §3 | 1 | reveal-ready 门控:内容直接可见 |
| W5 | 页签目录↔3D 页叠双向联动 + 键盘漫游 | home.js §4(页面侧)/ boot6+scene6(场景侧) | 2 | 页签为静态 HTML,文章面板默认展开、链接可用 |
| W6 | 封面↔页头 `latest-cover` 挂名生命周期(转场配对) | home.js §4b | 2(页头侧常驻,批次 1 起存在但无配对源=无 morph) | 不挂名→普通 cross-fade |
| W7 | 朱砂装订线滚动延伸 + 落线转接(场景侧 boot6 注入) | home.js §5 | 2 | 首页专属;不渲染即无 |
| W8 | 「这个站」三层展开 | home.js §6 | 2 | 手风琴全部展开、无隐藏内容 |
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
- **测量方法**:`site/scripts/measure_budget.py`(2026-10-09 审计后修正版):①冷缓存访问 `/posts/hello-nanmu-blog/`,仅计 2xx 分型汇总,**失败响应单列**;②同 context 顺序访问其余三页,记**跨页唯一资源增量**(唯一 URL 去重口径——回答"该页引入哪些新资源",不是缓存命中证据);③可缓存服务(Cache-Control: max-age=3600)下 CDP Network 实测**真实暖缓存传输**(零传输且 2xx=缓存命中;该 Chromium build 不置 fromDiskCache 标志,以实测行为为准);④`fonts.css` 原始与 gzip(固定 Python zlib level 6、mtime=0;不同 gzip 实现数字不混比)。Lighthouse 移动档为批次 3 复核项。
- **验收预算(v2 修订;超标=停在该项回表,不默放)**:
  - 内页:HTML+CSS+JS 冷缓存合计 ≤ 500KB(**不含另列的 woff2 字体分片**;其中 JS gzip ≤ 8KB;fonts.css gzip 预期 ≤ 60KB);首访字体分片 ≤ 1.2MB,跨页新增以实测记录基线
  - 首页(批次 2):poster ≤ 450KB 且先于任何 3D 字节到达;3D(three+scene,gzip)≤ 220KB 且 idle 动态 import;LCP 以文档/poster 为准
- **poster/3D 真实加载策略(批次 2 实施细则,2026-10-09 授权后定稿)**:
  - **触发顺序(实现后以请求时间线断言验证,不靠 defer 语义自证)**:①poster `<img>` 在 HTML 内,解析即请求,`fetchpriority="high"`——**请求口径昼/夜分述(2026-10-09 校正,与 §5 实测一致)**:昼首访仅 light 单张(dark 为 display:none+loading=lazy,不请求);夜首访**双张**(light 是 eager 的 HTML img,display:none 不阻止下载;既存行为,未改传输策略)→ ②`site.js`(defer,全站)与 `home.js`(defer,仅首页,承载 W5-W8 页面侧)执行 → ③`boot6.js`(type=module)执行,先 WebGL 探测(失败=加 `.no-webgl` 类结束,3D 零请求)→ ④探测通过后 `requestIdleCallback`(无则 2s 超时兜底)再动态 `import` scene6——此时才发出 three.module/three.core/scene6 请求 → ⑤`texReady`(字体就绪纹理,3.5s 超时)后场景淡入、poster 淡出移除、HUD 注入。验收时间线断言:poster 请求的发起序号先于任何 3D 资源请求(昼夜均成立)。
  - **失败结束状态(各有明确终态,无空白/遮罩/永久加载)**:WebGL 不可用或模块加载/初始化失败 → `.no-webgl`,poster 常显、无 HUD,页签仍切换 HTML 面板;字体挂起 → 3.5s 超时后素纸场景接替 poster(纹理无字,console 告警);poster 自身加载失败 → alt 文本与 hero 竖排标题/页签/正文照常(视觉层之外的内容零依赖)。
  - **poster 定位=装饰性主视觉**:固定图像内容(一叠稿纸),**不承载「最新文章」身份**,alt 不提具体文章标题;最新文章由 HTML 数据(data-* JSON)与 3D 文字纹理实时承载,新文章发布即自动更新,poster 无需同步机制。
  - **暂停/离屏/恢复**(沿用原型规则):`setAmbient` 暂停动态后,用户主动操作(拖拽/复位/换页)与 resize 仍即时 `renderOnce`;IntersectionObserver 离屏停、回视口续;`visibilitychange` 同理;reduced-motion=静态完成态+立即换页。
  - **预算口径**:poster 按两张资产合计 ≤450KB(实测 428676 B=418.6 KiB;昼首访传输 light 单张,夜首访传输双张——呈现口径昼 light 夜 dark,与请求口径分开,见 §5 批次 2 实测);3D 合计=three.module+three.core+scene6+boot6 四件,gzip-6 ≤220KB;home.js 计入全站脚本 gzip ≤8KB 线的**首页专属口径**(内页不含 home.js,site.js 字节不增)。
  - **内容同源**:首页构建时把最新文章(标题/日期/分类/摘录/篇数/字数/URL)、日报状态、站点层说明以 `data-*` JSON 挂在 `#scene3d` 宿主;scene6 排印只读该数据,JS 内零内容副本。长标题按 measureText 换行(至多 3 行,超长截「…」);特殊字符原样排印;空摘要不排正文段、不虚构占位;无公开文章时模板层渲染空态、3D 文章页排「暂无文章」;草稿经 getCollection 过滤永不入数据。
- **预算检查在批次内的位置**:批次 1 验收=内页预算实测;批次 2 验收=poster/3D 预算实测;批次 3=全站复核与真机。
- **批次 1 实测记录(2026-10-09 审计收口后,measure_budget.py 修正版 + 交错 fonts.css,本地无压缩服务)**:
  - 冷缓存 `/posts/hello-nanmu-blog/`(仅 2xx,原始字节):HTML 3954 B + CSS 321303 B(含 fonts.css 304185 B)+ JS 7344 B = **332601 B(324.8 KiB)≤ 500KB ✓**;woff2 另列 819232 B(800.2 KiB)
  - fonts.css:原始 304185 B(行尾统一 LF 后),gzip-6 **34013 B(33.2 KiB)≤ 60KB ✓**——serif 段按「分片号 × 字重(400/600/900)」交错排列(1f25d9a)后由 92969 B 降至此;等价验证:305 条声明多重集合一致、每族每字重内部顺序一致、303 个分片 sha256 前后全等、文章页+about × 昼/夜 4 组整页截图逐像素零差异
  - 字体首访(四页累计新增分片):819232 + 42520 + 89784 + 74440 = **1025976 B(1002.0 KiB)≤ 1.2MB** ✓(贴线,减字重为备选,当前不需要)
  - 跨页唯一资源增量(唯一 URL 去重,非缓存证据):/posts/ +html 2624 B +1 分片 42520 B;/digest/ +html 2503 B +2 分片 89784 B;/about/ +html 9448 B +2 分片 74440 B
  - 真实暖缓存传输(CDP 实测,max-age=3600):重访文章页 26 请求全部零传输命中、网络 0 B;暖访 /posts/、/digest/、/about/ 仅传新增资源(45608/92991/84592 B,含响应头,零传输命中 25-28/27-31)——跨页复用有了网络层证据;冷访另有 favicon.ico 404(浏览器自动请求,站点无该文件,观察项)
  - JS:7344 B 原始(gzip 约 3KB)≤ 8KB ✓
  - **勘误(2026-10-09 用户审计裁决)**:本节早前版本把 woff2 并入 HTML+CSS+JS 后折算「约 920KB gzip」判超 500KB 线,并断言「500KB 线与 CJK webfont 物理现实矛盾」——属比较口径错误:该线自方案起即为「HTML+CSS+JS,首访字体分片另列 ≤1.2MB」,错误结论撤回;早前「fonts.css 超 60KB 预期」经交错排列优化后回到线内(非放宽条款)。历史错误结论保留在批次 0–1 session 作为记录,不伪装未发生
  - 附:批次 0 资产曾有一处缺陷(分片 url 前缀未剥 `fonts/`,全站 404 静默回退系统字体),由加严后的验收断言(仅计 2xx + `document.fonts.check` 实测)抓出,已在 0562ae9 修复——首次「34/34」中字体断言为假阳性的教训记录在案
- **批次 2 实测记录(2026-10-09,ffffd6e 后,measure_budget.py E 段 + verify_browser.py)**:
  - **poster 请求/呈现口径(2026-10-09 修正轮校正,昼/夜分述)**:
    - 请求(昼首访,浅色上下文):仅 poster-light 一张(#4,先于任何 3D 字节);poster-dark 因 display:none+loading=lazy 不发起请求
    - 请求(夜首访,dark 上下文):**双张**——poster-light 是 eager 的 HTML img(解析即请求,display:none 不阻止下载),poster-dark 可见即载;此为既存行为,修正轮未改变
    - 呈现:昼显 light、夜显 dark(CSS display 切换);3D 就绪(texReady 或 3.5s 超时)后 poster 淡出移除,此后昼夜切换由场景 setTheme 接管(poster 已退场);WebGL 不可用/初始化失败时 poster 常显不退
  - E1 触发顺序(CDP requestWillBeSent 发起序,昼上下文):poster-light **#4** → boot6 #6 → scene6/three×2 **#30–32**——poster 先于任何 3D 字节;昼上下文下仅 light 单张(修正轮复测不变;夜首访双张,见上)
  - E2 预算(修正轮复测):3D 四件 gzip-6(zlib-6,mtime=0)合计 **197438 B(192.8 KiB)≤ 220KB ✓**(three.module 79012 + three.core 100875 + scene6 13875 + boot6 3676;较 ffffd6e 增 ~0.9KiB,为同源参数化与失败清理的代价);poster 两张合计 428676 B(418.6 KiB)≤ 450KiB ✓
  - 字体挂起路径(hang 前 2 个 woff2 各 9s):素纸场景接替 poster 终态 ~7s 达成(独立复现时间线:t=5.8s 场景就绪、t=6.8s poster 退场),`__bookscene` 可用、rAF 正常
  - 手机 360/390/430(has_touch):3D 场景就绪、56dvh(844 高实测 473px)、canvas `touch-action: pan-y`(水平拖转场景/垂直滚动页面)、零横向溢出;390 视检:纸面为真实文章内容(标题+摘要,内容同源生效)
  - 交互验收(verify_browser 73/73):boot 终态/页签↔场景双向联动/快速连选只保留末次/选回正在进入前景的页/暂停组合(暂停→选择→拖拽→resize→复位→恢复)/WebGL 不可用零场景请求(仅 boot6 探测入口)/scene6 abort 终态 poster 常显/字体挂起接替/封面挂名两条回程不残留;**3D 页面点击进文章(第三入口)录屏实测**:文章页头挂名 `latest-cover` 正确,回程后首页封面卡挂名已摘除
  - 全站脚本入口复核:首页 4(site.js+内联主题+home.js+boot6)、内页 2——smoke 白名单断言限定页面范围
  - 测试侧两处自坑修复(记录在案):verify N 段 poll 表达式三态 'pending' 字符串真值短路(poll_js 真值语义),measure E1 requestWillBeSent 回调取参 `e["params"]` 恒 KeyError 被吞(playwright 回调参数即 params 本身)——均为断言侧缺陷,功能时间线由独立复现证明
- **批次 2 定点修正轮实测(2026-10-09,审计后,五项)**:
  - 手机交接区单格化(TDD 反例先行):反例 A 复现双 56dvh(host 落在 poster 下一格,heroBottom=1398 膨胀)→ boot6 在 host 入 DOM 时挂 `.has-scene` + home.css 手机段 poster 转 absolute 叠加 → 交接期 host 与 poster 同格(hostInHero=473=56dvh,heroBottom=926);反例 B 以 route fulfill 注入「createScene 首行抛错」复现半成品 host 残留(hosts=1)→ 失败 catch 清 host+has-scene → hosts=0、poster 独撑回静态布局(no-webgl/无 JS 无此类,poster 独撑不受影响)
  - 就绪前主题切换不丢:boot6 弃 import 回调内旧快照,抽 nowDark() + nm-theme 监听提前注册(bookScene 未就绪时忽略,就绪时 setTheme(nowDark(), true) 采用最新值);scene6 api 增只读 themeDark()(themeTarget 观测点);反例(挂起 2 分片拖长 createScene 窗口,host 已现时连点两次切 dark)RED(场景 False)→ GREEN(sceneDark=True);N 段固化该断言
  - 日报状态/站点说明同源:data-digest(`{latest:{date,count}}`|空串)与 data-site(三层 name/state/solid)由 index.astro 构建期派生,页面层列表 li-state 同源引用(有期时「在线 · 每日一期」+class ok);boot6 解析传 opts.digest/opts.site,scene6 digestTex/aboutTex 参数化(缺省退内置默认),fontsReady 样本扩至动态三层/日报文本;夹具三态(零期=空串空态、一期=2026-10-04/2 条、更新=2026-10-05/5 条)临时构建实测 PASS,有期 3D 纹理截图视检(「最新一期:2026-10-04」入画,shots/r6-b2-3d-digest-fixture.png);verify I 段固化 data-site 与 li-state 逐字同源断言
  - 排队反例入生产验收:K 段新增 requeue-digest(动画中 digest→about→digest 变向,poll 稳定终态 digest+页签同步),验收 73→74 项
  - 回归:verify_browser **74/74**(另一轮出现过一次 73/74 偶发失败,当轮输出未存档、项未定位,后续三轮全绿;如再现以完整日志定位)、npm run verify 绿、check_docs 零错误、E1/E2 复测通过(见上);证据归档 shots/r6-b2-*(桌面昼/夜 top+full、手机 390 滚后整页、交互录屏含 3D 第三入口两回程、有期 3D 日报页)——注:手机整页截图须先逐节滚动触发 reveal(is_mobile 下 scrollTo 一次到底不触发 IO,整页截图会呈现节缺失假象,真实滚动浏览正常,视口逐节截图与滚后整页均完整)

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
| 1 公共布局与内页 ✅ c743993..e91d7c5 | Base/Header/site.js(W1-W4,W9-W12)/smoke 白名单/posts+post/digest 列表+详情/about/404/index 静态适配 | verify + `verify_browser.py`(昼/夜/手机 390/无 JS/键盘/直接访问与返回/reduced)+ 夹具构建浏览器抽验 + 预算实测(34/34;预算全过,§5 实测+勘误) | 见下方回退依赖 |
| 2 首页 3D ✅ 72a4c42 + a498f05 + ffffd6e | 验收工具先行(RED 34/73)→ 静态首页(home.css/真实内容接线/W5-W8)→ 3D(public/3d 四件/boot6 idle/scene6 内容同源/poster 先于 3D) | verify_browser **73/73** + measure E1/E2 + 手机三宽视检 + 3D 入口挂名录屏(§5 实测) | 3D 段独立 revert(ffffd6e),静态首页保留(a498f05 不依赖 3D 可读可用) |
| 2R 定点修正 ✅(2026-10-09,审计后) | 手机交接区单格化+失败清理 / 就绪前主题不丢 / 日报·站点状态同源(data-digest·data-site) / 排队反例入验收 / poster 口径校正+证据归档 | verify_browser **74/74** + 夹具三态 + E1E2 复测(§5 修正轮实测) | 回退路径已隔离实测(2026-10-09):自 1e23049 起 **revert 809cdd8 → revert ffffd6e**(后进先出),两笔均无冲突;隔离检出 astro build+smoke 绿,浏览器验收 3/3(静态首页 hero/页签/封面卡完整、零 three/scene/boot 请求与引用、手机 poster 独撑一格)。注意:回退后 verify_browser.py 回到 72a4c42 工具先行版(3D 断言为 RED 设计),**回退态验收以 npm verify + 上述浏览器检查为准,不跑 verify_browser 全量** |
| 3 测量收尾 | Lighthouse 复核、真机补测、预算回填 | 实测值回表 | 文档修正 |

**回退依赖(提交序)**:批次 1 内按 C2 布局(Base/Header/site.js/smoke,global.css 暂与新样式并存兜住未迁移页)→ C3 posts 两页 → C4 digest 两页 → C5 about+404+index 适配并移除 global.css。每提交点 `npm run verify` 绿、站点完整可用;**revert C2 必须先 revert C3–C5**(页面模板依赖新布局类);C3/C4/C5 可单页 revert。验收脚本(verify_browser.py/measure_budget.py)独立提交于 C1,先于实现入库(RED 证据在 session 记录)。

## 8. 已知风险与待裁决

- VT 跨页在旧浏览器退化为普通导航(无破坏);Safari/Firefox 未测(Chromium-only 验收,已标)。
- three 720KB 未压缩——**批次 2 实测后裁决(2026-10-09):移动端保留 3D**。依据:四件 gzip-6 191.9 KiB ≤ 220KB 线内;手机三宽场景就绪、56dvh、touch-action pan-y、零溢出、构图视检正常;poster 先行保证无 3D 时可用。「移动端仅 poster」备选保留在案(若真机/低端机实测帧率不达标再启用)。
- 字体首访 ~1MB 贴 1.2MB 线(备选:减字重,当前不需要);fonts.css gzip-6 34013 B(交错排列后),生产 Caddy 实压缩口径待批次 3 复核。
- 预算条款状态(2026-10-09 勘误后):内页 500KB 线(不含 woff2)实测 332601 B 在线内;fonts.css gzip 经交错排列回到 60KB 线内。早前「两条超线、方案内在矛盾」的结论系把 woff2 并入比较的口径错误,已撤回(§5 勘误段;历史记录见批次 0–1 session)。
- 移动端真机触摸未实测(模拟器证据 only;批次 2 手机 360/390/430 布局+3D 视检已过)。
