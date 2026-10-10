# 会话交接:R6 批次 3 修正轮——导航回归/对比度/TBT 对照/DSF 勘误(2026-10-10)

- **recorded_at**: 2026-10-10 10:38 Asia/Shanghai
- **continues**: [2026-10-10 兼容验收+现网基线](2026-10-10-r6-batch03-compat.md)(bf75029)
- **repository**: 起点 HEAD = bf75029;分支 `codex/r6-interaction`(仅本地,未推送/未合并/未部署)。本轮提交:febbdd9(任务 1)→ bf7f49a(任务 2)→ 5fee3eb(任务 3+4 产物);文档收尾提交见 Git 实况
- **objective**: 用户审计复核批次 3 后的有限修正与补证,四项:①修复 head 提前添加 `.js` 后的手机导航降级回归(正常首帧稳定 + site.js 请求/初始化失败时主导航可访问 + 无 JS 回归,点击后实际可用性入验收,覆盖首页与内页)②夜间主阅读按钮文字对比度达 WCAG AA 4.5:1(昼夜与 hover,现有设计系统内最小调整)③同移动节流「正常 3D/静态首页」对照,场景初始化窗口测目录/页签/阅读入口操作响应,记录长任务与 LCP 候选,据证据定夺不放宽标准④Lighthouse DSF 勘误+机器可读摘录入库。范围边界:不扩展新功能或新美术探索;性能取舍需用户决定的先交数据与方案;保存完整运行日志,及时提交,干净工作区交付复核;合并/推送/部署仍按用户明确授权

## fix_p1 手机导航降级回归(febbdd9,TDD)

- **缺陷**:批次 3a 把 `.js` 类提前到 head 内联首帧脚本后,site.js 请求失败或初始化失败时无人摘除 `.js`,`html.js nav.main{display:none}` 门控持续生效——手机 390px 阻断 /scripts/site.js 后点「目录」nav 不可用(用户实测复现)。
- **RED**:verify_browser.py 增 R 段三项——R1(首页)/R2(内页)=route abort site.js 后 poll 摘类+nav 平铺+**实际点击导航链接完成跳转**;R3=route.fetch 取原 site.js 响应体、在 `classList.add('js')` 行后注入 `throw new Error('b3-init-fail-probe')`(落在产品 try 块内,验初始化失败路径)。RED 实跑 **78/81**,三项 click 超时 FAIL。
- **GREEN**:Base.astro script 标签 `onerror="document.documentElement.classList.remove('js')"`(网络层失败)+ site.js 双层 IIFE 主体包 try/catch、catch 摘 `.js`(初始化失败)——双路都使门控失效回退无 JS 平铺。GREEN **81/81**;D 段无 JS 回归保持。
- **Q1 随之改正常路径归因**:旧断言「abort 后 js 类快照」随 onerror 修复必然翻车(失败路径检验整体移交 R 段),改为 MutationObserver 记 js 类添加时刻断言早于 first-paint(实测 tAdd≈18ms < fp≈104ms),正常首帧稳定有归因证据。

## fix_p2 夜间主按钮对比度(bf7f49a,TDD)

- **缺口**:夜间常态 #F7F4EB on --seal #D4604C = 3.42:1、hover on --seal-text #E08A72 = 2.37:1,普通文字 4.5:1 双不达标(WCAG AA 1.4.3)。
- **修法(现有设计系统内最小调整)**:tokens.css 夜块 `--seal-deep:#B5432F`——保 #D4604C 色相(H8.8° 偏差 0.1°)、饱和度不动仅降亮度 L56.5→44.7 → **5.01:1**;home.css 夜间 `.btn.primary` 底/边换 --seal-deep、hover 底色同值保持对比、反馈改亮边 --seal-text(特异性 `:root[data-theme="dark"]` (0,4,0) 压过 `.btn.primary:hover` (0,3,0))。昼间 --seal-deep=#A83622=原 hover 值,**昼间视觉零变化**;`.primary` 全站仅首页面板「读全文」两处覆盖,朱砂品牌色 #D4604C 不换。
- **S 段验收**:按计算样式实取颜色算 WCAG 比率,昼/夜 × 常态/hover 四态断言。RED **82/83**(dark 态 FAIL)→ GREEN **83/83**(light norm 4.70/hover 5.94 不变,dark norm/hover 均 5.01)。夜间常态+hover 截图归档 shots/r6-b3-btn-contrast-dark-*。
- **验收时序**:采样前 poll `document.styleSheets.length >= 2`(DCL 不等样式表);goto 后等 900ms(reveal 进场)再取态,hover 后等 400ms(≥--t-fast .18s)。

