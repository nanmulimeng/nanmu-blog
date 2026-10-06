# M1 开发 Agent 接手交接(2026-10-06)

- **recorded_at**: 2026-10-06 12:04 Asia/Shanghai
- **continues**: [M0 验收交接](2026-10-06-m0-acceptance.md)
- **repository**: 本轮开始 HEAD=f034ddc、分支 main,工作区与暂存区干净;本交接及入口同步为本轮未提交文档修改,未推送。新 Agent 必须重新核对现场,不得清理或覆盖这些改动。
- **objective**: 为用户指定的新开发 AI 准备 M1 开工入口;当前会话只负责审计与交接,不实现 engine。
- **change_scope**: 新增本交接;同步 AGENTS/README/文档索引及 spec/plan 的当前阶段文字。不改设计契约、应用代码、历史验收记录、标签或服务器。

## 开工结论与分工

**M0 已验收,M1 设计与实施计划已通过评审,现在可以正式开始 M1 本地开发。** 不再等待另一轮全面设计审查。用户决定何时启动新开发 AI、控制开发范围;开发 AI 执行已授权任务;审计 AI 审查交付证据与契约一致性,不代替开发 AI 编码或代用户批准发布。

实际进度仍是 **Task 0 尚未开始,根目录 `engine/` 不存在**。已授权范围与实际完成度必须分开记录。

## state 与依据

- 本地 `m0^{commit}`=cb6898a57a499541bc58aa8856aa7ef3a9dfc81f,当前 HEAD=f034ddc [verified: 本轮 git rev-parse/log;不移动 m0 标签]。
- M0 文章发布、RSS、主题、回滚及恢复已由执行 AI 完成 [declared: 用户交付与 M0 验收交接;本轮未重新进行线上操作]。
- 三张 [M0 截图](../evidence/2026-10-06-m0/)已实读:CommaFeed 显示 nanmu blog 与首篇条目;明暗主题截图均有修正后的文章正文 [verified: 本轮本地图片查看;图片不单独证明发布耗时或回滚过程]。
- 根目录 `engine/` 未创建 [verified: 本轮 Test-Path engine=False]。不要把 `docs/engine/` 设计文档当作实现。
- 设计评审通过与恢复实施范围见 [第五轮结论](2026-10-05-m1-plan-review5-passed.md)、[恢复实施指示](2026-10-06-resume-implementation.md);历史轮次仅在追溯具体问题时读取。

## 最短接手路线

1. 读根 [AGENTS.md](../../AGENTS.md)、本文及 [workflow](../development/workflow.md),先核对本轮用户指令、分支、HEAD、工作区、暂存区和标签。不自动重做 M0 验收。
2. 初次接手补读 [项目背景](../context/project-background.md)、[经验教训](../context/lessons.md)、[架构](../architecture.md),明确博客/引擎/个人检索的隔离边界。
3. 读 [M1 plan](../superpowers/plans/2026-10-05-m1-engine-implementation.md) 的全局约束、依赖与 Task 0–12;结合 [coding-standards](../development/coding-standards.md) 和 [quality-gates](../development/quality-gates.md)实施。
4. 规则按任务加载:跨组件约束及 DDL 以 [spec §2/§5/§9](../superpowers/specs/2026-10-02-nanmu-blog-design.md)为准;接口、配置与错误矩阵见 [design](../engine/design.md);采集读 [上游契约](../context/topic-digest-data-source.md)与 [单元一](../engine/units/data-ingestion.md),费用与复用读 [单元二](../engine/units/model-calls.md)和 [budget](../engine/budget.md)。功能语义追溯 [digest-design](../engine/digest-design.md)。

本文仅做导航与进度交接,不复制公式、DDL、重试矩阵或另建规则真相源。个别历史评审措辞不能覆盖已通过的最新阶段结论;实际规则冲突则按 workflow 局部核对,不得静默改契约。

## 首批实施范围与停止位置

| 任务 | 交付目标 |
|------|----------|
| Task 0–4 | 工程初始化、tokenizer 依据与计数、配置、12 表数据库、替身模型客户端 |
| Task 5–8 | 授权预占、持久化重试判定、结算/核清/费用快照、完整请求身份与复用 |
| Task 9–12 | URL 归一、只读采集、entry 与冻结同事务、确定性预筛与完整去向 |

从 Task 0 开始,按 plan 依赖推进;普通任务不逐文件等待审计。公共接口稳定后,计划允许账本侧 5–8 与采集侧 9–12 并行;是否分配多个开发 Agent 由用户与开发安排决定,不强制。

