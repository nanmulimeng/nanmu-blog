# 文档系统全量复审(第二轮,2026-10-04)

> 范围:2026-10-02 首轮审查(docs/reviews/2026-10-02-documentation-audit.md)之后新增/变更的全部活文档,叠加 Task 8a/Task 9 两轮实施带来的状态变更。触发:2026-10-04 用户指示回到文档完善阶段,并指出此前入口状态漏同步(AGENTS/README/索引/writing 四入口已先行校准,提交 `3a021d5`)。
> 方法:逐份实读入口与 context/development/engine/ops 文档;spec/plan 采信号词扫描(子域名/待部署/尚未/上线前等)加关键节抽读;历史 session/ADR 只查"是否被误引为现状",不改写。

## 结论

骨架健康:真相源分工(docs/README §真相源表)、声明分级(verified/declared)、索引路由、模板纪律均成立且被遵守。**系统性风险只有一个:实施类会话收口时的"状态同步"靠人工记忆,漏面已成规律**——Task 9 收口同步了 7 份文档却漏了 AGENTS 快照、README 状态段、索引状态列、writing 状态行、server-environment 回填(L4 门禁明确要求)五处。已在本轮将同步清单固化进 workflow(见下)。

> **结论范围勘误(2026-10-04 用户指出,同日补)**:本复审的检查目标是**状态一致性与事实准确性**(链接、口径、声明分级、实测回填),它不覆盖**开发准备度**——状态准确、DDL 能执行,与功能设计完整是不同的检查目标。本轮"骨架健康"仅指前者成立;模块级开发准备度由[设计评审规范](../development/design-review.md)另行判定,其缺口清单(期生命周期、模块数据交接、恢复存储映射、人工干预流程、摘要边界、模块验收)见该文档。原文其余内容不受影响。

## 发现与处置

### A. 状态漂移(全部修复)

| # | 位置 | 问题 | 处置 |
|---|------|------|------|
| A1 | AGENTS.md 快照/项目结构、README.md 状态段×3、docs/README.md 索引列×3+路由×2、writing.md 状态行 | 停留在"待 Task9-10" | 提交 `3a021d5` 校准,并固化"文档完善阶段"指示 |
| A2 | spec 状态行 | "Task 9-10 待做" | 更新为 Task1-9 已验收+文档阶段指示 |
| A3 | glossary M0 词条 | "子域名" | 改 apex 并注日期 |
| A4 | spec §1.2/§9 里程碑表 | "子域名走 Caddy" | 改 apex |
| A5 | spec §6.4 M2 路径 | "blog 站块" | 改"apex 站块"(与已改的 §7 示例一致) |
| A6 | spec §11 勾选项 | "子域名免单独备案"依据随 apex 决策失效 | 保留 [x] 历史,加勘误括注(备案未核实挂账) |

### B. 事实欠账(全部补齐)

| # | 位置 | 问题 | 处置 |
|---|------|------|------|
| B1 | server-environment.md | Task 9 服务器事实未回填(L4 门禁要求但收口漏做);内存/磁盘/时区仍 [declared];node 节仍"当前版本[declared]""工件尚未安装" | 全部摘帽为 2026-10-04 [verified] 实测;新增"nanmu-blog 服务器布局"节(bare repo/缓存/发布根/验收目标);"服务器 node"节改写为"服务器构建链" |
| B2 | server-environment.md 在跑服务表 | skills.nanmu.xyz DNS 消失事件未记录 | nanmu-skill-mcp 行补事件、现状与恢复动作;网络节备案口径改"已上线但备案未核实,显式挂账" |
| B3 | server-environment.md §M0/M1核查 | M0 核查项已全部执行但仍列为"部署前" | 收缩为"M0 已执行完毕";M1 项保留 |

### C. 经验沉淀(按"踩新坑时追加"口径)

- lessons.md SSH 行:补 2026-10-04 实测结论——直连失败疑似根因即"密钥非默认身份名",SSH 别名+IdentitiesOnly 解决;topic-digest 当年大概率同一原因。
- lessons.md 通用表新增一行:DNS 记录可无本机操作而消失(skills 实录);多解析器交叉定位后再归因,恢复只在 DNS 控制台。
- spec §10 风险表"域名/DNS 异常"行补同实录。

### D. 零修改(审查通过)

CLAUDE.md(极简入口无状态副本)、development/quality-gates、development/coding-standards、context/topic-digest-data-source(诚实标注"上一会话转述待复核")、engine/design、engine/pipeline、engine/selection、engine/budget(M1 契约层不携带 M0 阶段状态)、docs/README 文档纪律与真相源表本身。

## 结构改进:状态同步清单(已并入 workflow)

实施/部署类会话收口时,除既有步骤外按下表逐项过一遍(读回核对,不凭记忆):

1. 根 README.md 当前状态段 · 2. AGENTS.md 状态快照+项目结构 · 3. docs/README.md 索引状态列+按目标路由 · 4. spec 状态行 · 5. plan 执行状态行 · 6. 涉事文档自身头部状态行(writing/engine/ops 等) · 7. server-environment.md 按 L4 回填实测事实([declared] 摘帽) · 8. 新 session 的 next_action 与上述入口一致

## 边界(本轮未做)

- ADR 0001-0009 与 reviews/2026-10-02 未逐字复读(仅信号词扫描无命中);ADR-0007/0009 与 Task 9 实际执行的一致性未逐条核对——ADR 是决策记录不携带进度,风险低,留下一轮。
- project-background.md 只扫描未读全文(纯背景文档,无状态字段)。
- spec(约 490 行)/plan(约 1050 行)为信号词扫描+抽读,非逐行;M1 计划未编写(用户圈定为复审优先,编写与否待指示)。
- skills.nanmu.xyz DNS 恢复、ICP 备案核实、origin 推送、验收目录清理均为用户侧待办,不在文档轮处置范围。