## tbt_compare 同节流 3D/静态对照(5fee3eb)

- **工具**:`site/scripts/tbt_probe.py` 入库(一次性对照补证,无 PASS/FAIL 判定)。CDP 真节流 `setCPUThrottlingRate 4` + `emulateNetworkConditions`(latency 150ms/download 1.6Mbps/upload 93750bps)——与批次 3 Lighthouse 移动档同条件;390×844 is_mobile has_touch;full 组=正常首页,static 组=route abort `**/3d/scene6*`+`**/3d/three*`(boot6 保留,探测后走失败清理 poster 常显);PROBE_JS 注入 PerformanceObserver(longtask/lcp buffered/fcp)+capture click listener(rAF 记输入→下一帧 dt,.btn.primary preventDefault);ROUNDS_AT=(7,9,11,13) 墙钟秒每轮点 menu-toggle 开/关、#tab-digest→#tab-posts、.btn.primary。
- **结果**(logs/r6-b3-tbt-compare-{full,static}.json + .log 全文):
  - **操作响应两组无差异**:menu 中位 5 vs 4ms、tab 8 vs 8ms、read 1 vs 1ms;全部 20+20 样本 ≤19ms;无一次点击落入长任务(最近一次长任务与点击间隔 115ms)。
  - **长任务**:full Σ949ms(377@12.508s + 371@15.980s + 201@16.351s,attribution 均 unknown)vs **static 0**——代价全部来自 3D 场景构建/首帧渲染。
  - **LCP 候选两组同为 poster-light.png**(184470B;full 3984ms vs static 3848ms,FCP 同刻)。
  - full 组 posterGone=False 系 17s 探测窗口内淡出未走完(4× 节流拉长时间线;无节流 boot 终态批次 2 已验收),非缺陷;static 组 sceneReady=False 走失败清理路径符合设计(threeReqs 含 scene6 系请求发出但被 abort,request 监听仍记录)。
- **结论**:TBT 代价时间上均在 LCP 后、不与交互窗口重叠,操作可用性无影响;**是否优化属性能取舍,未动 3D,选项与数据提交用户裁决**(INTEGRATION-PLAN §8:A 接受现状 / B 分帧构建优化 / C 移动端仅 poster)。

## evidence 证据收尾(5fee3eb + 本轮文档提交)

- **DSF 勘误**:Lighthouse 移动档实际 `configSettings.screenEmulation.deviceScaleFactor`=**1.75**(412×823);2026-10-09 perf session 第 9 行原文误记「DSF2」,已按用户明示勘误(保留勘误痕迹不改写其余历史)。
- **机器可读摘录入库**:logs/r6-b3-lh-after-{home,post}.excerpt.json(2826/2300 B)——source 指针+fetchTime+version+finalUrl+environment+config(formFactor/throttlingMethod/screenEmulation/throttling)+performanceScore+10 项关键 audits+longTasks 明细(startTime/duration/url;Lighthouse 13 的 items 已无 startTimestamp 字段,首版提取全 null 已删)。完整原始 JSON(含 13MB trace)留 C:/tmp/b3-lh 未入库。
- **摘要核对**:home perf 0.50/FCP 2143.5/LCP 7081.4/TBT 846.4/CLS 0.0008/SI 5187/interactive 15861,长任务 6 项(scene6 543.9@10.38s、文档 489.7@1.65s、未归因 317@15.43s、three.module 116.7@15.74s、63.6@3.66s、55.1@3.73s);post perf 0.98/LCP 1941.2/TBT 0/CLS 0.0046,长任务 1 项 471ms 在 TTI 后(不计 TBT)。

