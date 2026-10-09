# 2026-10-09 R6 批次 0–1:资产入库与内页接入

> HEAD(本文写入时):0562ae9;分支 codex/r6-interaction(仅本地,未推送/未合并/未部署)。

## objective

按用户 2026-10-09 指令完成 R6 接入方案 v2 修订后的批次 0(资产入库)与批次 1(公共布局 + 内页本地接入),TDD 方式(验收脚本先入库先跑 RED),每提交点站点完整可用,真实内容验收,交付 SHA/实测/剩余边界。

## state

- 批次 0(5aa996e):`site/scripts/build-site-fonts.py`(serif 303 分片 + NM Plex Mono 改名 2 件 + fonts.css 305 条)+ `src/styles/tokens.css`/`base.css` 入库未被引用;verify 绿。[verified: 提交 5aa996e,脚本输出 serif faces 303|shards 303|plex 2]
- 批次 1 提交序(每步 `npm run verify` 绿):
  - C1 c743993:`scripts/verify_browser.py`(34 项断言)+ `scripts/measure_budget.py` 入库;对旧版式 dist 实测 **2/34 PASS = RED 基线**(失败全为 R6 结构缺失)。[verified: 运行输出留档于会话记录]
  - C2 19bc640:Base.astro(fonts.css link + W1 内联主题脚本 `is:inline` 逐字 + site.js defer + footer.site;global.css 过渡并存)/ Header.astro(R6 导航 + aria-current 首页精确、栏目前缀)/ `public/scripts/site.js`(W2-W4、W9-W12;§10 改扫 `.prose img`,caption 取 figcaption)/ smoke.mjs 白名单(仅 `/scripts/site.js` + 内联主题脚本内容签名逐字)。[verified: dist 内 `<script>` 两处逐字 grep 比对]
  - C3 e04ff3e:posts 列表(list-head/row-item/摘要=首段派生 90 字截断/pager/blank-sheet/RSS 订阅条)+ 文章页(progress-bar/paper-head 第 N 篇/toc 按 `render()` headings 条件渲染——真实文章无标题故不出现/colophon/prev-next 上一篇=更早方向)。
  - C4 fe24ef1:digest 列表(机印/blank-sheet 真实空态/成本行含 pending 文案)+ 详情(titleblock 三行溯源/issue-body 结构选择器引文/issue-foot/prev-next)。
  - C5 e91d7c5:about(about-grid+vignette SVG+facts+双 RSS,页内 style 同原型)/ 404(gate SVG 动画各一次、reduced none)/ index 静态适配(同数据不加功能)/ **删 global.css**。
  - 0562ae9:**字体分片 url 前缀修复**——build-site-fonts.py 未剥原型 `fonts/` 前缀,CSS 在 `/fonts/` 下解析成 `/fonts/fonts/shards/`(全站 404 静默回退系统字体);首次 34/34 中字体断言(≥5 个 woff2 响应)把 404 也计入,属假阳性;加严为「仅 2xx + `document.fonts.check('Noto Serif SC')` 实测装载」后抓出并修复(url 重跑,fonts.css 304490 B)。
- 最终验收(真实内容,clean build):`npm run verify` 绿;`verify_browser.py` **34/34 PASS**(含昼/夜 ×6 页矩阵、手机 390、无 JS、键盘、reduced、主题三态持久化、连续路径 aria-current 跟随、serif 实测装载)。
- 夹具抽验(手动注入 `tests/fixtures/2026-10-04.md` → build → 浏览器 → 删除 → clean verify 绿):列表行成本文案「¥0.41 含未决预占,为保守上界」、详情 titleblock 同标注、引文朱砂左边框 rgb(194,64,42)、移动 390 无溢出且 titleblock 转列、零 console 错误。
- 预算实测(measure_budget.py,本地无压缩服务):见 INTEGRATION-PLAN §5 实测记录——冷缓存文章页 1125.2KB raw / 约 920KB 生产 gzip 口径;fonts.css 304490 B raw / 92707 B gzip;字体首访四页累计约 1006KB;JS 7344 B raw。
- 文档:INTEGRATION-PLAN 状态/§5 实测/§7 批次标记/§8 风险更新;ADR-0010 与 coding-standards 已在 a2d3a60 同步(本批无新增白名单项)。

## disposition

continuable(批次 2 首页 3D 未开始;预算偏差待用户裁决)。

## next_action

1. **用户裁决预算条款**:内页冷缓存 500KB 线与 fonts.css 60KB 预期均被实测打破(INTEGRATION-PLAN §5 实测记录含修订建议:非字体资源 gzip ≤120KB + 字体单列 ≤1.2MB;或减字重,但后者改变版式)。裁决前不推进批次 2 的预算扩项。
2. 批次 2(首页 3D):home.css + public/3d + W5-W8 + §4b 挂名(来源正则改 `/posts/<id>/`)+ poster 策略;同矩阵验收 + WebGL 降级 + 预算实测。
3. 批次 3:Lighthouse 移动档、真机/Firefox/Safari 补测。

## omissions

- VT 跨页过渡**效果**未在本批断言(getAnimations 抓不到跨文档 VT,此前会话已证);仅断言了 `latest-cover` 挂名存在与声明序。转场观感仍属人工判断。
- 浏览器验收仅 Chromium 1248;Firefox/Safari/真机未测(批次 3)。
- 预算为本地 http.server 无压缩口径 + gzip 折算估算,非生产 Caddy 实测;Lighthouse 未跑。
- reduce 字重/子集化等预算优化方案未做(超出本批授权,涉及版式变更)。
- 首页仍为静态适配版,原型 3D 首页未接(批次 2 边界,非缺漏)。
- `page.total`/`render().headings` 为 Astro 运行值,已由构建成功间接验证,未单测。
