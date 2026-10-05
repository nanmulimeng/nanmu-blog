# 日报管线(engine,M1)

> 状态:定稿 2026-10-02(源自 spec §5,M1 实施基准;跨组件契约先改spec,再同步本文)。
> 模块契约、配置格式、判重规则、错误分类与日志字段见 [design.md](design.md)。
> 调度:每日 08:30 Asia/Shanghai(timer暂沿用裸时间;先核对系统时区与解析,不作上游239能力断言)+ RandomizedDelaySec=300 + Persistent=true(missed 补跑一次);flock 单实例。

## 阶段表

| 阶段 | 输入 | 输出 | 失败处理 |
|------|------|------|----------|
| collect | topic-digest只读;fetched_utc近48h;fresh/clustered,排除dropped | 候选条目 | 读失败 → digest_issue 记 failed,站点不受影响 |
| 判重 | 候选 URL | 按identity_key判重;未发布快照更新规则见data-source | — |
| 预筛 | 未发布且未被其他待发布期占用的条目(含可恢复的scored/selected) | 剔除:标题关键词黑名单 / 死源 / 正文空值 / 已上过日报;按预算限制候选 | 本地零成本 |
| 双次评分 | 预筛后条目 | analysis(score_1/score_2) | 额度不足停止新调用,已有合格条目可继续组装;单条失败跳过 |
| 摘要写作 | 入选条目 | 中文标题(答案先行)/一句话/推荐理由/标签 | 单条失败 → 该条剔除,不挂整期 |
| 组装 | 入选 + 摘要 | digest markdown(frontmatter:date/generated/ai_model/entry_count/cost_cny/cost_pending) | — |
| 发布 | 已验证markdown | 专用工作副本commit + push → submitted → 线上确认 → published | push冲突/构建失败保留产物,不重新付费生成 |
| 记账 | 每次receipt_attempt | 调用前预占、响应后结算;期末汇总报表 | 失败期也记账,unknown保留额度 |

## 数据落点

- `engine.db`(WAL):entry / receipt / receipt_attempt / budget / analysis / override / digest_issue / issue_freeze / api_usage / summary / notify_sent / engine_meta(**12 表** DDL 见 spec §5.3;2026-10-05 五单元批量定稿+核验修正:issue_freeze=期冻结确认+paused 三列,summary=摘要结果,notify_sent=通知去重(同 key UPSERT),engine_meta=全局运行标志(pay_paused 备份恢复付费暂停),entry.claim_issue=占用归属,digest_issue.content_sha256=产物内容身份)
- `rag.db`(M2):向量,独立库,可随时删除全量重建
- `site/src/content/digest/YYYY-MM-DD.md`:唯一公开内容源;经过push、构建和线上确认才算发布

## digest 产物模板(assemble 固定结构)

板块阈值是运营参数(放 selection.yaml),模板结构固定不动:

```markdown
---
date: 'YYYY-MM-DD'
generated: true
ai_model: example-model-id
entry_count: N
cost_cny: 0.xx
cost_pending: false
---

> AI 生成与精选 · 模型 example-model-id · 成本 ¥0.xx

## 头条(展示分 ≥ 80)

### 中文标题(答案先行)
- 一句话摘要。
- 推荐理由。[来源](url)(源名 · 展示分 82)

## 精选(75-79)

(同上结构,按展示分排序)

## 值得一瞥(压线入选)

- [标题](url)——一句话点评(源名 · 展示分 65)
```

要点:标题答案先行;每条必带原文链接与展示分;frontmatter 六字段是 site 构建契约(schema 不合构建即失败);`cost_pending` 由 assemble **显式写出**布尔值(`false`=无未决预占;`true` 时正文标注行同步"(含未决预占,为保守上界)",见 digest-design §3.4),`default(false)` 仅为旧文件兼容——字段契约三约束见 [digest-design.md](digest-design.md) §2 与 spec §4.1(当前 site 消费代码待 M1 实施许可);页面标题与AI标注由site模板保证,markdown正文不重复h1;示例model ID必须替换为实际调用模型(铁律 7)。

