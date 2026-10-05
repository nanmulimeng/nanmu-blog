# 模型调用与费用治理·单元详细设计(M1 第 3 步·单元二)

> 状态:**设计稿 v5,第四轮核验修正**(2026-10-05;改:①**attempt_origin=授权语义**——预占时确定、写入后不可改写,名额公式改"普通尝试已用数不按 error_class 过滤"(名额按授权消耗);②新增**规则 11 校准通道契约**(例外唯一/月预算与窗口照常/记录绑定配置/初始系数依据);③对账硬失败**停新增=持久化置 pay_paused**。v4 的三列持久化/三条件结构/pay_paused 读法保持)。
> 定位:回答"每一次模型调用如何被授权、执行、结算、复用,费用如何在任何中断下不丢不重"的**实现层设计**。运营数值真相源在 [budget.md](../budget.md);错误分类/调用 HTTP 契约在 [design.md](../design.md);回执状态机与 DDL 在 spec §5.4/§5.3;功能层费用呈现(digest-design §2)不在本文重复。
> 引用而非复制:候选上限公式本体在 design.md 候选上限节;未知结果恢复在 budget.md 回执与恢复节;本单元只落**接口、事务边界与操作协议**。

## 0. 单元边界与接口交接

| 数据/接口 | 本单元职责 | 相邻单元职责 |
|------|-----------|--------------|
| `receipt` / `receipt_attempt` / `budget` / `api_usage` 表 | **唯一写入者**(预占/结算/核清/月投影) | 全管线只读;费用真相源=receipt_attempt(整数微元);核清证据=reconcile_json(§5) |
| **N_new**(新增付费评分容量) | **计算**(design.md 公式代入预算参数)并输出给编排层 | 单元一预筛**消费**(只截断确需新增付费成员,§3 规则 4) |
| **reusable_scores(manifest 成员, identity_ctx) → 复用快照** | **提供**(只读判定,读 receipt/analysis,零副作用;含 needs 待补清单) | 编排层在预筛前调用,把结果作为预筛输入——预筛保持纯函数、不查 receipt |
| **identity_ctx(请求身份上下文)** | **消费**(构造 request_hash 的全部字段以生产方提供为准) | **生产=单元三**:prompt 版本/model/参数/截断后实际输入(§3 规则 2);本单元不自行拼装业务输入 |
| score / summarize 模型调用 | **执行**(经 llm.py;授权→出网→结算→业务回写) | 单元三消费结果(analysis/summary 行)并定入选与组装;业务写入与 receipt completed **同事务**(单元三 §5) |
| 期费用快照(cost_cny + cost_pending) | **产出**(同一只读聚合查询) | 组装(单元三)写入 frontmatter;核清后的过期提示与纠正提交属单元四 |
| 预算停用/预警事件 | 产生(E5.limit/¥40 预警) | 单元五消费并按 notify_sent 去重 |

## 1. 目标与范围

**解决**:一次付费调用从授权到结算的完整闭环;续跑/跨期时已有响应的识别与零网络复用;N_new 的精确语义与三类"不新增"的区分;双次评分完成度分类与恢复;期费用快照与未决预占口径;unknown 与核清的操作协议。

**本单元做到**:ledger 授权闸门(唯一)、请求身份构造规则与复用判定接口、N_new 计算、attempt 结算与核清(含证据存储)、费用快照产出、api_usage 投影。

**明确延期**:评分判据与 prompt 文案(单元三);入选判断/组装/占用写入(单元三);发布链与核清后内容更新(单元四);通知发送与去重执行(单元五消费 notify_sent 契约);M2 并发所有权(budget.md 既定)。

## 2. 使用场景

