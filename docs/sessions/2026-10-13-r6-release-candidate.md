# 会话交接:R6 发布候选收口与发布准备(2026-10-13)

- **recorded_at**: 2026-10-13 14:50 Asia/Shanghai
- **continues**: [B 优化 session](2026-10-13-r6-b3-initopt.md)(d226a26)
- **repository**: 起点 HEAD = d226a26;分支 `codex/r6-interaction`(仅本地)。候选 = **d226a26**(本批为文档/验收层,不改产品代码,最终提交见 Git 实况)
- **objective**: 用户 00c9 指令四项:①收窄性能结论关闭测量争议 ②分段初始化过程态定点验收(三场景,复用既有工具不建框架;发现回归最小修复,未发现不为测试形式改代码)③定点对齐前端指导文档(AGENTS 摘要引 ADR-0010 例外/ADR-0010 与生产入口对齐/coding-standards 删 global.css 失效指引;不开全仓文档重审)④形成发布候选交付包(验证/预算复测/恢复方式核对/授权动作清单/线上验收清单)。边界:不合并、不推送、不部署,不动 engine/上游/付费配置/timer;完成后交审计由用户决定发布

## 任务 1:性能结论收窄(五处编辑,旧提交 d226a26 不改写)

按用户逐字口径统一:**「最长连续任务由 446ms 降至 155ms;39 个成功配对的点击样本最大输入到绘制为 40ms;7 个未配对样本不计为 0;六个长任务窗口内的输入响应仍未直接覆盖。」**;删「最长任务+一帧=理论最坏响应」推算与「加载窗口全部达标」;200ms 保持建议优化目标不升发布硬门槛;poster +0.8s 改观察差值不作因果归因(前后 gzip 判定/观察窗口两处口径变化已标);「零视觉变化」改证据边界表述(host opacity=0 期间不可见+终态截图一致;纹理逐张出字是过程态变化)。落点:INTEGRATION-PLAN §5 P2-v3/§7 3d 行/§8 裁决行/状态行、AGENTS.md 第七轮段、[B 优化 session](2026-10-13-r6-b3-initopt.md) 五处+文末新增勘误节 5 条(勘误随本批新提交入库)。

## 任务 2:分段初始化过程态定点验收(38/38,未发现回归→未改产品代码)

工具:C:\tmp\r6rc-init.py(一次性,不入库;复用 verify_browser.find_chrome+tbt_probe.serve_gzip;CPU 4× CDP 节流;端口 8961)。完整日志入库 logs/r6rc-init-process.log,过程帧 shots/r6rc-init-*(终态截图不代替过程验收)。

### S1 字体快就绪/暖缓存(4 变体 19 项全过)

fast-dark-tab(初始 dark+就绪前点页签)/fast-light/reduced-motion(场景+HUD)/warm-2nd-visit(同 context 二访)。poster 退场 1.7–2.2s、tris=4351、host opacity=1、初始 dark 保持(themeDark=True+html=dark)、就绪前页签 cur=tab=digest、reduced 有 HUD、全部零 console error/pageerror——纹理回调与 createScene 交错无初始化异常。

### S2 字体延迟→poster 3.5s 超时接替(12 项全过,过程帧已归档)