- **change_scope**:
  - `site/src/layouts/Base.astro`:script 标签 onerror 摘类(febbdd9)
  - `site/public/scripts/site.js`:双层 IIFE try/catch 兜底(febbdd9)
  - `site/src/styles/tokens.css` / `home.css`:--seal-deep 夜块与夜间 .btn.primary(bf7f49a)
  - `site/scripts/verify_browser.py`:Q1 归因改造+R 段+S 段(76→83 项;febbdd9/bf7f49a)
  - `site/scripts/tbt_probe.py`:新增(5fee3eb)
  - `docs/design/2026-10-07-visual-redesign/logs/`:r6-b3-tbt-compare-{full,static}.json、r6-b3-tbt-compare.log、r6-b3-lh-after-{home,post}.excerpt.json(5fee3eb)
  - `docs/design/2026-10-07-visual-redesign/shots/`:r6-b3-btn-contrast-dark-{norm,hover}.png(bf7f49a)
  - `docs/design/2026-10-07-visual-redesign/INTEGRATION-PLAN.md`:状态行+§5 修正轮实测+§7 3c 行+§8 TBT 待裁决行(本轮文档提交)
  - `docs/sessions/2026-10-09-r6-batch03-perf.md`:DSF 勘误(本轮文档提交)
  - `AGENTS.md`:第七轮段更新(本轮文档提交)
  - 外部操作:未执行(无推送/合并/部署/付费/服务器访问)

- **verification**:

| 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
|--------------|--------------------------------|
| site/(Chromium,本地服务) | `python -I scripts/verify_browser.py`(任务 1 RED 轮) | **78/81**(R1/R2/R3 三项 click 超时 FAIL,符合预期) |
| site/ | `python -I scripts/verify_browser.py`(任务 1 GREEN 轮) | **81/81** |
| site/ | `python -I scripts/verify_browser.py`(任务 2 RED 轮) | **82/83**(S 段 dark 态 FAIL) |
| site/ | `python -I scripts/verify_browser.py`(任务 2 GREEN 轮+后续回归) | **83/83** |
| site/ | `npm run verify` | 绿(构建+smoke+夹具临时构建) |
| site/(本地 8944 + CDP 节流) | `python -I scripts/tbt_probe.py` | full/static 两组成形,stdout 全文归档 r6-b3-tbt-compare.log(首跑因 LOGS 路径假设错误失败,修正后成功) |
| C:/tmp(本地 8982 gzip 服务) | b3-lh-excerpt.py(一次性,不入库) | 两份摘录生成并入库;startTimestamp 字段 Lighthouse 13 已无,首版全 null 删后重提 |
| 仓库根 | `python scripts/check_docs.py` | 零错误(文档提交前) |

- **pending_runtime**: C:/tmp/b3-lh 完整 Lighthouse JSON+trace(不入库)、C:/tmp/b3-lh-excerpt.py 与 b3-serve*.py(一次性工具,不入库)、C:/tmp 本地 8981/8982/8944 服务(本轮结束应已停,接手时核对)
- **decisions_needed**: ①**TBT 949ms 取舍**(INTEGRATION-PLAN §8:A 接受现状/B 分帧构建/C 移动端仅 poster——数据与探针已入库,用户裁决前 3D 不动);②合并 main/推送/部署仍待用户明确授权
- **disposition**: complete(四项全部交付;TBT 取舍按指令作为待裁决项提交,不自行放宽标准)
- **next_action**: 用户复核本报告并裁决 TBT 取舍;若选 B/C 另开任务重跑对照验证。本文档不自动授予任何提交外权限
- **omissions**:
  - full 组节流下 17s 窗口内 poster 未退场系探针窗口限制非产品缺陷(无节流终态批次 2 已验收);未延长窗口重跑
  - 长任务 attribution 均 unknown(Chromium longtask API 不给调用栈);归因靠 static 对照(0 长任务)+Lighthouse long-tasks audit url(scene6/three.module)旁证
  - 真机(触摸/Safari/帧率)仍无设备登记待验(沿批次 3b 口径)
  - S 段对比度为计算样式实取+WCAG 公式断言,未做人类视觉评审(截图已归档供用户查看)
