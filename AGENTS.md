# AGENTS.md — nanmu-blog

**一句话**:极简静态博客(手写文章)+ AI 引擎自动日报(读 topic-digest 数据)+ 自用 RAG。博客先上线,AI 是渐进叠加层,**任何一层挂掉博客都在线**。

## 项目状态快照(2026-10-06)

- M0:**全部完成并验收通过(2026-10-06,tag `m0`)**——首篇文章《你好,nanmu-blog》真实发布上线(发布计时12s),线上验收全通过(RSS XML 解析+CommaFeed 真实订阅、明暗主题、文章页/404),持锁回滚演练实操通过(切旧版 c8a4567 确认后切回)。证据见 [M0 验收交接](docs/sessions/2026-10-06-m0-acceptance.md)与 [部署交接](docs/sessions/2026-10-04-m0-deploy.md)
- **当前阶段:校准指纹与 CLI 已通过复核,待用户授权独立真实校准;上游采集待方案 A 的完成识别与时效规则落实,生产日报及 timer 暂不启用(2026-10-07)**——engine 全套件 330 passed。已闭合:快照裸拷撤回(反例验收)、tokenizer 官方件锚定与资源身份核实(系数 1.0 仍由受控真实校准验证,不因模型名机械替换)、校准 CLI(python -m nanmu_engine.calibrate,替身+服务器冒烟)。方案 A 已实现 journal 任务级证据链完成识别+48h时效规则(docs/sessions/2026-10-07-plan-a-snapshot-rules.md),服务器现场验证待做;真实付费调用须用户当次显式授权,本状态不构成。
- 顺序:M1 Task 0-12→Task 13-24(本地替身端到端)→Task 25 部署/Task 26 分两段授权启用付费;进入条件以spec §9为准(M0 验收已满足)
- 执行方式:Native,按任务顺序执行;计划中提及的 skill 若环境没有,以本仓库 workflow 为准,按 [docs/superpowers/plans/2026-10-05-m1-engine-implementation.md](docs/superpowers/plans/2026-10-05-m1-engine-implementation.md) 逐任务
- 最新接手入口:[2026-10-06 M1 审计修复轮+跨模块核验+复核轮](docs/sessions/2026-10-06-m1-audit-fix-round.md)(审计 8 项+交界缝 8 处+复核轮三处修复全记录:账本校准/内容身份运行序/发布恢复/站点产物四组,测试与验收证据);前序:[M1 批次实施](docs/sessions/2026-10-06-m1-batch1-implementation.md)、[M1 开发交接](docs/sessions/2026-10-06-m1-development-handoff.md)。本轮修改/提交/推送状态接手时以 Git 实况核对。

## Agent接手入口

前端设计专项(2026-10-08)：按用户新要求集中完成全站页面、动画与 3D 原型及源资产，允许科技感与更大胆的美术探索。先读 [全站设计任务书](docs/design/2026-10-07-visual-redesign/FULL-SITE-BRIEF.md) 与 [专项交接](docs/sessions/2026-10-08-frontend-creative-research.md)；此为独立原型设计，不代表生产 JS 规则已修订或全站已实施，M1 状态另行核对。