- **场景构造(两轮迭代后才正确)**:只延迟 `*.woff2`(12s),**不延迟 fonts.css**。机理(首轮 12s 双延迟实测发现):fonts.css 挂起会阻塞 module 脚本执行(等 CSSOM)→整条 3D 链顺延、且 createScene resolve 时字体已到、texReady 分支必先赢——素纸期不可见(首轮 poster>17.5s 未退场+唯一帧 hostOp=None,系**测试场景构造问题非产品缺陷**;guard 语义「字体挂起不致 poster 永不退场」仍成立)。woff2 单延迟复现批次 2 字体挂起验收的真实路径。
- **时间线(终轮)**:guard 兑现 t_plain=5.9s(createScene ~2.4s+3.5s)< fonts 到达 12.8s → **素纸期 5.9–12.8s 可见(17 帧字节稳定 ~43KB)** → 12.8s 字体到达 → 逐张出字(13.5s 捕到前景页有字+后面素纸的混合帧)→ 终态 tris=4351/posters=0。录屏轮独立同路径复现(t_plain=5.54s)。
- **视检(5 关键帧,analyze_image 远程 URL——本环境 Read PNG 仅回 CDN 链接)**:poster 期(f05.4)→素纸期(f09.7:三张纸页全无字、暖米色底=rgb(240,237,229) 与主题断言一致、无白闪)→混合态(f13.5:前景「你好,nanmu-blog」+正文已上、后面纸页仍素纸=逐张出字坐实、无残缺/错位)→终态(f18.8:全字清晰、构图与既有验收一致)。四项检查(白闪/错误主题/明显跳变/可见半成品)均未见异常。
- **契约**:暂停 ambientOn=False、暂停态 resize 画布跟随(canvas=390=host)、恢复动态、主题恒定 ['sys','rgb(240,237,229)']、零 console error。
- 归档:shots/r6rc-init-s2-{poster,plain,mid,final}.png + r6rc-init-s2-timeline.webm(同条件独立录屏轮)。
- **测试侧发现(记录,不影响产品)**:①Playwright `page.screenshot` 在字体未就绪时前置等待挂起(实测首张耗 ~9.5s≈字体到达+渲染完成,素纸期实时截不到)→换 CDP 原生 `Page.captureScreenshot` 解决;②ffmpeg 本机不可用,过程证据以时间轴帧为主、webm 兜底;③favicon.ico 404=dist 无该文件+HTML 无 rel=icon 的浏览器默认请求(M0 起既有状态,仅每实例首个 context 报一次),**登记不修**(线上验收清单可选项)。

### S3 分段初始化中途受控失败(7 项全过)

route 层改写 scene6.js 在 `renderer.compile(scene, camera);` 后注入 throw(仅本地隔离验证,故障代码不提交):poster 常显(posters=2)、半成品 host 清理(hosts=0)、no-webgl 终态+has-scene 移除、阅读入口 /posts/hello-nanmu-blog/ 保留、目录展开 nav display=flex、页签面板仍切换、预期 warn 一次(rc-injected-compile)且零 error/pageerror。截图 shots/r6rc-init-s3-fallback.png。

## 任务 3:前端指导文档定点对齐(六个文件位点)

- **AGENTS.md**:编码规范摘要「零客户端 JS」→「客户端 JS 按 ADR-0010 白名单」;禁止事项「不加客户端 JS(ADR-0002)」→「客户端 JS 仅限 ADR-0010 白名单四类例外(全站 site.js+内联首帧/首页 home.js+boot6,ADR-0002 其余条目不变)」。
- **coding-standards.md**:白名单段补 home.js/boot6.js(仅 index.astro,smoke 按页面范围限定);样式指引删失效的 global.css(已于 C5 e91d7c5 删除),改 tokens.css/base.css/home.css 三层职责。
- **ADR-0010**:实施状态更新(批次 0–2+修正+优化全部落地,本地未合并);例外 3 补生产入口三文件(boot6 type=module/scene6+three 运行时动态 import 不经 HTML/home.js defer 页面侧);预算归属写清(home.js 计 8KB 线首页专属口径、3D=四件 gzip-6 ≤220KB 实测 192.8→**193.5 KiB**(本批复测)/poster ≤450KB);生产强制点补 home.js/boot6.js 页面范围限定+scene6/three 不属 HTML 白名单。smoke.mjs 实际白名单已核对,与修订后文书一致。
- 未做(按边界):全仓文档重审、engine/运维文档。

## 任务 4:发布候选交付包

### 验证矩阵(候选 d226a26,本批实测)