## 失败隔离不变量

1. 单条目失败不挂整期(例外:人工强制纳入的条目失败时组装暂停转人工——强制项是人工意志,不静默丢弃不静默降级,见 [digest-design.md](digest-design.md) §5.2)
2. LLM 全挂 → 该期不生成(digest_issue 记 failed),博客照常在线
3. engine 任何崩溃不影响静态站(独立进程独立库)

## 运维

- OnFailure 通知(凭据配在服务器 env,随 M1 部署)
- 巡检与故障处理:见 [../ops/runbook.md](../ops/runbook.md)

## 发布契约与异常恢复(M1计划必须实现)

- engine使用专用Git工作副本,开始前fast-forward同步main;生成内容只能进入digest路径。人工写作仍在个人工作副本,不得共享正在写文章的目录。
- 按issue_date唯一生成一期。重复运行复用已有回执与产物,先检查提交/线上状态;并发由engine单实例锁保护。
- 本地commit不触发bare repo hook,必须push。远端main前进导致拒收时仅做可证明安全的同步;冲突转人工,禁止force push或覆盖个人文章。
- published的证据是线上release.txt所示版本包含日报提交且对应日报可读取,不是“git命令成功”。构建可合并多个提交,不要求线上SHA恰好等于日报commit。超时保留submitted,后续只重查/重试发布。
- 坏markdown需在push前通过site schema/verify,避免阻塞个人文章后续构建。部署失败不使旧站离线;污染main仍会阻塞新内容,两种风险分开测试。
- 专用副本会跨期复用,内容删除/改名/撤回和fixture清理必须遵守[质量门禁](../development/quality-gates.md)的缓存验证;不能用残留Astro store里的旧日报证明本期产物存在。生成器不写slug,原始路径与date一致,校验从源文件开始。
- 原文材料视为不可信数据,不执行其中指令;来源URL只允许http/https,模型输出的Markdown/HTML按固定模板转义或限制,不得让原始HTML/脚本进入静态页面。
- 每次调用立即记账;发布、构建或人工覆盖失败均不能丢失实际费用。

## 通知边界

无合格产物、上游读取失败或LLM全挂记非成功期并退出非零;OnFailure调用本项目通知脚本。脚本读取历史期状态做连续2期去重告警,配置错误/进程崩溃立即通知。不能把失败退出0后期待OnFailure执行。

错误子类、HTTP处理、重试与退出码优先级统一以[design.md错误矩阵](design.md)为准。配置/不可重试请求错误及402立即通知;¥40预算预警按自然月去重,其他事件按子类+issue_date去重。402和预算预警即便已有合格内容成功发布也由应用主动通知,不能只依赖非零退出。发送结果持久化;发送失败有界重试并写日志,不得改变账本或使旧站离线。合法限额停用保留结算/复用/发布能力,与配置格式错误区分。

## 期状态、断点与恢复

以下是M1的实现与测试契约,当前没有可运行的恢复命令。`issue_date`在运行开始时按Asia/Shanghai确定,中断后继续该期不得按重启时间悄悄改期。首次没有产物时不伪造draft;在需要记失败时使用`failed`、空entry_ids与可空markdown_path。

| 持久化状态 | 成立条件 | 重启/重跑动作 |
|------------|----------|---------------|
| 无期记录 | 尚未组装出产物,可能已有付费回执 | 先恢复回执,复用同请求响应,再继续生成;读取失败可直接记failed |
| draft | 本地Markdown已落盘,路径明确;尚未确认远端接收 | 重读文件并校验schema/verify,核对Git中是否已有同产物提交,再提交或重试push |
| submitted | 远端已接收目标提交,git_commit可追踪 | 只核对线上版本与目标内容;构建失败走部署恢复,不重做评分/摘要 |
| published | 线上SHA包含目标提交,对应日报内容与目标产物一致 | 同一产物重复运行直接复用;必要纠错走新的已校验提交,费用历史保留 |
| failed | 该次执行未形成可发布产物,如读失败/零合格项 | 保存失败证据;显式重跑仍使用原issue_date与回执,已有Markdown先检查再决定重组 |