R6 接入进展与当前接手入口(2026-10-09 第七轮):设计基线 **R6 换页碑**(原型入口 [prototypes/r6/index.html](docs/design/2026-10-07-visual-redesign/prototypes/r6/index.html))。**生产接入批次 0–2 及批次 2 定点修正轮均已完成并经用户复核通过**(分支 `codex/r6-interaction`,5aa996e 起仅本地):字体包 + tokens/base + 公共布局 + 全内页 + **首页静态版式与 3D 场景**(72a4c42 验收工具 → a498f05 静态首页 → ffffd6e 3D 接入 → 809cdd8/1e23049 修正轮+收口:手机交接区单格化+失败清理、就绪前主题不丢、日报/站点状态同源接线、排队反例入验收、poster 昼/夜口径校正)。验收:verify 绿 + **verify_browser 78/78**(批次 3 收尾增 P 段:手机交接高度+createScene 失败清理;批次 3 性能轮增 Q 段:首帧 nav 不闪 RED→GREEN;含 WebGL 降级/模块失败/字体挂起+挂起期主题切换/挂名生命周期/排队变向/同源断言)+ **scripts/verify_digest_states.py 三态 3/3**(零期/一期/更新,入库可复跑;批次 3 修复:经 junction 落盘的真实 node_modules/.astro 持久 store 构建后清理,防空源裸构建报「源文件数与加载条目数不一致」)+ measure E1(poster 先于 3D)/E2(3D gzip-6 192.8KiB≤220KB、poster 418.6KiB≤450KiB)+ 证据归档 shots/r6-b2-*;移动端保留 3D 的裁决与依据见 INTEGRATION-PLAN §8;**回退路径已隔离检出实测**(revert 809cdd8→ffffd6e 无冲突,静态首页完整,见 INTEGRATION-PLAN §7)。**批次 3 进行中**:三项收尾已完成;**Lighthouse 测量+CLS 修复已完成**——CLS 0.288 归因于渐进增强 nav 占位塌陷(site.js 加 `.js` 前 main 上移 261px),修复=`.js` 类提前到 head 内联首帧脚本(Base.astro+smoke 签名同步),修后 Lighthouse CLS home 0.001/post 0.005、perf 50/98(devtools 口径),证据归档 logs/r6-b3-*;**兼容验收+现网基线(2026-10-10)亦完成**:Firefox 146.0.1 验收 14/14(verify_browser_firefox.py 入库:内容/导航/主题/3D 正常+暂停/WebGL 禁用降级/reduced-motion)+ Playwright WebKit 26.0 验收 13/13(verify_browser_webkit.py 入库,口径=非真机 Safari)+ 生产 Caddy 现网只读基线归档(logs/r6-b3-caddy-baseline.log);真机(触摸/Safari/帧率)无设备登记待验。**批次 3 修正轮(2026-10-10,用户审计后)已完成**:①手机导航降级回归修复(site.js 请求失败 onerror+初始化失败 try/catch 双路摘 `.js` 回退平铺导航,R 段=首页/内页实际点击跳转+注入 throw,验收 83/83)②夜间主按钮文字对比度 #F7F4EB on #B5432F=5.01:1 达 WCAG AA(保朱砂色相,昼间零变化)③TBT 同节流「正常 3D/静态」对照补证(tbt_probe.py v1 口径经用户审计驳回、结论撤回,同日 v2 重写重测:Event Timing+归档配置对齐+async 并发派发+仪器自检 6/6——场景构建长任务窗口内点击排队 163–409ms、窗口外中位 2–5ms vs 静态组无长任务无排队,**取舍待用户裁决见 INTEGRATION-PLAN §5 P2-v2/§8**,未动 3D)④Lighthouse DSF 勘误(实值 1.75)+修后机器可读摘录入库。**TBT 重测轮(2026-10-10,7423552)已完成并通过用户审计**:Event Timing 探针 v2(async 并发派发+归档配置逐项对齐+仪器自检),实测场景构建长任务窗口内点击排队 163–409ms、输入到绘制最长 448ms,六类数字分别报告(INTEGRATION-PLAN §5 P2-v2)。**B 方案初始化优化轮(2026-10-13)已完成**:用户裁决执行 B——mark 插桩分阶段测量归因三条长任务(resize 内联首绘 284ms 重复劳动/三张纹理连画 390ms/换贴后集中上传 221ms;采样剖析法在 4× 节流下轴失真弃用)→ scene6 三处局部优化(首绘去重+compile 独立段+纹理逐张分帧让出,+26/−6;host opacity=0 期间多出的帧不可见、终态截图一致,纹理逐张出字为过程态变化)→ tbt3 对照(两处口径前后有变:gzip 判定/观察窗):最长连续任务 446→**155ms**、长任务窗口内点击 overlap 2 发(409ms)→**0 发**(六窗内输入响应无直接样本)、输入到绘制最长 448→**40ms**(39 个配对样本最大值,7 个未配对不计 0;200ms=建议优化目标非发布硬门槛)、inputDelay max 11ms、poster 退场较基线晚 0.8s(观察差值,不作因果归因);同批三处测量口径修正(首页 gzip 判定/static Lighthouse 标未测/统一 20s 观察窗);回归 verify_browser **83/83**+verify 绿(INTEGRATION-PLAN §5 P2-v3/§8 裁决行)。**发布候选收口批(2026-10-13)已完成**:①性能结论收窄(六窗内输入响应仍未直接覆盖/7 个未配对样本分列/poster 退场 +0.8s 为观察差值;勘误随新提交入库,旧提交 d226a26 不改写)②分段初始化过程态验收 **38/38**(S1 字体快就绪×4 变体交错无异常/S2 woff2 单延迟:素纸期 5.9–12.8s 可见+逐张出字混合帧+暂停 resize 契约/S3 注入失败 poster 常显+host 清理;未发现回归,未为测试形式改产品代码)③前端指导文档定点对齐(AGENTS 摘要与禁止事项引 ADR-0010 例外;coding-standards 四入口白名单+tokens/base/home 三层样式;ADR-0010 实施状态/例外 3 生产入口/预算归属/生产强制点)④候选交付包(候选=**d226a26**;verify 绿+Chromium 83/83+Firefox 14/14+WebKit 13/13(后两者 d226a26 后首次)+E1/E2 复测 3D 193.5 KiB;恢复方式候选上实测——服务器切版(分钟级)+Git revert 链 d226a26→809cdd8→ffffd6e 唯一冲突 smoke.mjs 已解、回退态 verify 绿+冒烟 4/4,旧「两笔无冲突」结论不适用候选;授权动作三步与线上验收清单成文)——**R6 已发布上线(2026-10-13,用户授权)**:候选经两轮勘误至 **9120bf3**,ff 合并 main、推 origin、`git push server main` 触发 hook 构建,线上 release=9120bf3(34s 达标),旧版回滚目标 734c47f 已预核仍在保留窗口;线上验收等效 13/13(真机触摸/Safari/帧率仍登记待验),SHA 清单与过程见 [发布 session](docs/sessions/2026-10-13-r6-release.md);接手先读 [发布 session] 与 [发布候选 session](docs/sessions/2026-10-13-r6-release-candidate.md)与 [B 优化 session](docs/sessions/2026-10-13-r6-b3-initopt.md)(2026-10-13:分阶段测量+三处优化+前后对照+口径修正+勘误)与 [TBT 重测 session](docs/sessions/2026-10-10-r6-batch03-tbt-remeasure.md)、[修正轮 session](docs/sessions/2026-10-10-r6-batch03-fixround.md)、[INTEGRATION-PLAN](docs/design/2026-10-07-visual-redesign/INTEGRATION-PLAN.md) §5/§7/§8;前序:[兼容验收 session](docs/sessions/2026-10-10-r6-batch03-compat.md)、[批次 3 第一部分 session](docs/sessions/2026-10-09-r6-batch03-perf.md)、[修正轮 session](docs/sessions/2026-10-09-r6-batch02-fixes.md)、[批次 2 接入 session](docs/sessions/2026-10-09-r6-batch02-3d.md)、[批次 0–1 接入 session](docs/sessions/2026-10-09-r6-batch01-integration.md)、[审计收口 session](docs/sessions/2026-10-09-r6-budget-audit-fix.md)。原型侧前序:[R6 全站统一 session](docs/sessions/2026-10-09-r6-site-unification.md)、[交接收口](docs/sessions/2026-10-09-r6-handoff-fixes.md)、[R6 交互轮](docs/sessions/2026-10-09-r6-interaction-round.md)。已关闭事项不重开。

