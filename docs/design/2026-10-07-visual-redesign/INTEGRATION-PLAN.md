# R6 正式接入方案(提案)

- 状态:待评审(与全站统一原型同批交付;方案本身不是已生效规则)
- 日期:2026-10-09
- 对象:R6 全站统一原型(`prototypes/r6/`,基线 a45dc39 之后的本轮工作树)→ 生产站 `site/`
- 关联:[R3-REVIEW.md](R3-REVIEW.md) · [prototypes/site/map.html](prototypes/site/map.html) · ADR-0002 调整提案(见 `docs/decisions/0010-*.md`,同批)

## 0. 范围与原则

接入对象只有四类资产:**token 与样式**(tokens6/base6/pages6)、**全站脚本**(site6.js)、**首页 3D**(boot6/scene6 + three r180 本地固定 + poster)、**字体分片**(fonts/ + fonts.css)。

**不进生产**:R1–R5 全部历史原型、lab 实验页、search-m2 概念稿、shots 与 rec 证据、poster-capture 调试页、页面内的夹具/演示块(posts 夹具、digest 变体、post specimen 样张)。历史材料永久留在本设计目录。生产改造只动 `site/src` 模板层与 `site/public` 静态资产;内容 collection、校验、RSS 端点、构建流程一律不动,不引入数据库/后台/构建期模型调用。

## 1. 原型页 → Astro 路由映射

| 原型页(r6/) | 生产路由(现有,不新增) | 备注 |
|---|---|---|
| index.html | `src/pages/index.astro`(首页) | 唯一 3D 页 |
| posts.html | `src/pages/posts/[...page].astro` | pageSize 10 保持;原型下半的多页节奏**夹具不接** |
| post-hello.html | `src/pages/posts/[id].astro` | 页内 specimen 样张框**不接**(原型演示块) |
| digest.html | `src/pages/digest/[...page].astro` | 列表夹具(3 期/长模型名两态)**不接**,仅真实数据渲染 |
| digest-2026-10-05.html | `src/pages/digest/[id].astro` | 变体夹具**不接**;正文结构由 assemble.py 产物决定 |
| about.html | `src/pages/about.astro` | 「待填」槽照搬语义,不虚构内容 |
| 404.html | `src/pages/404.astro` | 保持不泄露条目存在性 |
| —(订阅条) | `rss.xml.js` / `digest.xml.js` | 端点不动,订阅条链接指向 |
| search-m2.html | **无路由** | M2 概念稿,不接、不进导航 |

## 2. 共用资产:原型三层 → 生产一层

原型因静态 HTML 不得不分 tokens6(全站)/ base6(首页)/ pages6(内页),其中约 80 行基础段在 base6/pages6 重复——这是"逐页复制"问题的根源,生产由 **Astro 布局消解**:

- `site/src/styles/tokens.css` ← tokens6.css 原样(双主题 token,`data-theme` 三态 + `prefers-color-scheme` 兜底;`--paper2` 已含)
- `site/src/styles/base.css` ← base6 与 pages6 的**并集去重**(基础排版/导航/页脚/印章/焦点/reduced-motion/VT 声明序:auto 在前、reduced none 在后,顺序是已知陷阱)
- 首页专属段(场景宿主/页叠/HUD)→ 独立 `home.css`,仅首页布局引入;页面特有样式(404 gate、about vignette)留各 `.astro` 页内 `<style>`
- 布局:`layouts/Base.astro` 承载全站骨架(header/footer/theme-btn/menu-toggle + `<script src>` 引 site.js);`Header.astro` 改为 R6 导航(含 `aria-current`,替代现行 `active` 类逻辑)
- `site/public/fonts/` ← 分片目录整拷;`fonts.css` 并入全局样式
- `site/public/3d/` ← boot6/scene6/three×2/poster×2(仅首页引用)

## 3. 客户端脚本清单(全部并入 `site.js`,defer,全站加载)

| 段 | 加载页面 | 性质 | 无 JS / 失败时行为 |
|---|---|---|---|
| §1 主题三态(nm-theme + localStorage) | 全站 | 增强 | 跟随系统(纯 CSS `prefers-color-scheme`,即 ADR-0002 原行为) |
| §2 移动菜单 | 全站 | 增强 | 导航平铺可读可点(html.js 门控) |
| §3 reveal 进场 | 全站 | 纯装饰 | 内容直接可见(reveal-ready 门控) |
| §4–7 首页:3D 管理/挂名生命周期/换页排队/盖印复制 | 仅首页 | 增强 | poster 静态图;RSS 链接可手复制 |
| §8 阅读进度 + 目录书签 | 文章详情 | 增强 | 目录仍是普通锚链接,点击照常跳转 |
| §9 代码块复制 | 文章详情 | 增强 | 代码可读可手选 |
| §10 图片展开(原生 dialog) | 文章详情 | 增强 | 图片原样内联显示 |

全站脚本 ~14KB 未压缩、零第三方依赖;所有段带元素守卫,在不含对应元素的页面为空操作。首页 3D 另加载 `boot6.js`(module)。

## 4. 3D 策略(仅首页)

