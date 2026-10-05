# 模型调用与费用治理·单元详细设计(M1 第 3 步·单元二)

> 状态:**设计稿,待用户评审**(2026-10-05;第 3 步五单元之二,以 [digest-design.md](../digest-design.md) v3 与单元一复核结论为输入)。含与单元一的**联合定稿**:复用识别与新增付费容量(N_new)的交接,定稿后已回填单元一规则 8/输出③/验收 9。
> 定位:回答"每一次模型调用如何被授权、执行、结算、复用,费用如何在任何中断下不丢不重"的**实现层设计**。运营数值真相源在 [budget.md](../budget.md);请求身份/错误分类/调用 HTTP 契约在 [design.md](../design.md);回执状态机与 DDL 在 spec §5.4/§5.3;功能层费用呈现(digest-design §2)不在本文重复。
> 引用而非复制:候选上限公式本体在 design.md 候选上限节;未知结果恢复在 budget.md 回执与恢复节;本单元只落**接口、事务边界与操作协议**。

## 0. 单元边界与接口交接

| 数据/接口 | 本单元职责 | 相邻单元职责 |
|------|-----------|--------------|
| `receipt` / `receipt_attempt` / `budget` / `api_usage` 表 | **唯一写入者**(预占/结算/核清/月投影) | 全管线只读;费用真相源=receipt_attempt(整数微元) |
| **N_new**(新增付费评分容量) | **计算**(design.md 公式代入预算参数)并输出给编排层 | 单元一预筛**消费**(只截断确需新增付费成员,§3 规则 4) |
| **reusable_scores(manifest 成员, 请求身份上下文) → 复用快照** | **提供**(只读判定,读 receipt/analysis,零副作用) | 编排层在预筛前调用,把结果作为预筛输入——预筛保持纯函数、不查 receipt |
| score / summarize 模型调用 | **执行**(经 llm.py;授权→出网→结算→业务回写) | 单元三消费结果(analysis 行/摘要 JSON)并定入选与组装 |
| 期费用快照(cost_cny + cost_pending) | **产出**(同一只读聚合查询) | 组装(单元三)写入 frontmatter;核清后的纠正提交属发布链(单元四) |
| 预算停用/预警事件 | 产生(E5.limit/¥40 预警,事件与去重键留给单元五持久化) | 单元五定通知去重存储 |

## 1. 目标与范围

**解决**:一次付费调用从授权到结算的完整闭环;续跑/跨期时已有响应的识别与零网络复用;N_new 的精确语义;期费用快照与未决预占口径;unknown 与核清的操作协议。

**本单元做到**:ledger 授权闸门(唯一)、请求身份构造与复用判定接口、N_new 计算、attempt 结算与核清、费用快照产出、api_usage 投影。

**明确延期**:评分判据与 prompt 文案(单元三);入选判断与组装(单元三);发布链费用呈现的提交动作(单元四);通知去重键/重试计数的持久化字段映射(spec §5.3.1 清单,单元五);M2 并发所有权(budget.md 既定延期)。

## 2. 使用场景

| 场景 | 触发 | 前提 | 正常完成后 |
|------|------|------|-----------|
| 新期评分授权 | 预筛输出 to_score | 预算闸门通过 | 每条两 attempt(score-1/2)结算回写,analysis 行交付单元三 |
| 续跑恢复 | 同期再次进入,预筛前 | 冻结已确认 | reusable_scores 判定→可复用成员零网络进入下游 |
| 跨期复用 | 条目在新期入围 | 完整请求身份未变 | 旧响应直接复用,费用留在原 attempt 期不重复计入 |
| 摘要授权 | 入选条目进摘要阶段 | 每次调用逐过闸门 | understand attempt 结算回写 |
| unknown 恢复 | 定时/续跑发现 unknown≥30min | 自动名额未用 | 一次额外重试;二次转人工 |
| 费用快照 | 组装时/核清后/status 查询 | — | 同一时点单查询产出数字+标志 |
| 核清 | 供应商账单对账 | 有对账证据 | actual_micro_cny 落账,预占转实付,月投影更新 |

