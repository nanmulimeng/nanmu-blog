# 日报管线(engine,M1)

> 状态:定稿 2026-10-02(源自 spec §5,M1 实施基准;实施中变更先改本文)。
> 调度:每日 08:30 Asia/Shanghai(systemd timer 无时区后缀——systemd 239 限制,topic-digest 已踩坑)+ RandomizedDelaySec=300 + Persistent=true(missed 补跑一次);flock 单实例。

## 阶段表

| 阶段 | 输入 | 输出 | 失败处理 |
|------|------|------|----------|
| collect | topic-digest SQLite 只读(item JOIN source,近 24-48h) | 候选条目 | 读失败 → digest_issue 记 failed,站点不受影响 |
| 判重 | 候选 URL | entry 表新增(INSERT OR IGNORE,identity_key 归一) | — |
| 预筛 | entry(pending) | 剔除:标题关键词黑名单 / 死源 / 已上过日报 | 本地零成本 |
| 双次评分 | 预筛后条目 | analysis(score_1/score_2) | 预算熔断 → 中止本期;单条失败跳过 |
| 摘要写作 | 入选条目 | 中文标题(答案先行)/一句话/推荐理由/标签 | 单条失败 → 该条剔除,不挂整期 |
| 组装 | 入选 + 摘要 | digest markdown(frontmatter:date/generated/ai_model/entry_count/cost_cny) | — |
| 发布 | markdown | git commit → 构建链 → digest_issue.status=published | git 失败 → status=draft,人工介入 |
| 记账 | 本期 receipts | digest_issue.cost_cny + api_usage 月聚合 | — |

## 数据落点

- `engine.db`(WAL):entry / receipt / budget / analysis / override / digest_issue / api_usage(8 表 DDL 见 spec §5.3)
- `rag.db`(M2):向量,独立库,可随时删除全量重建
- `site/src/content/digest/YYYY-MM-DD.md`:唯一公开产物(git 即发布)

## 失败隔离不变量

1. 单条目失败不挂整期
2. LLM 全挂 → 该期不生成(digest_issue 记 failed),博客照常在线
3. engine 任何崩溃不影响静态站(独立进程独立库)

## 运维

- OnFailure 通知(凭据配在服务器 env,随 M1 部署)
- 巡检与故障处理:见 [../ops/runbook.md](../ops/runbook.md)