Git和SQLite不是同一事务:必须覆盖“commit成功但状态未写入”“push实际成功但客户端超时”“上线成功但进程未记published”三个窗口。恢复先查询远端提交、路径和内容身份,再补记状态;不能仅凭命令退出码重新生成。线上SHA的祖先关系只能证明提交被包含,还要排除后续提交删除/修改目标日报。`entry.status=used`只在确认published后更新,恢复时可根据已发布期补齐;未发布期选中的条目不得被另一待发布期重复占用。

人工撤回或整站回滚另留操作记录,历史published只证明曾发布,不代表当前可见。撤回前暂停该期自动重试,将排除策略与期状态核对完成后再恢复调度,避免定时器把已撤内容自动发布回来。M1计划须给出实际操作命令并演练,不能在此阶段假设命令已存在。

## 公开成本口径

`cost_cny`是该期在发布时的费用快照,包含失败候选、评分、摘要与重试;不能只算最终入选条目。按每个attempt的实际费用或尚未结算的保守预占求和,不重复计同一次预占和结算。若仍有未决(所有 actual 未核清的 attempt,不限于 status=unknown),frontmatter 写 `cost_pending: true`,正文与页面说明“成本含未决预占,为保守上界”;不得标成已结算实付或写0。`cost_pending` 与 `cost_cny` 出自**同一时点、同一期费用快照**;新生成日报显式写出布尔值,`default(false)` 仅为旧文件兼容。账本始终是最新结算依据;后续核清需要纠正公开数字时,**数字、标志与正文标注一起**通过正常内容提交更新,不另发模型请求(三约束全文见 [digest-design.md](digest-design.md) §2)。

## M1实现前必须映射的恢复信息

| 信息 | 使用者与恢复要求 |
|------|------------------|
| 失败阶段/原因、更新时间 | 运维区分生成失败与发布失败;通知按期而非重试次数判连续失败 |
| 产物内容身份与git_commit | commit/push返回未知时核对已有文件/远端提交;不能仅比较路径存在 |
| 期重试暂停标志及原因 | 人工撤回后重启仍不自动重发;恢复必须显式操作并留痕 |
| 告警去重键/发送结果 | 同期重复失败、月度预算预警去重;发送失败允许有界重试 |
| 普通重试与unknown计数 | 同一logical_key跨重启累计,分别限次且总attempt不超过design规定;不能通过重启或切换错误类型重新领次数。**口径与落点(第三轮定稿,units/model-calls.md §3 规则 5/spec §5.3.1)**:普通名额消耗=该 logical_key 中 `attempt_origin IN ('initial','retry') AND error_class='retryable'` 行数(≤max_attempts);unknown 专属=receipt.unknown_retry_used(与 `attempt_origin='unknown_retry'` 行同事务双写);类别判定读 attempt.error_class(与 fail_detail_json 于失败更新同事务写入) |
| 条目与未完成期的归属 | draft/submitted占用条目;failed经核对后释放或恢复,避免永久卡死与跨期重复 |

M1计划逐项选择现有表字段/JSON或本项目状态文件,同步spec DDL及操作命令后实施,不引入队列服务。正常运行先恢复未完成期(**恢复阶段有预算上限 recover_budget_s,旧期失败不挤占当天新期采集与生成,见 units/scheduling-ops.md**),再选新候选;scored/selected不能因只查询pending而丢失。已收响应按完整请求hash复用(**复用有效性=完整 E4 验证器,非正常终止不可消费,见 units/model-calls.md**),输入变化走新请求身份,旧attempt费用保留。**上述恢复信息映射已于 2026-10-05 五单元设计+核验修正轮全部定稿(spec §5.3.1 清单)。**

engine工作副本在已有未推送提交时不能先盲目fast-forward同步。先保存并识别本期提交,再检查远端差异;仅无冲突且内容身份保持时同步,否则暂停自动发布并留人工处理证据。