## 3. 业务规则(优先级从高到低)

1. **授权闸门唯一**(budget.md/spec §5.4):一切新增付费 attempt 只经 ledger——短事务内查窗口次数(receipt_attempt.started_utc 聚合)+金额(已结算+全部未决预占)与限额,通过则写 receipt_attempt(pending+reserved)并 COMMIT,**之后**才出网。业务模块禁止绕过;预筛截断是容量**估算**,不替代逐次授权。
2. **请求身份与复用判定**(spec §5.4 幂等键):logical_key=provider/endpoint/purpose/model/request_hash/attemptTag;request_hash 覆盖 identity_key、manifest 正文 content_hash、prompt 版本、模型参数与输出上限。**复用条件=完整请求身份匹配且 receipt.status ∈ {received, completed} 且响应业务可解析**;本期已有同身份 analysis 行同等视为可复用(零网络)。换 prompt/模型/正文(含跨期正文刷新)→身份变化→旧响应不得冒充(budget.md)。
3. **复用判定接口(联合定稿核心)**:`reusable_scores(members, identity_ctx)` 只读、零副作用、纯查询;输出复用快照(每成员:score-1/score-2 是否各有可复用响应+analysis 行引用)。**预筛不查 receipt**——编排层先调本接口,把复用快照与 N_new 一起传入预筛(单元一 §3 规则 8 回填后口径)。
4. **N_new 究竟限制什么(定稿,回填单元一)**:N_new=本期**确需新增付费评分**的条目容量上限,且只限制这一件事。作用顺序:**排除(内容/编辑/占用)→ 复用判定 → 剩余成员=确需新增付费 → 确定性排序 → 截断前 N_new**。不占 N_new、不被截断的三类:①当前身份下评分可复用的成员(本期 selected 的常态;评分响应已持久化、写入入选前中断的成员;跨期同身份成员);②摘要调用(N 公式按 max_entries 预留);③重试(retry_reserve 单列)。**不因 N_new=0 丢失任何可恢复工作**——可复用成员照常输出,未评分成员停增但不消失(capped 可见)。
5. **recoverable 语义收敛(回填单元一)**:recoverable=通过内容/编辑/占用检查且**当前完整请求身份下评分响应可复用**的成员——只承诺"评分网络零新增",**不承诺摘要完成、不承诺可组装**。是否还需摘要(或身份变化后的重新评分)由对应阶段按完整请求身份与实际完成结果判断,任何新增调用仍逐次经授权闸门。组装就绪的判定依据=实际评分与摘要结果,不能仅凭属于 recoverable。
6. **结算规则**:收到响应先持久化(received+usage_json+pricing_version)再解析业务;usage 按该次价目快照结算填 actual_micro_cny(明确的 0 也是核清);`actual IS NULL`=未决,不能 COALESCE 为 0 释放预算;解析失败不抹去响应与费用(E4 走普通重试,费用照记)。
7. **unknown 与核清**:pending→unknown(超时/崩溃);≥30min(从该次 started_utc 起)自动重试一次,unknown_retry_used 与新预占同短事务;二次转人工。核清=按 attempt 关联供应商账单证据填 actual,保留原尝试/started_utc/价目版本;跨月未决继续占用;供应商实付超预占→停新增+修正计价上界。
8. **费用快照(三约束的物理实现)**:同一时点、同一只读聚合查询——`cost_cny`=该期(issue_date)全部 attempt 的 Σ(已核清取 actual,未核清取 reserved 保守值);`cost_pending`=是否存在任一 actual IS NULL 的 attempt(**覆盖所有未核清,不限 status=unknown**)。两值同查询产生,禁止分别查询拼装(digest-design §2 约束①②③)。账本更新不依赖站点发布成功。
9. **费用归属**:attempt 归属 issue_date;跨期复用不新增付费也不把旧费用计入新期快照;旧 attempt 归属不得为释放单期额度改期;重试是新 attempt 归原期(budget.md)。