| 场景 | 触发 | 前提 | 正常完成后 |
|------|------|------|-----------|
| 新期评分授权 | 预筛输出 to_score | 授权闸门通过 | 每条两 attempt(score-1/2)结算回写,analysis 行交付单元三 |
| 双次评分部分恢复 | 续跑发现某成员仅一条有效响应 | 该响应身份仍有效 | 复用快照标 needs→**只补缺失那条**,已有响应不重发,attempt 序号继续(计数不重置) |
| 跨期复用 | 条目在新期入围 | 完整请求身份未变 | 旧响应直接复用,费用留在原 attempt 期不重复计入 |
| 摘要授权 | 入选条目进摘要阶段 | 每次调用逐过闸门 | understand attempt 结算回写,summary 行交付单元三 |
| unknown 恢复 | 定时/续跑发现 unknown≥30min | 自动名额未用 | 一次额外重试;二次转人工 |
| 费用快照 | 组装时/核清后/status 查询 | — | 同一时点单查询产出数字+标志;零 attempt 期=0/false |
| 核清 | 供应商账单对账 | 有对账证据 | actual+reconcile_json 同事务落账,月投影更新 |

## 3. 业务规则(优先级从高到低)

1. **授权闸门唯一**(budget.md/spec §5.4):一切新增付费 attempt 只经 ledger——短事务内查窗口次数(receipt_attempt.started_utc 聚合;复用响应不计)+金额(已结算+全部未决预占)与限额,通过则写 receipt_attempt(pending+reserved)并 COMMIT,**之后**才出网。**闸门同时检查 engine_meta.pay_paused——仅显式 0 放行;=1(备份恢复后的全局付费暂停,单元五)或键缺失(违规恢复/库损坏的异常态,合法库建库时即写入默认值)均拒绝一切新增**,复用/结算/只读不受限。业务模块禁止绕过;预筛截断与公式预留都是容量**估算**,不替代逐次授权(**预留不构成调用许可**,规则 6);**新增付费另受规则 2 的"计数可得"前置约束(计数不可得不出网)**。
2. **完整请求身份(覆盖实际发送的有效输入及参数)**:request_hash = sha256(确定性序列化的以下全部字段)——provider、endpoint、purpose、model、**prompt_version、模板实例化后的完整 system+user 文本(含截断标记后的实际输入,非原始材料)**、max_tokens、thinking=disabled、response_format、identity_key、manifest 正文 content_hash、attemptTag(score-1/score-2/understand)。**费用预占按发送前的最终请求 token 计数计算**(单元三 §3 规则 5:tokenizer 对完整请求消息计数,预占=计数×校准系数向上取整;字符比例不进入授权链——官方换算仅"大致比例"且随模型分词而异,推不出"每字符至多一 token")。**计数不可得(model→tokenizer 映射缺失/资源加载失败/校准未完成)→拒绝新增付费,不出网**,不回退字符估算(**唯一例外=校准通道自身,见规则 11**;正式管线 purpose∈{score,understand} 均受此约束)。响应回填后 usage.prompt_tokens 与预占计数对账,**超出=上界失效:置 engine_meta.pay_paused=1 持久化停新增并记录原因(第四轮:停新增不是内存态——复用既有闸门,与备份恢复暂停同一解除协议,重启继续拒绝、人工核对后显式置 0;复用/结算/只读照常)+修正系数或映射**,处置同规则 8"供应商实付>预占"(无容忍个位;首轮 v2 的"记警示日志"口径作废)。
   - **复用验证与首次消费使用同一有效性规则**:reusable_scores 命中即返回 receipt 引用,消费方按该引用读取响应,**不做第二次不同规则的判定**——不存在"预筛说可复用、评分单元说无效"的分叉;判定与消费共用本规则的 request_hash 构造。
   - **analysis/summary 通过关联回执核对身份**:业务行有效 = receipt_ids 所引 receipt 的 request_hash 与当前 identity_ctx 一致(prompt 升级/正文变化后旧行自动失效,不迁移不删除,append-only)。
