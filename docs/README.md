# 文档索引

**新读者路线**:AGENTS.md(仓库根)→ context/(背景与环境)→ specs/ → 当前 plan → sessions/ 最新记录。

| 文档 | 内容 | 状态 |
|------|------|------|
| [context/project-background.md](context/project-background.md) | 三个前项目的完整故事:为什么存在、继承什么、拒绝什么 | 定稿 |
| [context/server-environment.md](context/server-environment.md) | 服务器/开发机环境事实(部署排障必读,含 [declared] 分级) | 随巡检更新 |
| [context/topic-digest-data-source.md](context/topic-digest-data-source.md) | 上游数据源实况:schema 契约/15 源清单/已知坑 | 定稿(M1 前复核) |
| [superpowers/specs/2026-10-02-nanmu-blog-design.md](superpowers/specs/2026-10-02-nanmu-blog-design.md) | 设计文档(唯一设计真相源,§2 八条铁律) | 定稿 |
| [superpowers/plans/2026-10-02-m0-blog-launch.md](superpowers/plans/2026-10-02-m0-blog-launch.md) | M0 实施计划(10 任务) | 待执行(Task 1 已完成) |
| [architecture.md](architecture.md) | 三件套架构与数据流 | 定稿 |
| [decisions/](decisions/) | ADR 架构决策记录(0001-0008;模板 `_template.md`) | 持续追加 |
| [engine/pipeline.md](engine/pipeline.md) | 日报管线各阶段说明 | 定稿(M1 实施基准) |
| [engine/selection.md](engine/selection.md) | 精选标准/门槛/调整记录(编辑策略) | 定稿(随运营调整) |
| [engine/budget.md](engine/budget.md) | 成本治理与月度成本台账 | 定稿(台账按月追加) |
| [ops/deploy.md](ops/deploy.md) | 部署 runbook(逐字可执行) | 随 M0 Task 8 落盘 |
| [ops/runbook.md](ops/runbook.md) | 巡检/回滚/故障处理 | 定稿 |
| [sessions/](sessions/) | 开发会话交接记录(模板 `_template.md`;最新一份 = 当前进度) | 每会话一份 |

## 文档纪律

- 设计变更先改 spec/ADR 再改代码
- 过期文档宁可删除,不留误导
- 交付文档是终态,不引用草稿/评审轮次/被否决的决策