批次 C 上线修正轮(2026-10-20)接手入口:用户真实使用反馈四项全完成——①hero 左列结构锚定修复竖排标题与目录块全视口重叠(根因=bottom:250px 硬编码预留与面板实际高度脱钩,ef78ab5)②真撤下《你好,nanmu-blog》+零文章空态(消费方全同步:源删除/RSS/路由/首页/3D/关于,git 历史保留,ff3fa0e)③公开文案回到个人博客定位(去烂尾经历/开发周数/部署链路/借鉴说明/占位,c3aa570)④文章管理工作台最小设计(**仅设计不实现**,d9db3c2)。**随后定点修正轮(2026-10-20)已完成**:①生产 poster 重拍中性主视觉清除被撤文章残留(poster-stack-* 换名缓存失效+scene6 纹理通用化+FIXED_SAMPLE 对账脚本入 verify,f9c9e3e)②日报状态文案从内容数据派生,全站去「每日一期」(6709365)③布局验收补页签 resize+非空文章夹具+session「CDN 归档」勘误(5b34dd5)④工作台设计 B1–B5 补齐(仅设计,Git 身份/保存契约/发布七态/预览边界/运行时,5c198fb)。本地 main 在此之上,**origin/server 均未推送,线上仍 9120bf3(撤稿前版,含被撤文章),发布待用户授权**;⚠️回滚到批次 C 前版本会重新公开被撤文章。详见 [定点修正 session](docs/sessions/2026-10-20-c3-pre-release-fixes.md)、[批次 C session](docs/sessions/2026-10-20-c3-live-fixes-withdraw-copy.md) 与 [工作台 DESIGN](docs/design/2026-10-20-writing-workbench/DESIGN.md)。

1. 读本文与上方最新交接,先明确**本轮用户目标**。交接中的下一步不是自动执行授权。
2. 按 [workflow](docs/development/workflow.md) 核对工作区、暂存区、分支与提交;保留已有修改,不要先清理工作区。
3. 初次进入补读 [项目背景](docs/context/project-background.md)(两个自有前项目与外部借鉴)、[经验教训](docs/context/lessons.md)及 [spec](docs/superpowers/specs/2026-10-02-nanmu-blog-design.md) 总体边界。继续会话只读本次影响的章节。
4. 读取当前任务的 plan 与实际文件;写代码前读 [coding-standards](docs/development/coding-standards.md),选择验证看 [quality-gates](docs/development/quality-gates.md)。未创建的应用不能当作现成功能。
5. 部署补读 [环境](docs/context/server-environment.md)与 [部署手册](docs/ops/deploy.md);M1补读 [上游契约](docs/context/topic-digest-data-source.md)。其余按需从 [文档索引](docs/README.md)查找。