3. **复用判定接口**:`reusable_scores(members, identity_ctx)` 只读、零副作用;输出复用快照=每成员 `{score_1: ok?, score_2: ok?, needs: [待补 attemptTag], analysis_ref?}`。**有效性条件**(同一套,判定与消费通用):完整请求身份匹配(规则 2)+ receipt.status ∈ {received, completed} + 响应通过**完整 E4 业务验证器**(与首次消费同一验证器,非仅"可解析":正常终止 finish_reason=stop、JSON 契约字段类型与范围全过——`finish_reason=length` 等非正常终止即使 JSON 恰好可解析也**不可消费**,按 E4 处置;design.md 错误矩阵为验证器真相源);本期同身份 analysis/summary 行同等视为有效进度。
4. **N_new 究竟限制什么**:N_new=本期**确需新增付费评分**(score-1 与 score-2 **均无**有效响应)的条目容量上限,且只限制这一件事。作用顺序:**排除(内容/编辑/占用)→ 复用判定 → 剩余=确需新增付费 → 确定性排序 → 截断前 N_new**。不占 N_new、不被截断的三类:①**至少一条有效评分响应**的成员(进度保留,needs 补全);②摘要调用(N 公式按 max_entries 预留);③重试(retry_reserve 单列)。**不因 N_new=0 丢失任何可恢复工作**。
5. **双次评分完成度分类与恢复(2026-10-05 评审修正+核验修正:计数按 logical_key 独立)**:
   | 完成度 | 判定 | 去向 | 恢复行为 | 计数 |
   |--------|------|------|----------|------|
   | 全部完成 | score-1、score-2 均有效 | recoverable(needs=∅) | 零评分网络;直接进入入选判断/组装 | — |
   | 部分完成 | 恰一条有效 | recoverable(needs=缺失项) | **只补缺失那条**;已有响应保留不重发;补全调用逐次过闸门 | **缺失侧按其自身 logical_key 计数顺延**:从未发送则从 1 起,已有失败/unknown 则续计 |
   | 均未完成·未发起/未耗尽 | 两条均无效(从未发起、或身份变化致旧响应失效),且缺失侧满足**再发送三条件**(下段;从未发起=天然满足) | 确需新增付费,参与排序截断 | to_score 补评;capped 可见停增 | **各自 logical_key 统计**,重启不重置:同身份逻辑回执续在原计数上,不因重跑重获尝试额度 |
   | 均未完成·已耗尽 | 缺失侧不满足再发送三条件之一(普通名额耗尽/类别不允许/硬上限满) | 不再自动发起 | 最终处置=**E7 剔除该条**(普通项;强制项→暂停联动,单元三);重启后仍视为耗尽;仅身份变化(新 logical_key)或人工显式操作才可能新调用 | 计数不重置、不重获额度 |
   身份变化的本期 selected 落"均未完成"类(旧响应不得冒充当前结果),被截断则 capped 可见,组装边界按"曾 selected 而无当前有效评分"暂停联动(单元三)。

   **再发送三条件(同一判定用于"部分完成补缺失"与"均未完成重跑";第二轮拆名额类别;第四轮定稿计数口径——名额按授权消耗,不随响应结果改写)**:
   1. **错误类别允许自动重试,并决定通道**:读该 logical_key 最近一次失败/unknown attempt 的 `error_class`(design.md 错误矩阵为准)——no_retry(HTTP 400/请求格式错误/终止原因/余额类)→**不允许,计数未满也不再调用**;retryable→走**普通通道**(下一个 attempt origin='retry');unknown→仅当满足 unknown 专属名额等待条件(≥30min)才走 **unknown 通道**(下一个 attempt origin='unknown_retry');
   2. **对应类别名额有剩余**(**读 receipt_attempt 持久化列,唯一口径**):**普通尝试已用数=该 logical_key 中 `attempt_origin IN ('initial','retry')` 的行数(不按 error_class 过滤——每次授权即消耗一个名额,与返回结果无关;spec §5.3.1 公式,上限 max_attempts,即 design.md"共享 max_attempts−1 个普通重试名额")**;**unknown 专属额外名额**=receipt.unknown_retry_used=0 且距该次 started_utc≥30min(等待条件;标志与 `attempt_origin='unknown_retry'` 行同事务双写,判定读标志、审计按行重算);**两类名额不可互借**——普通额度耗尽不因 unknown 名额未用而继续,反之亦然;
   3. **累计硬上限+当次授权**:该 logical_key 总 attempt 行数 < max_attempts+1(budget.md L20 既有契约:普通最多 max_attempts 次、unknown 满足条件的一次额外,总和即硬上限),且当次过授权闸门(含规则 1 pay_paused/键缺失检查与规则 2 计数可得)。
   **判定输入全部来自持久化列(第三轮核验补齐)**:条件 1 读最近一次失败 attempt 的 `error_class`(规范化映射:矩阵 E1.request/E4.terminal/E5.balance→no_retry;E3.http/E4.parse→retryable;E3.unknown→unknown——由 llm.py 响应处理产出,失败/unknown 更新**同事务**写入,`fail_detail_json` 存 HTTP 状态+子类+摘要);条件 2/3 按上述公式查询。**重启后仅凭 DB 重放判定**,不依赖进程内存。**`attempt_origin` 是预占时确定的授权来源,写入后不可改写(第四轮定稿)**:unknown 通道重试(attempt 2)即使返回 HTTP 503,该行仍保持 origin='unknown_retry'/error_class='retryable';若普通名额仍有剩余而再发起普通重试(attempt 3),那是**新授权**,origin='retry' 计入普通尝试已用数——名额在授权时消耗,历史不因响应类型变化。
   反例封堵:max_attempts=2、同 logical_key 两次普通尝试(initial+retry 各一,均返回可重试失败)、unknown_retry_used=0——条件 2 失败(普通已用 2=max_attempts),不再发送;重启后判定不变。