| 项 | 结果 |
|---|---|
| npm run verify(build+smoke+夹具) | 绿(6 页构建) |
| verify_browser.py(Chromium 156.0.8078.4) | **83/83** |
| verify_browser_firefox.py(Firefox 146.0.1,**d226a26 后首次**) | **14/14** |
| verify_browser_webkit.py(Playwright WebKit 26.0,**d226a26 后首次**,口径=非真机 Safari) | **13/13** |
| E1 poster 先于 3D | ✓(poster #4 → boot6 #6 → scene6/three #30–32) |
| E2 3D 四件 gzip-6 | **198180 B(193.5 KiB)≤ 220KB ✓**(scene6 14602 B,较优化前 +0.7 KiB=分帧让出代价) |
| E2 poster 两张 | 428676 B(418.6 KiB)≤ 450KiB ✓(昼首访单张) |
| 过程态三场景 | **38/38**(见任务 2) |

字体方案无变化,未重开字体优化;纯文档编辑发生在验证之后,未机械重跑浏览器验收。

### 恢复方式核对(实测,区分两条路径)

1. **服务器切回上一完整版本**(部署层,分钟级紧急恢复):M0 部署已有持锁回滚实操演练(切旧版 c8a4567 确认后切回)。本次发布后若整站异常,同法切回发布前归档的产物目录——**不依赖 Git,先于一切代码层操作**。发布部署时先归档当版目录即获得该能力。
2. **Git 撤销 3D 实现**(代码层;旧「revert 两个 3D 提交无冲突」结论系自 1e23049 实测,**不适用候选 d226a26**,本批在隔离 worktree 重测):自 d226a26 起 **revert d226a26 → revert 809cdd8 → revert ffffd6e**(后进先出三笔);**唯一冲突 smoke.mjs**(ae4c7be 的 js 类内联签名与 ffffd6e 白名单同区域),解法固定=保留批次 3 内联签名(不在撤销链)、去 boot6 白名单、home.js 保留(属 a498f05 静态首页)。回退态实测:npm run verify 绿 + 浏览器冒烟 4/4(logs/r6rc-revert-smoke.log;poster 独撑=预期终态——poster 两张系静态首页资产、零 3D 引擎请求、hero/页签完整、文章页可用)。**副作用须知**:revert d226a26 连带撤销 tbt_probe 口径修正与 B 优化文档/截图,回退态性能=tbt2 基线(446ms 长任务/448ms 输入到绘制,已知数据)。
3. 中间档(记录不实施):C「移动端仅 poster」备选仍保留(§8),若真机帧率不达标再议。

### 后续授权动作(待用户逐项明确授权,本文档不构成)

1. **远端保存开发分支**:推 `codex/r6-interaction` 至 GitHub origin——目标=候选与全部过程证据异地留存(本批后分支含 R6 全部 20+ 提交),范围=仅此分支,不动 main。
2. **合并 main**:本地 merge `codex/r6-interaction` → main——目标=形成可部署主线;范围=站点与文档,engine/上游零变更;合并后 npm run verify 复跑一次。
3. **部署**:按 [部署手册](../ops/deploy.md) 同步 dist 至服务器并切版——目标=线上生效;范围=博客静态站(Caddy 80/443 归属不变);**部署前归档服务器当版目录**(恢复路径 1 的前提);engine/timer/付费配置不碰。

### 线上验收清单(部署后执行)

- [ ] release SHA 记录(合并后 main 的提交)
- [ ] 首页:3D 场景就绪/页签联动/暂停按钮;昼夜主题切换+刷新保持
- [ ] 文章页 /posts/hello-nanmu-blog/:正文/目录/阅读增强(进度条/代码复制)
- [ ] 日报 /digest/:当前为空态(在线状态同源);RSS 两端点(/rss.xml、/digest.xml)拉取解析
- [ ] 真实 404(乱路径):极简页不泄露条目
- [ ] 关键资源:fonts.css/woff2 分片/3D 四件/poster 经 Caddy 实际传输压缩与缓存头(与本地 gzip-6 口径对照,现网旧版基线见 logs/r6-b3-caddy-baseline.log)
- [ ] 主题与 3D 降级:WebGL 关闭浏览器(或真机低端)poster 常显可读;reduced-motion 静态完成态
- [ ] 可选:补 favicon.ico 消除浏览器默认 404(既有状态,非本批回归)

### 未测边界(如实登记)

真机(触摸/Safari iOS/帧率)无设备,登记待验不以模拟代替(沿批次 3b 口径);线上 Caddy 对 R6 候选实际传输(woff2/fonts.css/3D)未验证,部署后按清单第 6 项执行。

- **change_scope**:
  - `AGENTS.md`:第七轮段 B 优化轮句收窄+编码规范摘要与禁止事项引 ADR-0010 例外+第七轮段补发布候选批入口
  - `docs/design/2026-10-07-visual-redesign/INTEGRATION-PLAN.md`:§5 P2-v3/§7 3d 行与状态行收窄;§5 过程态验收结果补记;§7 增 3e 行;§8 增发布候选状态
  - `docs/sessions/2026-10-13-r6-b3-initopt.md`:五处收窄+勘误节(旧提交不改写)
  - `docs/development/coding-standards.md`:白名单段四入口+样式三层指引
  - `docs/decisions/0010-adr0002-client-js-exceptions.md`:实施状态/例外 3 入口/预算归属/生产强制点四处对齐
  - `docs/design/2026-10-07-visual-redesign/logs/`:r6rc-init-process.log、r6rc-revert-smoke.log
  - `docs/design/2026-10-07-visual-redesign/shots/`:r6rc-init-s2-{poster,plain,mid,final}.png、r6rc-init-s2-timeline.webm(替换首轮不充分版本)、r6rc-init-s3-fallback.png
  - `docs/sessions/2026-10-13-r6-release-candidate.md`:本文档
  - 外部操作:未执行(无推送/合并/部署/付费/服务器访问);C:/tmp 一次性工具(r6rc-init.py/r6rc-404.py/rc-revert-smoke.py)与帧序列不入库;回退实测在 C:\tmp\rc-revert-test worktree 隔离完成并已清理(git worktree remove --force,node_modules 独立安装未污染主仓)

- **verification**:

| 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
|---|---|---|
| site/ | `npm run verify` | 绿(6 页+smoke+夹具) |
| site/ | `python -I scripts/verify_browser.py` | **83/83**(Chromium 156.0.8078.4) |
| site/ | `python -I scripts/verify_browser_firefox.py` | **14/14**(146.0.1,d226a26 后首次) |
| site/ | `python -I scripts/verify_browser_webkit.py` | **13/13**(26.0,非真机 Safari 口径) |
| site/ | `python -I scripts/measure_budget.py` | E1 ✓;E2 193.5 KiB/418.6 KiB ✓ |
| C:/tmp(8961 gzip-6+4×CPU) | `python -I r6rc-init.py` | **38/38**;logs/r6rc-init-process.log |
| C:\tmp\rc-revert-test(隔离 worktree@d226a26) | `git revert`×3 + `npm run verify` + `python -I rc-revert-smoke.py` | smoke.mjs 一处冲突已解;回退态 verify 绿+冒烟 4/4(logs/r6rc-revert-smoke.log) |
| 仓库根 | `python scripts/check_docs.py` | 提交前跑,见 Git 实况 |

- **pending_runtime**: C:/tmp 一次性工具与 s2frames 帧序列(不入库);本地 8961/8963 服务随进程退出已停
- **decisions_needed**: 发布授权三步(远端分支保存/合并 main/部署)逐项待用户明确授权(本文档不构成)
- **disposition**: complete(四项指令全部交付;过程态验收未发现回归,未为测试形式改产品代码;恢复方式在候选上实测重证)
- **next_action**: 用户审计;若接受按「后续授权动作」逐项授权;部署后执行线上验收清单
- **omissions**:
  - S2 素纸期中间帧的「逐张出字」混合态仅捕到一帧(f13.5,前景有字+后面素纸)——采样密度受 CDP 截图 ~0.15s/张物理限制,三段逐张(单段 <160ms)在同帧完成的部分无帧证据,以 webm 录屏兜底
  - Playwright screenshot 字体等待挂起系行为观察(未深究内部实现),已绕开;若未来工具链升级需复验
  - 真机(触摸/Safari/帧率)仍无设备登记待验;线上 Caddy 实际传输/缓存待部署后验证
  - favicon.ico 缺失登记为既有观察项未修(可选补齐入线上清单)