**完成 Task 0–12 后统一交付审计,不自动扩展到 Task 13–24。** 本批不要求日报发布能力已经实现,不得把底层测试通过写成 M1 里程碑通过。

提前停点沿用 plan:Task 1 无法建立计量依据、出现实质契约冲突、或同一修复方向连续两轮无效。提交具体证据、影响和待决定事项;不靠扩大架构或改弱测试消除失败。

## 授权与环境边界

- 本地实施批次已获授权,由用户指定的新开发 AI 接手。普通开发修改、验证与按原计划的小步本地提交遵循 workflow;本交接不新增远程操作许可。接手时若已有未提交文档修改,先核对归属和提交范围,不得混入代码后声称只有本批实现。
- 所有模型调用使用替身;不读取或索取真实 API key,不进行真实校准或付费调用。Task 1 官方资源核查/离线计数与真实 API 校准是不同阶段。
- 本地上游如需读取,仅 `mode=ro`;不修改 topic-digest 代码、数据库、schema 或配置。本批没有服务器 SSH/部署授权,不因“真实上游只读”擅自上服务器。
- `server`/`origin` 的 push、新建或推送 tag、M1 部署、远程清理、真实校准及正常付费运行仍按用户对应范围授权。M0 已用完的发布范围不自动延伸到 M1。
- 不启动 M2/M3,不顺手修 favicon 或改站点功能;这些不属于 Task 0–12。
- 开发机是 Windows;先核对 Python 版本、Git Bash 路径及依赖实际可用性。按工程环境执行测试,不把系统 Python 与计划目标 Python 3.11 混为已验证兼容。工具缺失报告实际缺口。

## 调研事项落点

| 事项 | 处理阶段 |
|------|----------|
| 上游长 RSS 摘要可能未写入 content_text | 本地采集测试覆盖空正文;Task 25 核对线上实际影响,本项目不擅修上游 |
| AIHOT 旧域名迁移 | Task 25 核对源地址、重定向和采集状态,不为 engine 增加抓取功能 |
| tokenizer 与当前 API 模型/完整消息计量对应关系 | Task 1 取得资源依据;后续授权校准取得真实对账证据,没有依据不以字符估算替代 |
| 中文 FTS 召回 | M2 再验证,不阻塞 M1 |

## 首批交付审计所需证据

- 实际完成的 Task 编号、提交范围、工作区状态、未完成项;仅实际完成才勾选 plan。
- 测试环境、工作目录、可复现命令、退出码与摘要。engine 已建后按 quality-gates 跑适用测试;文档运行 check_docs;修改相关代码后重跑受影响检查。
- 重点证据沿用 plan 测试种子:计数缺失拒绝出网;授权先落库;关闭连接重开后重试名额不变;unknown 保留预占;复用不重发;只读不写上游;collect 与 freeze 原子性;候选去向不遗漏。
- 验收测试按契约而不是照抄计划伪代码。示例字段/路径笔误按 spec 和实际消费方校正,不为使示例通过而改 DDL;遇到语义冲突再局部回补设计。
- 一份实施 session,明确零真实付费、未部署的证据边界,以及下一批入口。不要额外创造“审计通过说明的收口说明”等重复交接。

## verification

| 核查 | 本轮结果 |
|------|----------|
| Git 状态/标签/实现目录 | 开始时干净;HEAD=f034ddc;tag m0→cb6898a;engine 未创建 |
| M0 验收记录与三张图片 | 已实读;本轮不重复线上验收,运行结果归原执行记录 |
| 仓库根 `python scripts/check_docs.py` | 通过:73 md/269 local_links/12 表,schema 示例一致,errors/warnings 均空 |
| 仓库根 `git diff --check` | 通过;仅既有 Git LF→CRLF 提示。未修改代码片段,本轮不重跑 snippets/site/engine 测试 |

## disposition 与 next_action

**disposition: complete**(仅本轮交接准备完成)。由用户启动新开发 AI,从 **M1 Task 0** 开始,首批到 Task 12;当前审计会话不接管开发。

## omissions

- M0 发布耗时、服务器回滚和最终线上 SHA 本轮未独立重测;本地证据审阅不冒充线上复验。
- M1 代码、tokenizer 对应关系、费用上界、备份恢复与真实发布尚未运行验收;既有设计结论不替代后续实施证据。
- 本轮文档修改未提交、未推送,新开发 AI 在同一工作区可直接读取;若用户另建 worktree/使用远端副本,应先确认本交接已包含其中,避免拿旧入口开工。
- favicon 404、用户侧 DNS/ICP、origin 推送与验收残留清理均不纳入本批开发。