6. **三种"不新增"的区分(2026-10-05 评审修正)**:
   | 概念 | 性质 | 发生时点 | 效果 |
   |------|------|----------|------|
   | N_new=0 | 容量**估算结果**(预算参数代入公式) | 预筛前计算 | to_score 空;可复用/needs 补全/摘要照常走各自路径 |
   | 合法停用(E5.limit) | **配置层状态**(限额≤0/预算行缺失除外——缺失是 E1) | 加载时即知,运行中变更在下一次授权前生效 | N_new 直接 0 **且**闸门拒绝一切新增;复用/结算/发布照常 |
   | 逐次授权拒绝 | **运行时事件**(单次调用时窗口/金额不足) | 每次出网前 | 该条停止新增(跳过);不回滚已授权调用;不影响其他成员;与 N_new 无必然联系(估算可以乐观,闸门是强制) |
   **摘要与重试预留不构成调用许可**:公式中 max_entries/retry_reserve 的扣减只为容量估算,每次摘要/重试调用仍逐次过闸门,预留内也可能因金额/窗口被拒(拒绝后按 E7 跳过该条/强制项例外转单元三)。
7. **结算规则**:收到响应先持久化(received+usage_json+pricing_version)再解析业务;usage 按该次价目快照结算填 actual_micro_cny(明确的 0 也是核清);`actual IS NULL`=未决,不能 COALESCE 为 0 释放预算;解析失败不抹去响应与费用(E4 走普通重试,费用照记)。
8. **unknown 与核清**:pending→unknown(超时/崩溃);≥30min(从该次 started_utc 起)自动重试一次,unknown_retry_used 与新预占同短事务;二次转人工。**核清=按 attempt 关联供应商账单证据,单事务 UPDATE actual_micro_cny + reconcile_json**(证据:类型[账单行/usage 复核]、关联标识、核查时间、依据说明;**证据不足不得核清**,不得凭"应该没扣费"填 0);跨月未决继续占用;供应商实付超预占→**置 pay_paused=1 持久化停新增并记录原因(第四轮,同规则 2:重启继续拒绝、人工核对后显式解除,复用/结算/只读照常)**+修正计价上界。receipt.cost_cny 为可重算投影,核清事务内顺带更新,失败不阻塞账本(投影可由 attempt 重算修复)。
9. **费用快照(三约束的物理实现)**:同一时点、同一只读聚合查询——`cost_cny`=该期(issue_date)全部 attempt 的 Σ(已核清取 actual,未核清取 reserved 保守值);`cost_pending`=是否存在任一 actual IS NULL 的 attempt(**覆盖所有未核清,不限 status=unknown**)。**零 attempt 期**(零候选/E2/全复用未发布)=cost_cny 0、cost_pending=false。算例:3 条已核清(¥0.0096+¥0.0096+¥0.0001)+1 条 received 未核清(reserved ¥0.0096)→ cost_cny=¥0.0289、cost_pending=true;核清最后一例为 ¥0.0090 后→¥0.0283/false(数字、标志、正文标注一起更新,经正常内容提交,digest-design §3.4)。账本更新不依赖站点发布成功。
10. **费用归属**:attempt 归属 issue_date;跨期复用不新增付费也不把旧费用计入新期快照;旧 attempt 归属不得为释放单期额度改期;重试是新 attempt 归原期。
11. **校准通道(第四轮入契约——plan 评审发现的付费例外必须先有设计再实现)**:
    - **例外范围唯一**:purpose='calibration' 是规则 2"校准未完成→拒绝新增付费"的**唯一显式例外**——它解决"未校准不得调用,却必须先调用才能取得校准数据"的执行循环;正式管线(score/understand)的授权前置=engine_meta 校准状态对**当前配置**生效(见下)。
    - **走完整账本,不设免检额度**:每次校准调用逐过授权闸门(窗口次数/金额/pay_paused),**月预算与窗口限额照常适用**;单列 `calibration.budget_micro_cny`(config,design.md budget.yaml;校准调用的**预占合计上限**,默认 50000 微元=¥0.05,耗尽即中止不追加)——小额只限制"按预占值批准的调用量",不自动保证实付不超,故仍受对账硬失败处置(规则 2)约束。
    - **校准记录绑定配置,不可跨配置沿用**:engine_meta 校准状态必须记录 {model, tokenizer 资源与版本, 消息计数方式, 校准系数, 样本对账结果, 判定时刻}——**当前配置任一项变化(换模型/换 tokenizer 资源或版本/改计数方式/改系数)即失效,须重新校准**;不得只存一个可跨配置沿用的全局 passed 标志。
    - **初始系数依据**:使用模型方官方 tokenizer 资源(资源即服务端分词器)时初始系数=1.0;**无官方资源时不预设默认系数**——必须先建立"近似资源+系数能覆盖目标 API 输入计量"的依据(来源、版本、覆盖论证),**建立不了则停**(不进入付费);若以近似资源做小额探索,该探索是**尚未验证上界的小额实验**,不得表述为"已建立保守上界";四个样本通过只证明这四个样本未超预占,不把近似计数器升格为已证明上界。
    - **通过条件**:全部样本 usage.prompt_tokens≤预占计数→校准状态对当前配置生效;任一超出→停新增(置 pay_paused,同规则 2)+上调系数(人工确认后重新校准)。

