# R6 全站风格统一 + 正式接入方案(2026-10-09)

指令:以 a45dc39 为基线,完成全站风格统一(不加首页功能)、同步写正式接入
方案与 ADR-0002 调整提案、按典型页面与连续路径验证、随批提交交接。不另起
R7;不修改生产 site/、engine;不合并、不推送、不部署。

## 资产分层(本轮核心架构决定)

内页统一迁入 R6 基座,首页 base6 零改动(避免动已验收的首页):

| 文件 | 角色 | 变更 |
|---|---|---|
| tokens6.css | 全站 token | 补 `--paper2`(昼 #E7E4D9 / 夜 #10141C),三块主题各一处 |
| base6.css | 首页版式 | **不动**(零回归) |
| pages6.css | 内页共用版式(新,~430 行) | 导航/印章/行式列表/分页/图签/paper-head/`.prose` 全套/issue-body/空态/订阅条/页脚/reveal/VT 声明序/夹具三件套/reduced |
| site6.js | 全站脚本(233→330 行) | §1–7 原有(守卫式);新增 §8 进度+目录书签、§9 代码复制、§10 图片展开(承 R4 site4.js,反馈色统一朱砂盖印) |

原型阶段 base6/pages6 基础段重复约 80 行——已知债,生产由 Astro 布局消解
(写入接入方案 §2),不在原型层强行去重。

## 逐页要点(每页适合自身用途,不复制大场景)

- **posts**:行式列表(朱砂点+标题位移)+ 分页器 + 文章 RSS 订阅条;下半
  多页节奏夹具保留(标注)。**post-hello**:34em 阅读中心 + 稿纸页头(与
  首页封面卡 VT 共名 latest-cover)+ 书签/进度/复制/展开/落款印;页内
  原有阅读脚本并入 site6.js;specimen 样张框标注"原型演示块,不进生产"。
- **digest**:空态换 blank-sheet 语言(与首页同语言:一页没写的稿纸)+
  日报 RSS 订阅条;列表夹具保留。**digest-2026-10-05**:图签(模型/条目/
  成本两态)+ issue-body(1:1 对齐 assemble.py)+ 变体夹具不变,仅换基座。
- **about**:窄栏+vignette(--paper2)+ 时间线;双 RSS 订阅条;SVG 线稿不动。
- **404**:缺页意象换基座;gate 动画留页内(reduced 下 none)。
- **search-m2**:仅换基座的最小统一;夹具横幅强化为"不实现、不接 API、
  不进正式导航"完整口径;不加入 nav(任务边界)。

## 验证(verify6.py,35/35 PASS;只记实测)

- 矩阵:8 页 × 昼/夜(bg/token 生效、aria-current、无横向溢出、title、
  console 干净);手机 390 六页(布局成立+目录按钮接管)。
- 无 JS 四页:内容/导航可读、html 无 .js;reduced:过渡时长归零
  (dur 解析兼容 1e-05s)、404 动画 none、VT 由 CSS 禁用。
- 文章页 paper-head 挂名 = latest-cover(computed);连续路径:深链文章→
  history.back→首页→文章→日报(展开夹具)→日报详情→关于→404,aria-current
  全程跟随、零 pageerror。
- 键盘 Tab 进导航;WebGL getContext→null:poster 显示、无 canvas、内容在。
- CSS 静态:pages6.css VT 声明序 auto 先于 reduced none(已知陷阱)。
- 回归:a45dc39 两修正的 repro1_queue 8/8、repro2_vtname 8/8、
  regression 6/6 全 PASS(未破坏)。
- 证据截图 shots/r6uni-*(10 张:6 页昼、post/digest 夜、手机 post/digest)。

**未测项(条件缺失,如实标注)**:iOS Safari/真机触摸、Firefox;VT 在
非 Chromium 的实际表现未验证。

## 工具侧事故与修正(联调记录)

- serve.py 单线程 TCPServer 在字体分片并发请求下串行超时→改
  ThreadingTCPServer(8934,no-store)。
- verify6 初版三处假信号修正:title 截断误判(改用全 title)、reduced 断言
  元素选错(post 页无 .copy-link,改 .toc a)、duration "1e-05s" 解析报错
  (dur_sec 兼容 ms/s 与逗号多值)。digest 夹具点击前需先展开 details。
- 承上轮教训:判定一律 JS 硬证据,不用图像分析。

## 交付物

- 原型统一:tokens6/site6 修改,pages6.css 新增,7 个内页换基座,
  map.html R6 区块改"全站"(补 7 行页面索引+资产行),10 张截图。
- [INTEGRATION-PLAN.md](../design/2026-10-07-visual-redesign/INTEGRATION-PLAN.md):
  路由映射(对照 site/src/pages 实核)/资产三层→一层/脚本逐项清单(含关闭
  行为)/3D 策略/字体预算与测量/内容契约逐项表/四批接入与回退。
- [ADR-0010](../decisions/0010-adr0002-client-js-exceptions.md):ADR-0002
  零 JS 条款的四类有限例外(主题切换/阅读增强/首页 3D/VT)+ 共同边界;
  **状态=提议,未生效**。

## 边界与下一步

本轮未动生产 site/、engine;未合并/推送/部署。待裁决:ADR-0010 是否生效、
接入批次时点、three 体积与字体首访预算的接受度、真机/Firefox 补测安排。
