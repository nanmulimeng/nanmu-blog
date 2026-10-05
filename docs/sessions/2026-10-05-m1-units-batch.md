# 会话交接:M1 第 3 步五单元批量闭环轮(2026-10-05)

- **recorded_at**: 2026-10-05 Asia/Shanghai
- **continues**: [单元二设计+单元一回填](2026-10-05-unit2-model-calls.md)
- **repository**: main;本轮一个提交(五单元批量闭环,见 git log),未推 origin/server。
- **objective**: 按用户批量闭环指令,一次完成:①单元一/二遗留修正(请求身份覆盖实际输入/双次评分三分/N 三分/核清证据存储定稿);②单元三/四/五设计;③交付前自走 8 组端到端场景推演并修矛盾;④五单元+spec/DDL/公共契约一致性同步。

## change_scope

**① spec §5.3 扩为 11 表(存储映射一次性定稿,不留 M1 plan)**:entry.`claim_issue`(占用归属);receipt_attempt.`reconcile_json`(核清证据四要素与 actual 同一 UPDATE 事务);digest_issue 扩 6 列(fail_reason/updated_utc/last_exit/last_run_utc/withdrawn_utc/withdraw_commit);issue_freeze 加 paused 三列;**summary 表**(第 10,摘要结果与 analysis 对称 append-only);**notify_sent 表**(第 11,dedup_key 主键)。check_docs expected 同步,内存 SQLite 实际执行 DDL 验证。

**② 单元一/二修正**:model-calls.md v2 全量重写——请求身份 request_hash 覆盖模板实例化后的完整 system+user 实际文本(截断后),预占按 max_input_tokens 上界与截断解耦;复用判定与首次消费同一有效性规则(共用构造);analysis/summary 以 receipt_ids 关联回执核对身份;双次评分全部/部分/均未完成三分(部分=needs 只补缺失、计数不重置);N_new=0/合法停用 E5.limit/逐次授权拒绝三分表,预留不构成调用许可;费用快照算例(3 settled+1 未决=¥0.0289/true;核清后 ¥0.0283/false)+零 attempt 期=0/false。data-ingestion.md 回填微调(规则 8/输出③/验收 9b/§9 闭环)。

**③ 新增三单元**(docs/engine/units/):
- **content-editing.md(单元三)**:占用协议五事件表+不变量(selected⇒claim 非空);analysis/summary 与 receipt completed 同一事务+崩溃窗口幂等重放;prompt 权重初版(五轴×六类型权重表+两清单+虚构样例自检:6/5/8/7/7 工程实践→70 分 T1 一瞥);字符预算 2×max_input_tokens 截断(截断后文本入 hash);组装就绪五判据(recoverable 不豁免);安全输出(字面文本/HTML 转义/URL scheme 白名单)。
- **publish-withdraw.md(单元四)**:published 证据=线上 release.txt 包含提交+URL 可读+内容身份一致+排除后续删除;三中断窗口恢复(先查远端线上后补记);跨期隔离检查;撤回四步(暂停→删→三处验证→withdrawn 落库);重新上线两条零模型;核清后过期提示+人工纠错(不自动改已发布内容,决策+理由)。
- **scheduling-ops.md(单元五)**:运行序(锁→config 校验→恢复存量升序、期内 submitted 只读确认→draft 恢复→生成中续跑→当天新期→汇总);"1 个后续调度日"=D 与 D+1 两个触发窗、frozen_utc 运行时计算不加列;暂停/解除/failed 人工重跑/放弃期命令语义;spec §5.3.1 恢复字段映射收口表;通知去重键规则(子类+期/月/配置 hash;立即类不去重);status 五组事实清单;备份边界(engine.db 全量+config+prompts,不含 site/上游/rag.db)。

**④ 公共契约同步**:design.md score.py 行加 claim_issue 同事务、summarize.py 输出改 summary 表;pipeline.md 数据落点 9→11 表;digest-design.md §7 未决项表批量闭环(占用/暂停存储/prompt 权重结构三条划线)+评审提示更新;spec 变更记录加批量轮条目。

## 端到端场景推演(8 组,文档推演+未来验收设计;非已通过的运行测试)

每组核对:输入→状态变化→持久化事实→下一步动作→是否新费用→最终可见结果。

**① 正常全链+少量/零候选/零合格**
正常:08:30 触发→锁→校验→无存量恢复→新期 collect(48h 窗口 34 条→判重合并→单事务 entry upsert+资格过滤+issue_freeze INSERT)→预筛(复用快照+N_new=12)→to_score 12 条各 2 attempt 过闸门→analysis 双分+selected+claim_issue 同事务→摘要逐条过闸门→summary 行→组装五判据→draft 落盘+digest_issue draft 行→隔离检查→push→submitted→线上确认→published 同事务 used+claim 清→收尾 last_exit/last_run_utc。费用=24 评分+15 摘要 attempt 结算归本期;可见=日报页+cost 快照。少量候选(5 条)同链路。**零候选**:freeze(entry_count=0)→下游 digest_issue failed(no_candidates),零 attempt,cost_cny=0/pending=false,通知按 E 类去重。**零合格**:评分全完成但均未过线→组装记 zero_qualified failed(单元五落行),已结算评分费用照记(该期 cost 真实非零)。✅一致。