## 4. 输入输出

**输入**:manifest 成员(单元一;含 content_hash)、identity_ctx(单元三生产:prompt 版本/model/参数/**截断后实际输入**)、budget.yaml、budget 表、receipt/receipt_attempt/analysis/summary 现状、供应商账单证据(核清时)。

**输出**:
- `N_new`(int ≥0;design.md 公式,输入=预算参数与窗口余量);
- **复用快照**(reusable_scores 结果:{identity_key → {score_1, score_2, needs, analysis_ref}};给编排层→预筛);
- 结算回执+analysis/summary 业务行(与单元三同事务,交界协议见其 §5);
- 期费用快照(cost_cny + cost_pending 单查询;零 attempt=0/false);
- api_usage 月投影(报表,不作授权依据)。

**非法输入处置**:budget 行缺失=E1 拒付费(design.md 加载契约);价目版本缺该 model=E1;账单证据不足→不核清(保持未决);identity_ctx 字段不全→拒绝发起调用(E1 类配置缺陷)。

## 5. 数据与状态(表操作协议;spec §5.3 现为 12 表,本单元涉 4 表)

| 操作 | 事务边界 | 写入 |
|------|----------|------|
| 授权 reserve | 短事务 BEGIN IMMEDIATE→COMMIT 后出网 | receipt_attempt(**attempt_no=该 logical_key 既有计数+1**:score-1/score-2/understand 各自独立序列,重启不重置, pending, reserved, issue_date, started_utc, pricing_version,**attempt_origin**(initial=该 logical_key 首行/retry=普通重试/unknown_retry=unknown 通道));首 attempt 同事务建 receipt 行 |
| 响应回写 | 单事务 | receipt_attempt→received+usage_json+actual_micro_cny(可结算时);receipt.response_json/status→received |
| 业务完成 | **与单元三同一事务** | receipt.status→completed + analysis/summary 行 + entry 状态/占用(生产方=单元三,见其 §5) |
| 失败/未知 | 单事务 | attempt→failed(有 usage 则结算)/unknown(预占保留)**+error_class(no_retry/retryable/unknown,矩阵映射)+fail_detail_json 同事务写入**;receipt.status 同步 |
| 复用 | **无事务(只读)** | 无写入;logical_key 查询 |
| 核清 | **单事务 UPDATE** | attempt.actual_micro_cny + reconcile_json(证据四要素);receipt.cost_cny 投影顺带更新;api_usage 重算该月行 |
| 月投影 | 幂等重算 | api_usage(月,provider,model)聚合行 |
| 校准执行(规则 11) | 每次调用同授权/结算事务;状态记录单事务 | attempt(purpose='calibration')照常预占/结算/计入窗口与月预算;engine_meta 校准状态{模型/资源版本/计数方式/系数/结果/时刻}——配置变化即失效 |

**关键决策与理由**:
- **复用判定放单元二而非预筛内**:判定需要请求身份构造与 receipt 语义,属费用域知识;预筛消费只读结果保持纯函数与等价输入可测性(同 manifest+同占用/override/**同复用快照**+同 N_new→同输出)。
- **可复用≠可组装**(进度分级):"全部完成/部分完成"都保留进度,但组装就绪=评分双齐+摘要齐+安全过(单元三判据);recoverable 只免除"重发已收到的请求",不豁免任何新增调用的授权。
- **核清证据落 reconcile_json 而非独立表**:证据与 attempt 一对一,同事务保证"改 actual 必留证据";独立表需第二事务反而引入中断窗口。DDL 已同步 spec §5.3。
- **快照单查询**:约束①(同时点同源)的物理保证=一条 SQL 的同一读事务。

## 6. 异常与恢复

| # | 场景 | 现场状态 | 恢复判定与动作 | 费用 |
|---|------|----------|----------------|------|
| A | 授权后出网前崩溃 | attempt=pending(已预占) | 无已持久化响应→转 unknown(不视为未发送免费重试) | 预占保留 |
| B | 响应已落库、业务未写 | receipt=received;attempt 已结算 | 续跑按身份复用 received 响应→补写业务(零网络) | 已结算不重付 |
| C | 写入选前中断(评分完成未 selected) | analysis/received 在,entry 未 selected | 复用快照 needs=∅→recoverable→下游零网络重新判断入选 | 零 |
| C' | 双次评分只完成一次 | 一条有效响应在 | needs 补缺失那条(过闸门);不重发已完成侧 | 仅补发侧新增 |
| D | unknown 到期 | attempt=unknown≥30min | 名额未用→一次自动重试(标志+新预占同事务);已用→转人工 | 旧占用保留 |
| E | 预算停用(E5.limit) | 限额≤0 或闸门拒绝 | to_score 停增;可复用/needs/摘要内工作按各自授权走;已有合格条目组装发布 | 已发请求照常结算 |
| F | 供应商实付>预占 | 核清时发现 | 停新增调用+修正计价上界+记账实付;提示已发布期数字过期(更新走单元四纠错提交) | 不截断数字 |
| G | 跨期正文刷新 | entry 新 content_hash;旧 attempt 旧 hash | 身份已变:旧响应不可复用于新输入,旧费用保留归原期;新评分走新授权 | 旧费用不退 |

## 7. 验收场景(M1 plan 强制测试种子;输入→期望)

1. **复用判定矩阵**:同身份 completed→可复用;prompt 版本变→不可;**截断标记差异(实际输入变)→不可**;received 过完整 E4 验证器→可;received 不可解析→不可(走 E4);**received 且 finish_reason=length 而 JSON 恰好可解析→不可**(非正常终止,走 E4)。
2. **N_new 作用顺序**:10 合格成员中 4 条可复用+6 条需新增,N_new=4 → 4 recoverable+4 to_score+2 capped;N_new=0 → 4 recoverable+6 capped,**无成员丢失**。
3. **部分完成恢复**:score-1 有效、score-2 缺失 → needs=[score-2] → 仅补发 score-2(**若 score-2 该 logical_key 从未发送则其 attempt_no=1;已有失败/unknown 则按其自身计数顺延**;断言不重发 score-1);重启后计数连续不重置。
4. **身份变化的 selected**:prompt 升级→两条均无效→参与排序;落 capped 可见,不静默。
5. **三分行为**:N_new=0(可复用照常)/限额置 0(N_new=0 且闸门拒绝)/闸门单次拒绝(该条跳过,他条不受影响)——三路径分别断言;摘要预留内调用被金额拒绝→跳过该条(强制项→暂停联动,接口断言)。
6. **授权闸门**:小时窗口将满→新增 attempt 被拒(不写预占);复用查询不计窗口次数。
7. **unknown**:替身时钟+进程中断→30min 从 started_utc 起、标志持久化、二次转人工;不因重启重置。
7b. **耗尽不重获额度**:同身份普通重试达上限后重启→仍视为耗尽(不再自动发起,断言零新增 attempt);仅 prompt 版本/输入变化(新 logical_key)才从 attempt_no=1 起。
7c. **名额不可互借(第二轮核验反例)**:max_attempts=2、同 logical_key 两次**普通**可重试失败、unknown_retry_used=0→重启后断言零新增 attempt(总数 2<3 不构成发送许可);仅当存在满足等待条件(≥30min)且名额未用的 unknown 时才允许一次额外重试;**HTTP 400 类不可重试失败计数未满→断言不再自动调用**;同一判定在"部分完成补缺失"与"均未完成重跑"两路径分别断言。
7d. **持久化重放判定(第三轮核验反例;第四轮修正 origin 语义,替身 HTTP,零真实付费)**:同一请求首 attempt 分别注入 HTTP 400 与 HTTP 503 后**落库并关闭连接**→重新打开 DB 仅凭行数据判定:400→`error_class='no_retry'` 断言拒绝自动重试(计数未满也拒);503→`error_class='retryable'` 按普通剩余名额判定;普通耗尽+unknown 名额未用→仍拒(不互借);**origin 授权语义序列(第四轮表)**——attempt1 首次调用超时未知→`initial/unknown`;attempt2 满足等待条件的 unknown 额外重试返回 503→**保持 `unknown_retry/retryable`(不因返回类型改写授权来源)**;attempt3 普通名额仍有剩余而继续调用返回 503→`retry/retryable`(新授权计入普通尝试已用数);**普通尝试已用数=`origin IN ('initial','retry')` 行数,不按 error_class 过滤(initial/unknown 与 initial/retryable 同样各占一个普通名额,断言两者计数一致)**;失败更新事务只写 error_class/fail_detail_json,**断言不改写 attempt_origin**;`fail_detail_json` 含 http_status 与矩阵子类;判定函数无内存依赖(两次独立进程/连接实例断言一致)。
8. **费用快照单查询**:3 settled+1 未决(含 1 条 received 未核清的非 unknown)→ cost_cny=Σ(3 actual+1 reserved)、cost_pending=true;**零 attempt 期→0/false**;两值断言出自同一查询(查询计数替身)。
9. **核清**:证据四要素齐→actual+reconcile_json 同事务落账、月投影更新、下期月可用变化;**证据缺失→拒绝核清保持未决**(断言 actual 仍 NULL);核清后已发布期数字过期提示产生(内容更新属单元四验收)。
10. **跨期复用费用归属**:上期 attempt ¥0.01 已结算,本期复用→本期快照不含该 ¥0.01,上期快照不变。
11. **校准通道(规则 11,第四轮,替身)**:校准状态对当前配置未生效时正式管线(score/understand)→断言零新增付费 attempt(例外仅 calibration purpose);校准调用在账本中有预占/结算行且**计入窗口次数与月预算**(不绕闸门断言);`calibration.budget_micro_cny` 耗尽→中止不追加;**换模型/tokenizer 资源或版本/计数方式/系数任一项→校准状态失效,正式管线重新拒绝新增(须重校准)**;样本 usage.prompt_tokens 超预占计数→停新增置 pay_paused 断言(持久化,重启仍拒)。

## 8. 依赖与维护成本

- 零新增依赖:httpx+sqlite3 既有契约;零新表(reconcile_json 为 receipt_attempt 扩列);无新服务。
- 复用判定查询按 logical_key 精确匹配(receipt UNIQUE 索引),attempt 窗口聚合走 idx_attempt_started。

## 9. 未决项

| 未决项 | 验证方法 | 通过条件 | 失败后的备选 | 定位 |
|--------|----------|----------|--------------|------|
| ~~analysis/summary 与 receipt completed 事务交界~~ | **已定稿(单元三 §5)**:同事务写入 | — | — | 已闭环 |
| ~~对账证据存储与事务边界~~ | **已定稿(本文 §3 规则 8/§5)**:reconcile_json 与 actual 同事务 | — | — | 已闭环 |
| ~~通知去重键持久化~~ | **已定稿(单元五)**:notify_sent 表 | — | — | 已闭环 |
| M2 并发时的请求所有权/超时机制 | M2 计划 | 不把活跃调用误改 unknown | 进程级租约 | M2(既定延期) |
| 1:1 字符上界的实际充分性 | **已废止**(第二轮核验:官方换算仅"大致比例",推不出 1:1 上界;字符比例退出授权链,方案改 tokenizer 计数,见规则 2/单元三 §3 规则 5) | — | — | 已改方案 |
| tokenizer 选型与校准有效性 | M1 实施第一步:选定与 API 模型匹配的 tokenizer 资源(模型方发布渠道,版本固定进 config)+样本对账定校准系数;运行期持续对账;**校准通道契约=规则 11(第四轮定稿)**:官方资源初始系数 1.0,无官方资源不预设系数、建立不了覆盖依据则停 | 零超预占事件(**任何超=置 pay_paused 停新增+修正,无容忍个位**) | 更换 tokenizer 资源/调校准系数/下调 max_input_tokens | 待实施验证(核对+对账) |

## 评审提示

v2 落实三组评审修正:①请求身份覆盖**实际发送的有效输入及参数**(截断后文本入 hash);复用判定与首次消费**同一有效性规则**(共用 request_hash 构造,消费按判定返回的引用);analysis/summary 以 receipt_ids 关联回执核对身份。②双次评分**全部/部分/均未完成**三分+恢复表(needs 只补缺失、计数不重置)。③N_new=0/合法停用/逐次授权拒绝**三分表**;预留不构成调用许可。核清证据=reconcile_json 与 actual 同事务;费用快照算例与零 attempt 结果补齐。首轮联合核验修正(保持):复用有效性纳入**完整 E4 验证器**;"均未完成"拆未耗尽/已耗尽;attempt 计数粒度=**logical_key 独立**。**第二轮核验修正(v3)**:预占改 **tokenizer 计数**——字符比例(含 1:1)退出授权链,计数不可得→不出网,对账超计数=停新增+修正(删"孤立个位可忽略");**再发送三条件**(错误类别允许/类别名额剩余且普通与 unknown 不互借/硬上限+当次授权),反例=max_attempts=2 两次普通失败不因 2<3 而续发;pay_paused 检查=仅显式 0 放行、键缺失同拒。占用写入释放已在单元三定稿(entry.claim_issue)。**第三轮核验补齐(v4,名额公式已被第四轮修订)**:重试判定持久化契约——`attempt_origin`(预占事务)/`error_class`+`fail_detail_json`(失败更新事务,矩阵映射 no_retry={E1.request,E4.terminal,E5.balance}/retryable={E3.http,E4.parse}/unknown={E3.unknown});重启仅凭 DB 重放判定(验收 7d:400/503 同为 failed 未核清,靠 error_class 区分)。**第四轮核验修正(v5)**:①`attempt_origin`=授权语义,**预占后不可改写**(unknown 通道重试返回 503 保持 unknown_retry;再发起普通重试是新授权 origin='retry');**名额唯一口径改为**普通尝试已用数=`origin∈{initial,retry}` 行数(**不按 error_class 过滤**——名额按授权消耗,initial/unknown 同样占一个普通名额),error_class 只决定能否再发送与通道;②新增**规则 11 校准通道契约**(例外唯一/完整闸门+月预算窗口照常/记录绑定模型+资源版本+计数方式+系数,配置变化失效/**初始系数:官方 1.0、无官方不预设、建立不了覆盖依据则停**);③对账硬失败停新增=**持久化置 pay_paused** 记录原因(同备份恢复闸门,人工解除)。