- **加载序**:poster 先占位(随主题切换昼夜两图)→ boot6 探测 WebGL(`getContext` 失败即停,不发模块请求)→ 动态 `import('./scene6.js')` → 场景内字体样本门控(文档字体到位后再排印上页,避免错字闪现)。
- **销毁**:非 SPA 导航(生产即 Astro 静态多页)随页面卸载自然销毁;`latest-cover` 挂名只存在于首页文档与文章页头,§4b 已管排队与恢复,生产沿用同一逻辑,不新增跨页状态。
- **暂停**:HUD 暂停/恢复(aria-pressed 同步)+ 离屏暂停(IO)。
- **回退**:WebGL 不可用或初始化抛错 → poster 常驻,内容与导航零损(已实测:verify6 §I)。
- **reduced-motion**:CSS 层 VT 归零、进场归零;场景动态归零为静态完成态,poster 优先。
- **资产预算**:three r180 本地固定两文件共 ~720KB 未压缩(估 gzip ~180KB)+ scene6 34KB + boot6 6.7KB + poster 2×~214KB;只在首页、poster 之后、非渲染阻塞加载。

## 5. 字体与资源进入生产

- 方案照搬 [prototypes/fonts/FONTS.md](prototypes/fonts/FONTS.md):606 个 unicode-range 分片(18MB 仓库体积)整目录进 `site/public/fonts/`;**磁盘 ≠ 传输**,实测原型首载命中 28 个分片约 1MB,站内后续页面全走缓存,与日报新增汉字解耦。生成脚本已入库可复现,构建只做拷贝。
- **OFL 合规前置条件**:Plex 子集进入生产前须在生成脚本改写 name 表另起字体名(FONTS.md 已标注 RFN 义务),Noto 无 RFN 但对外宣传避免商标化表述。
- **测量方法**:Playwright 网络监听脚本(沿用本轮联调基建)记录冷缓存传输字节 + Lighthouse 移动档复核;预算超标即在本方案内回表,不默放。
- **验收预算(提案初值,批次 3 实测校准)**:
  - 内页:JS 传输 ≤ 8KB(site.js gzip);0 第三方请求;字体不阻塞首绘(font-display:swap 已设),首访字体传输 ≤ 1.2MB、回访 ≈ 0
  - 首页:poster ≤ 450KB 且先于任何 3D 字节到达;3D(three+scene)合计 gzip ≤ 220KB 且全部懒加载;LCP 以 poster/文档为准,不被 3D 阻塞

## 6. 内容契约保留(逐项核对,模板层改动不碰数据流)

| 契约 | 生产现状 | 接入后 |
|---|---|---|
| 草稿隔离 | 每出口 `filter(!data.draft)`;`drafts-example.md` 永不发布 | 查询逻辑一行不动;只换渲染模板 |
| RSS | `rss.xml.js` / `digest.xml.js` 独立端点 | 端点与条目字段不动;订阅条 URL 指向同两端点 |
| 404 语义 | 极简页,不泄露被撤回内容是否存在 | 沿用原型同语义(缺页意象不携带任何条目信息) |
| AI 标注/模型/费用 | 列表行与详情页头渲染 `ai_model`/`entry_count`/`cost_cny` | 图签(titleblock)数据源 = 同一 frontmatter,字段一处不增删 |
| cost_pending | `(含未决预占,为保守上界)` 两态文案 | 原型已做两态夹具,生产按 schema 布尔渲染同一文案 |
| 构建校验 | `assertPostsIds`/`assertDigestIds` 全出口调用,违约即构建失败 | 调用点保持;新模板不绕过 `getCollection` |
| 零模型调用 | 页面与构建不调 LLM(铁律) | 不变;3D/主题/阅读增强均纯前端 |

## 7. 接入批次(每批独立提交、独立验收、独立回退)

| 批 | 内容 | 验收 | 回退 |
|---|---|---|---|
| 0 资产入库 | fonts/ + 3d/ 进 `site/public`,tokens.css/base.css 进 styles;Plex 改名 | `npm run verify`(build+smoke+fixture)绿;页面尚为旧版式 | revert 单提交 |
| 1 内页换版 | Base/Header 改造 + posts/digest/about/404/页脚/订阅条接 R6 版式 | 移植 verify6 矩阵(昼夜×页/手机 390/无 JS/reduced/键盘/深链→返回)+ `npm run verify`;真机抽测(缺则标未测) | 每页一提交,可单页 revert |
| 2 首页 | 先静态版式(无 3D,poster 常驻)合入;再单独提交 3D 段(boot/scene/挂名/暂停) | 同矩阵 + WebGL 失败降级 + r6 修正轮回归(排队 8/8、挂名 8/8)移植为 site 版脚本 | 3D 段独立 revert,静态首页保留可用 |
| 3 测量收尾 | 性能预算实测、OFL 合规复核、真机补测 | 预算表回填实测值,超标项裁决 | 文档修正,无代码回退 |

约束:全部批次只在本地分支进行,合入与部署另行裁决;每批交付时在 session 记录验收证据链接。

## 8. 已知风险与待裁决

- **View Transitions 跨页**(:has/auto)在旧浏览器退化为普通导航,无破坏;Safari/Firefox 表现未测(本轮 Chromium-only,已标未测项)。
- **three 体积**:720KB 未压缩是当前唯一的大额静态资产;若批次 3 实测移动端体验不达标,备选 = 移动端只出 poster(方案内回表裁决,不默改)。
- **字体首访 1MB**:接受与否属产品判断;备选 = 减字重(6 → 4)。
- **主题切换按钮**与 ADR-0002「零客户端 JS」的张力 → 由同批 ADR 调整提案裁决,本方案不预设结论。