**② 三种中断形态**
采集事务中断:无 issue_freeze 行(单事务回滚,entry 无半写)→重跑从头采集(窗口=重跑时刻)。冻结后评分中崩溃:行在→下次触发运行序恢复该期(生成中)→读 manifest 续跑→已收响应按身份复用,未发起的不重发已完成侧。新期刷新 entry 后旧期续跑:entry.content_text 新值但旧期 manifest 快照旧值→旧期请求身份不变→旧回执复用;entry_id 链接仍有效。✅一致(单元一 A/C/D 行)。

**③ 双次评分与业务落库的三种半途**
只完成一次:一条有效→needs=[score-2]→仅补发 score-2(attempt_no=2 续),不重发 score-1。响应落库业务未写:receipt=received→续跑按身份复用 received 响应重放业务事务(先查 analysis 无同身份行,幂等)。评分完成摘要未完成:组装判据 b 不满足→不组装;续跑摘要阶段按授权补发;强制项此态→暂停转人工。✅一致(单元二 B/C/C'、单元三 A-C)。

**④ 复用/身份变化/预算耗尽/合法停用**
跨期复用:上期已评分身份未变→本期 recoverable,费用留原期,本期快照不含旧费用。身份变化(prompt 升级):旧响应不可冒充→均未完成→参与 N_new 排序,被截断则 capped 可见,组装边界按"曾 selected 无当前有效评分"暂停联动。预算耗尽 N_new=0:to_score 空,recoverable 照常,capped 全可见,不丢可恢复工作;已有合格条目照常组装发布(E5.limit 口径)。合法停用(限额≤0):N_new=0 **且**闸门拒绝一切新增;复用/结算/发布照常。✅一致(单元二规则 4-6、恢复 E/G)。

**⑤ 重试与核清**
unknown 30min(从 started_utc 起):一次自动重试(标志+新预占同短事务);二次转人工;跨月未决继续占用不释放。普通重试耗尽:E7 跳过该条,费用照记;强制项例外转单元三暂停。核清:账单证据四要素齐→actual+reconcile_json 同一 UPDATE 事务,月投影更新;证据不足拒绝核清保持未决。核清致已发布期快照变→过期提示清单→人工纠错提交一次改数字/标志/正文标注三处(digest-design §3.4),零模型费用。✅一致(单元二规则 7-8、单元四规则 8)。

**⑥ 强制项与占用**
强制项被截断(落 capped):PrescreenResult 全覆盖保证可见→组装边界发现未完成评分→暂停转人工,不静默发布缺强制项日报。强制项评分/摘要失败:同暂停。人工排除:override exclude 命中本期 selected→移出组装、其余照常重组装(已付费复用零新增);**期发布时**该成员 rejected+claim 清(见下方矛盾修正 1)。占用释放两路径:放弃 failed 期(claim 清、status 回 scored、used 不动、留痕)/期正常发布(进产物 used+清、被排除 rejected+清)。✅修正后一致。

**⑦ 发布三窗口**
commit 成功 DB 未记 draft:副本 git log 有该期内容身份提交、无 draft 行→补记 draft(复用提交不重组)。push 成功状态仍 draft:ls-remote 含 git_commit→补记 submitted。上线成功未记 published:线上证据齐→补记 published+used+claim 清(幂等,重复恢复不重复置 used)。线上确认失败(E9):保持 submitted 只重查,不重做评分/摘要/重组。✅一致(单元四规则 2-3)。

**⑧ 跨期人工态与撤回**
旧期待人工时新期运行:待人工旧期**无未推送提交**(撤回已 push 完/暂停期无产物文件)→不阻塞,新期照常生成+发布;若旧期有未推送提交→新期不 push 转人工(见矛盾修正 2)。撤回期间离线纠错:paused 已置位→无自动重发路径;纠错在副本修正暂不上线→暂停标志保持。显式重新上线:原样恢复(取撤回父版本内容身份)/修正后恢复(一次新提交),均零模型、显式命令+留痕,used 保持,withdrawn 史实保留(status 展示 published withdrawn=relisted)。✅修正后一致。

**推演发现并修正的两处矛盾**:
1. **published 期被 exclude 的 selected 成员无 claim 清路径**(单元三原 §6 E"保持 selected+claim 至本期终态"只写了放弃路径;期发布后 claim 挂在已终态期上,新期预筛按"他期占用"永久排除,违反 digest-design §4.6"落选次日可再入围")→修正:published 同事务进产物者 used+claim 清、未进产物者 rejected+claim 清+日志(单元三规则 7/E、单元四规则 2,两侧验收补断言)。
2. **隔离检查阻塞条件过宽**(单元四原规则 4"无待人工处理标志"把 digest-design §4.6"不得意外**带出**待人工旧期内容"扩大为"存在待人工标志就不 push",新期被无关阻塞)→修正:阻塞=其他期未推送提交会被带出/变更集含他期文件;待人工旧期无未推送提交不阻塞。

## key_decisions(自主处理的常规选择,附理由)

| 决策 | 理由 |
|------|------|
| 核清证据=receipt_attempt.reconcile_json(与 actual 同 UPDATE 事务) | 证据与 attempt 一对一;独立表引入第二事务窗口 |
| 摘要结果=summary 第 10 表(append-only,与 analysis 对称) | 可追溯+身份关联复用;覆写 digest_issue 列会丢历史 |
| 通知去重=notify_sent 第 11 表(dedup_key 主键) | 发送结果持久化、重启不重置;轻表零依赖 |
| 自动恢复资格不加列(frozen_utc 运行时计算) | 状态双写漂移风险>查询成本;单实例下判定廉价 |
| published 事务处理被排除成员(修正 1) | 无清路径=永久误占用;rejected 保留评分事实符合落选语义 |
| 截断字符预算 2×max_input_tokens 与预占解耦 | 保守性由预占全额保证;字符换算精度不影响账本 |
| prompt 权重初版六类型表+虚构自检(两分法) | 确定性部分可自检;质量只能真实样本验证,不编造 |
| 核清后不自动改已发布内容 | 自动改线上内容风险>数字滞后;M1 接受滞后+runbook 巡检 |

## open_items

**设计未定(无)**:五单元 §9 原"设计未决"项全部闭环(占用/事务交界/核清证据/通知去重/恢复字段映射)。

**待实施验证(不阻塞设计评审)**:prompt 文案与评分质量(真实样本,获准试运行后);截断充分性;线上确认轮询参数;撤回缓存时延;通知渠道凭据(部署核查);备份频率终值(试运行观测);上游 fetched_utc 分布与服务器权限(部署核查);M2 并发所有权(既定延期)。

## state

- 五单元+spec/design/pipeline/digest-design 同步完成,**待用户跨单元联合核验**(不逐份等待)。
- M1 plan 未编写、编码暂停、未推送,继续有效。
- 用户核验重点自查:错误发布(强制项可见性/隔离检查/安全输出已覆盖)、重复付费(身份复用/同规则判定/幂等重放已覆盖)、恢复失败(三窗口+运行序+截止判定已覆盖)、越界(待人工旧期不阻塞新期/published 清 claim 修正已覆盖)。

## verification

| 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
|--------------|----------------|--------------|
| 仓库根 | `python scripts/check_docs.py --snippets --bash … --node …` | 见当轮输出 |
| 仓库根 | `git diff --check` | 通过 |

- **disposition**: continuable(等用户跨单元联合核验)
- **next_action**: 用户核验五单元与 8 组场景推演;通过后再谈 M1 实施计划编写(仍不自动恢复编码)。
- **omissions**:
  - llm.py HTTP 契约/DeepSeek 调用细节未在单元文档重复(design.md/budget.md 既有)。
  - 命令形态(run/resume/abandon/pause/unpause/status)与测试实现细节留 M1 plan(本文已定语义与序列)。
  - 用户侧待办不变(skills DNS/ICP/origin 推送/验收目录清理/Task10);线上仍 c8a4567。

## erratum(2026-10-05 联合核验后追加,原文不改)

用户联合核验指出本文两处推演数字不成立,更正如下(作为未来测试输入时不得沿用原数字):

1. **"12 条评分候选 → 15 次摘要调用"推导错误**:摘要调用量由入选条目数(max_entries=15 上限内)决定,不由评分候选数直接推出;该场景行中"15 次摘要调用"应改为"按实际入选条目数逐条调用"。此外当时按"12 候选×2 评分"计 24 次评分 attempt 的口径保留,但**任何场景中的摘要次数都必须重新按入选结果推算**。
2. **"补发 score-2 记为 attempt_no=2"错误**:attempt_no 按 logical_key 独立计数(score-1/score-2/understand 各自序列);score-2 从未发送时其首次发送 attempt_no=1,不因 score-1 已有一次而顺延。原文把"该条第 2 次调用"误写成"score-2 的第 2 次 attempt"。计数契约以 units/model-calls.md §3 规则 5/§5(核验修正轮)为准。

受影响的下游表述已在核验修正轮统一修正;本文其余内容保持原样作为历史记录。