## 4. 输入输出

**输入**:manifest 成员(单元一;含 content_hash)、请求身份上下文(prompt 版本/default_model/参数/config 快照 hash)、budget.yaml、budget 表、receipt/receipt_attempt/analysis 现状、供应商账单证据(核清时)。

**输出**:
- `N_new`(int ≥0;design.md 公式,输入=预算参数与窗口余量);
- **复用快照**(reusable_scores 结果:{identity_key → {score_1, score_2, analysis_ref}};给编排层→预筛);
- analysis 交付(评分两条 attempt 结算+业务写,归单元三消费);
- 摘要 JSON(understand attempt 结算+业务写);
- 期费用快照(cost_cny + cost_pending 单查询);
- api_usage 月投影(报表,不作授权依据)。

**非法输入处置**:budget 行缺失=E1 拒付费(design.md 加载契约);价目版本缺该 model=E1;账单证据不足→不核清(保持未决),不得凭"应该没扣费"填 0。

## 5. 数据与状态(表操作协议;DDL 不新增,spec §5.3 既有 4 表)

| 操作 | 事务边界 | 写入 |
|------|----------|------|
| 授权 reserve | 短事务 BEGIN IMMEDIATE→COMMIT 后出网 | receipt_attempt(attempt_no, pending, reserved_micro_cny, issue_date, started_utc, pricing_version);首attempt 同事务建 receipt 行 |
| 响应回写 | 单事务 | receipt_attempt→received+usage_json+actual_micro_cny(可结算时);receipt.response_json/status→received |
| 业务完成 | 单事务 | receipt.status→completed;analysis/摘要结果写入(与单元三交界,业务表归其定稿) |
| 失败/未知 | 单事务 | attempt→failed(有 usage 则结算)/unknown(预占保留);receipt.status 同步 |
| 复用 | **无事务(只读)** | 无写入;logical_key 查询 |
| 核清 | 单事务 | attempt.actual_micro_cny+对账证据;api_usage 重算该月行 |
| 月投影 | 幂等重算 | api_usage(月,provider,model)聚合行 |

