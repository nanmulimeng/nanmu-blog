# 会话交接:单元二《模型调用与费用治理》设计+单元一复用交接回填(2026-10-05)

- **recorded_at**: 2026-10-05 Asia/Shanghai
- **continues**: [单元一第二轮复核交接](2026-10-05-unit1-review2.md)
- **repository**: main;本轮两个提交(复核状态记录 d419958 + 单元二设计与回填,见 git log),未推 origin/server。
- **objective**: 按用户指示直接进入单元二并联合收口复用/付费容量接口问题:明确"已有响应如何识别、剩余调用如何授权、N_new 究竟限制什么",定稿后一次性回填单元一规则 8/输出表/验收 9;费用快照、attempt 结算、未决预占照常设计。

## change_scope

**① 复核状态记录(d419958)**:data-ingestion.md 状态行改"部分通过复核,联合定稿中";§9 加复用交接未决项(两个 P1+交接原则);验收 9 加复核标注;评审提示重写。规则 8/输出③/验收 9 实质未动。

**② 单元二设计(新文档 [engine/units/model-calls.md](../engine/units/model-calls.md),设计稿待评审)**:

- **三问定稿**:已有响应识别=`reusable_scores(members, identity_ctx)` 只读接口(完整请求身份匹配+status∈{received,completed}+业务可解析;本期同身份 analysis 行同等);剩余调用授权=ledger 唯一闸门(短事务查额度+写预占→COMMIT→出网,逐次);**N_new=仅限"确需新增付费评分"的条目容量**,作用顺序=排除→复用判定→排序→截断,可复用成员/摘要/重试三类不占 N_new。
- **回填单元一**(联合定稿闭环):recoverable 重定义=**当前完整请求身份下评分响应可复用**的成员(单义:只承诺评分网络零新增,不承诺摘要完成/可组装);预筛签名加复用快照(纯函数保持,等价输入含复用快照);身份变化的 selected 按需新增付费参与排序、capped 可见;验收 9 扩四子场景(a 全完成零网络/b 评分已持久化未入选不丢/c 摘要未完成不当可组装证明/d 身份变化不冒充);正常样例更新(34 冻结→recoverable 4+to_score 12+capped 7);规则 7.6 本期 selected 去向改由复用判定决定。
- **费用域操作协议**:授权/响应回写/业务完成/失败/复用/核清/月投影的表操作事务边界表(receipt/receipt_attempt/budget/api_usage 四表,DDL 零新增);费用快照=**同一时点同一只读聚合查询**产出 cost_cny+cost_pending(约束①的物理实现);结算规则(先持久化再解析、actual IS NULL=未决不 COALESCE)、unknown 30min 从 started_utc 起+一次自动重试、核清(账单证据填 actual、跨月未决保留、实付超预占停新增)、费用归属(attempt 归 issue_date、跨期复用不重复计费)。
- 恢复表 A-G(授权后出网前崩溃/响应已落库业务未写/写入选前中断/unknown 到期/预算停用/实付超预占/跨期正文刷新);验收 9 例(复用矩阵/作用顺序/身份变化 selected/闸门/unknown/快照单查询/核清/跨期费用归属/回填四子场景)。

**③ 同步**:design.md 候选上限节补"N 只限确需新增付费评分,先复用后截断"一条(引用两单元文档);spec 变更记录加 2026-10-05 复核+联合定稿条目。

## state

- 单元二设计稿**待用户评审**;单元一回填部分**待用户复核**(冻结存储方案与排除规则已通过的结论不受影响)。
- 单元一 §9 未决项现为:占用归属存储(单元三联合)为首行,复用交接行已移除(定稿回填完成)。
- 单元二 §9 开放两条:analysis/摘要业务写入与 receipt completed 的事务交界(单元三);通知去重键持久化(单元五);对账证据字段留 M1 plan。
- M1 plan 与编码暂停继续有效。

## verification

| 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
|--------------|----------------|--------------|
| 仓库根 | `python scripts/check_docs.py --snippets --bash … --node …` | 见当轮输出 |
| 仓库根 | `git diff --check` | 通过 |

- **disposition**: continuable(单元二与回填待用户评审)
- **next_action**: 用户评审 [units/model-calls.md](../engine/units/model-calls.md) 与单元一回填(阻塞点=N_new/复用/授权三问是否成立、recoverable 单义化是否到位);通过后进入单元三《日报编辑与内容生成》(须联合定稿占用写入释放协议、analysis 摘要事务交界、prompt 权重两分法)。
- **omissions**:
  - 单元二未设计 llm.py HTTP 契约细节(已在 design.md 定稿,本文只引用)。
  - 通知/去重/重试计数字段映射留单元五;对账证据形态留 M1 plan。
  - 用户侧待办不变(skills DNS/ICP/origin 推送/验收目录清理/Task10);线上仍 c8a4567。