本文保留入口与关键边界;会话动作由workflow维护,编码约束由coding-standards维护,验收条件由quality-gates维护。发现冲突先核对真相源与实际证据,不要复制另一套规则。

## 八条铁律摘要(完整定义以spec §2为准,修改先改spec)

1. **范围是生死线**:每个里程碑必须独立可发布,不欠债进下一个(nanmuli-blog 12.5 周烂尾的头号教训)
2. **博客本体永远不为 AI 功能加复杂度**:AI 挂了博客照常在线
3. **AI 引擎独立进程独立数据库**:engine 崩溃不影响博客,反之亦然
4. **topic-digest 保持现状不动**:本项目只读它的 SQLite(同机文件只读,`mode=ro`)
5. **付费请求先记回执再消费 + 三级次数限制与月/期金额预占**,全部付费LLM/embedding月预算红线 **¥50**
6. **页面永不调模型**:读者打开页面只读预生成内容
7. **AI 生成内容必须标注**:digest 栏目注明 AI 生成、模型与成本,与个人文章视觉区分
8. **文档随代码走**:设计变更先改文档;修改型会话结束写交接记录,只读讨论不强制写盘

## 项目结构

```
scripts/   已有文档检查工具
site/      Astro 5 静态站已建(M0 Task 2-8+8a;posts 手写 + digest 生成)
engine/    AI 引擎已建(M1 Task 0-24,Python + SQLite + systemd timer;src/nanmu_engine + tests,330 测试;服务器已部署 /opt/nanmu-blog,timer 未启用)
docs/      specs/plans/decisions/engine/ops/sessions/context
deploy/    服务器部署工件(已安装并在 Task 9 验收;线上 https://nanmu.xyz)
```

## 常用命令

仓库根:`python scripts/check_docs.py`检查文档;修改计划中的代码片段时加`--snippets`(需要Node与Git Bash)。

site/下(已创建,verify自Task7起可用):

- `npm run dev` 本地开发
- `npm run build` 构建
- `npm run verify` build + 冒烟检查 + 夹具临时构建验证;从Task7起用于site验证,此前用build。工作目录与各类任务要求见quality-gates

engine/下(M1 已建):

- `python -m pytest tests -q` 全套件(engine 目录内执行;替身模型+本地 bare repo,零真实网络)

## 开发流程

详见 [docs/development/workflow.md](docs/development/workflow.md)(会话开始 live_state 核对 / 任务执行 / 提交规范 / 会话结束交接)。要点:

- 会话开始:当前目标 → 最新session → Git/文件核对 → 适用基线验证。已有失败先区分原因,不顺手修无关问题
- commit前通过当前阶段适用验证;暂存/提交/推送分别核对范围与授权,不混入已有改动
- 修改型会话结束写 `docs/sessions/` 交接记录;只读审查不强制写盘——**硬性步骤,被中断也要写 continuable**
- 编码规范:[docs/development/coding-standards.md](docs/development/coding-standards.md)(客户端 JS 按 ADR-0010 白名单 / 依赖白名单 / engine 目录结构 / 密钥只走环境变量)
- 设计/决策变更:先改 spec 或新增 ADR(模板 `docs/decisions/_template.md`),再改代码

## 禁止事项

- ❌ 不改 topic-digest 的任何东西(铁律 4)
- ❌ 密码/密钥不落盘:服务器密码只在交互输入,API key 只进服务器 env(铁律与凭据政策)
- ❌ 不在页面/构建里调 LLM(铁律 6)
- ❌ 不给博客本体加数据库、后台;客户端 JS 仅限 ADR-0010 白名单四类例外(全站 site.js+内联首帧/首页 home.js+boot6,ADR-0002 其余条目不变)
- ❌ 不跳过当前阶段适用验证提交;禁止故意将坏内容提交到生产 main
- ❌ 不把过期文档当执行依据——修改任务内修正相关指南;只读审查报告偏差。历史session保留,不为“更新”改写旧证据
- ❌ M3 想法(周报/热度/事件聚簇等)只记录不动工,见 spec §9

## 环境速查(详见 server-environment.md)

- 服务器 123.56.223.97(Alinux 3,systemd **239**历史记录;timer暂沿用本机裸时间策略,版本/时区/解析在部署时复核,1.8G内存)
- 80/443 归 Caddy;服务器上有 topic-digest(8080)与 nanmu-skill-mcp(3456,**勿动**)
- 开发机 Windows 11 + Git Bash;shell 脚本必须 LF(.gitattributes 已强制)