**关键决策与理由**:
- **复用判定放单元二而非预筛内**(联合定稿):判定需要请求身份构造与 receipt 语义,属费用域知识;预筛消费只读结果保持纯函数与等价输入可测性(同 manifest+同占用/override/**同复用快照**+同 N_new→同输出)。
- **可复用≠可组装**:recoverable 只免除评分网络,摘要与身份变化后的重评仍走闸门——"已有进度不丢"与"新增付费受控"两个承诺由不同机制分别保证,不混在一个状态位里。
- **身份变化的 selected** 不再可复用→按确需新增付费参与 N_new 排序;被截断则 capped 可见,组装边界按"曾 selected 而无当前有效评分"暂停联动(动作归单元三)——不静默丢,也不让罕见路径扭曲容量模型。
- **快照单查询**:约束①(同时点同源)的物理保证=一条 SQL 的同一读事务,消除"分别查询形成不同口径"的实现可能。

## 6. 异常与恢复

| # | 场景 | 现场状态 | 恢复判定与动作 | 费用 |
|---|------|----------|----------------|------|
| A | 授权后出网前崩溃 | attempt=pending(已预占) | 无已持久化响应→转 unknown(budget.md:不视为未发送免费重试) | 预占保留 |
| B | 响应已落库、业务未写 | receipt=received;attempt 已结算 | 续跑按身份复用 received 响应→补写业务(零网络) | 已结算不重付 |
| C | 写入选前中断(评分完成未 selected) | analysis/received 在,entry 未 selected | 复用快照识别→recoverable→下游零网络重新判断入选 | 零 |
| D | unknown 到期 | attempt=unknown≥30min | 名额未用→一次自动重试(标志+新预占同事务);已用→转人工 | 旧占用保留 |
| E | 预算停用(E5.limit) | 限额≤0 或闸门拒绝 | to_score 停增;可复用/摘要预留内工作照常;已有合格条目组装发布 | 已发请求照常结算 |
| F | 供应商实付>预占 | 核清时发现 | 停新增调用+修正计价上界+记账实付 | 不截断数字 |
| G | 跨期正文刷新 | entry 新 content_hash;旧 attempt 旧 hash | 身份已变:旧响应不可复用于新输入,旧费用保留归原期;新评分走新授权 | 旧费用不退 |

## 7. 验收场景(M1 plan 强制测试种子;输入→期望)

1. **复用判定矩阵**:同身份 completed→可复用;prompt 版本变→不可;content_hash 变→不可;received 且可解析→可复用;received 不可解析→不可(走 E4 重试路径)。
2. **N_new 作用顺序**:10 合格成员中 4 条可复用+6 条需新增,N_new=4 → 4 条 recoverable+4 条 to_score+2 条 capped;N_new=0 → 4 recoverable+6 capped,**无成员丢失**。
3. **身份变化的 selected**:本期 selected 但 prompt 升级→不可复用→参与排序;落 capped 时结果可见(接口断言),不静默。
4. **授权闸门**:小时窗口将满→新增 attempt 被拒(不写预占);复用查询不计窗口次数(spec §5.4 统计口径)。
5. **unknown**:替身时钟+进程中断→30min 从 started_utc 起、标志持久化、二次转人工;不因重启重置。
6. **费用快照单查询**:构造 3 settled+1 未决(含 1 条 received 未核清的非 unknown)→ cost_cny=Σ(2 actual+2 reserved)、cost_pending=true;两值断言出自同一查询(可用查询计数替身)。
7. **核清**:填 actual(含 0)→未决转实付、月投影更新、下期月可用随之变化;证据字段非空。
8. **跨期复用费用归属**:上期 attempt ¥0.01 已结算,本期复用→本期快照不含该 ¥0.01,上期快照不变。
9. **(回填单元一)验收 9 四子场景**:见 [data-ingestion.md](data-ingestion.md) §7——selected 全完成+N_new=0 零新增网络/评分已持久化未入选不因截断丢失/selected 摘要未完成不被当可组装/身份变化旧响应不冒充。

## 8. 依赖与维护成本

- 零新增依赖:httpx+sqlite3 既有契约;无新表无新服务。
- 复用判定查询按 logical_key 精确匹配(receipt 已有 UNIQUE 索引),attempt 窗口聚合走 idx_attempt_started。
- 对账证据存储位置(usage_json 内或独立元数据)在 M1 plan 映射(spec §5.3.1 既定)。

## 9. 未决项

| 未决项 | 验证方法 | 通过条件 | 失败后的备选 | 定位 |
|--------|----------|----------|--------------|------|
| analysis/摘要业务写入与 receipt completed 的事务交界(同事务或先后) | 单元三设计推演 | 崩溃窗口内无"业务在而回执未完成"或反向不一致 | 分事务+恢复补写(按 received 复用) | 日报编辑与内容生成 × 本单元 |
| ¥40 预警/E5 通知去重键的持久化 | 单元五按 spec §5.3.1 清单 | 同月/同期去重可判定且重启不重置 | 独立状态文件 | 调度与运行维护 |
| 对账证据字段与核清命令形态 | M1 plan 映射 | 核清操作可留痕、可重放 | usage_json 内嵌 JSON | M1 plan |

## 评审提示

本单元**联合定稿**了单元一遗留的复用识别与新增付费容量交接(§3 规则 3/4/5):复用判定=单元二只读接口、预筛保持纯函数;N_new=仅限确需新增付费评分、先复用后截断;recoverable 收敛为"评分网络零新增"单义。**已回填**单元一规则 8/输出③/验收 9 与 design.md 候选上限节一句引用。开放项:§9 两条交界(单元三/单元五)。费用快照/attempt 结算/未决预占按 budget.md 与三约束落操作协议,未新增表。
