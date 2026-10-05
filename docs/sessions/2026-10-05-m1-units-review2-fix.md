# 2026-10-05 五单元联合核验修正轮

## background

- 用户完成五单元首版联合核验:结论"具备完整设计稿形态,但不能确认设计未定项为零,暂不进入 M1 实施计划";记录口径=**"五单元首版联合核验完成,存在集中待修问题"**。
- 用户以七组问题+prompt 缺口+两处推演数字错误下达批量修正指令(一次修正+自审+统一交付,不逐条等待确认);已通过的冻结/窗口/去重/费用快照/11 表规模等不重开。
- 本轮范围锁定为用户所列问题,不扩展功能;修正后按用户要求**用反例重走链路**,重点检查真实副作用发生前后、数据库落事实前后的中断窗口。

## 修正清单(逐反例:修订后状态 / 账本 / 文件 / 下一步动作)

### 反例 1:字符截断不能保证 token 上界(4000 tokens→8000 字符推论不成立)

- **修订后状态**:字符比例降级为"截断执行器",不再作为费用授权证明。授权证明链=**1 字符=1 token 保守上界**:截断保证完整请求(system+标题+正文+截断标记)总字符数 ≤ max_input_tokens,迭代截断后重数,发送前再数一次超界即拒绝;system 自身超限=config 校验 E1;超长标题/截断标记占用同入预算。依据:DeepSeek 官方中文≈0.6 token/字、英文≈4 字符/token,1:1 同时覆盖两者最坏情况。闭环结论:**实付输入 ≤ 预占**。
- **账本**:预占(max_input_tokens 上界)≥实际发送字符数≥实际 token;usage.prompt_tokens 响应后对账,超预占记警示日志(§9 观测项:1:1 充分性,失败备选=引入离线 tokenizer 或下调 max_input_tokens)。截断不可行的条目走普通项失败处置(反例 6),不产生调用不产生 attempt。
- **文件**:units/content-editing.md §3 规则 5;units/model-calls.md §3 规则 2;model-calls §9 观测项。
- **下一步动作**:M1 plan 测试种子=验收 3(content-editing):超长正文迭代截断后完整请求字符数断言 ≤ 预算;发送前重数拒绝路径断言;system 超限 E1 断言。

### 反例 2:回执恢复三缺口+备份恢复重复付费

- **修订后状态**:①"均无有效响应"拆为**未发起/未耗尽**与**已耗尽**:同 logical_key 重试耗尽后重启继续原计数、不再自动发起(不重获额度),仅新 logical_key(身份变化)或人工显式操作才有新调用;②**attempt 计数粒度=logical_key 独立**(score-1/score-2/understand 各自序列,对齐 budget.md L20/pipeline.md 既有契约):score-2 从未发送则首次发送 attempt_no=1(批量轮验收 3 的"固定 attempt_no=2"已修,session 附 erratum);③**复用有效性=完整 E4 验证器**(身份匹配+status∈{received,completed}+finish_reason=stop+JSON 契约全过):finish_reason=length 而 JSON 恰可解析→不可消费,走 E4 处置;④**备份恢复**:restore-backup 命令恢复整库+置 engine_meta.pay_paused=1(第 12 表),闸门置位即拒一切新增付费(复用/结算/只读照常),人工核对恢复点之后的调用与账单后显式解除;裸文件恢复=runbook 违规。
- **账本**:中断窗口走查——授权(COMMIT 后)→出网前崩溃=attempt pending 转 unknown 预占保留不重发;响应落库(received+结算)→业务未写=续跑零网络复用补写业务,已结算不重付;恢复旧库丢回执=若无闸门会"查无回执按从未发起重发重复扣费",现由 pay_paused 拦截为零新增,核对后再放行。
- **文件**:units/model-calls.md §3 规则 1(pay_paused)/规则 3(E4 验证器)/规则 5(完成度表拆行+计数列)/§5(授权行 attempt_no 语义);units/scheduling-ops.md §3 规则 9(restore-backup)+§6 G;spec §5.3 engine_meta。
- **下一步动作**:M1 plan 测试种子=model-calls 验收 1(length 不可复用)/3(score-2 首发编号)/7b(耗尽不重获额度);scheduling-ops 验收 8(restore-backup→闸门拒新增+核对解除)。

### 反例 3:字面文本转义挡不住 Markdown 语法(`[伪装链接](url)` 仍渲染 `<a>`)

- **修订后状态**:按上下文分治——模型文本字段(中文标题/一句话/推荐理由/标签)按 **Markdown 文本上下文**转义(控制字符 strip+CommonMark ASCII 标点集 `` \ ` * _ { } [ ] ( ) # + - . ! < > | ~ `` 全集,非仅 `<>&`);来源 URL 按**链接目标上下文**构造(scheme 白名单 http/https+括号/空白/反斜杠/百分号编码或 `<url>` 尖括号形式;模板生成链接的 URL 不进入正文文本流)。结构化生成(模板拼装)而非字符串拼接。
- **账本**:纯本地零成本,不涉 attempt;转义失败/无法安全编码的条目按安全失败走普通项失败处置(反例 6),不组装不发布。
- **文件**:units/content-editing.md §3 规则 10;pipeline.md 发布契约既有行(不重复)。
- **下一步动作**:M1 plan 测试种子=content-editing 验收 7:**渲染后 HTML 断言**(DOM 中无模型文本转义后残留的 `<a>`/可点击链接;URL 上下文编码断言),不只查 Markdown 字符串。

### 反例 4:发布撤回恢复证据未闭合(漏"SHA 未写库"窗口/线上是 HTML 不能比字节)

- **修订后状态**:①**content_sha256=draft 落盘时计算、随 draft 行同事务写入=不可变预期值**;git_commit **commit 成功即回填**(仍 draft);②中断窗口从三个扩为**四个**:W1(commit 成功无 draft 行)/W2(draft 在、SHA 未回填——比对基准=库内 content_sha256,非工作副本现状)/W3(push 成功仍 draft)/W4(上线成功未记 published);③**确定查找法**=按目标路径过滤提交、取树内文件 sha256=预期值的提交(非"最新");查找失败=未真正 commit→回单元三重组装(评分/摘要全复用零新增);④**线上证据链三步**:线上 release SHA 树内目标文件身份=content_sha256(git cat-file,绕开 HTML/字节不可比)→排除后续删除→URL HTTP 可读;⑤撤回/重新上线各补"远端成功而本地未记"恢复路径(按远端删除/恢复提交+线上三处状态补记两列);⑥**三态判定**:withdrawn 空=未撤回/withdrawn 非空 relisted 空=处于撤回/relisted 非空=已重新上线;当前在线状态=站点内容运行时核验,持久事实凭 DB 重启可复现。
- **账本**:四窗口全部零新增费用(只补记状态);重组装路径复用回执零网络;撤回/重上/纠错均零模型调用。
- **文件**:units/publish-withdraw.md §3 规则 1/2/3/5/7;spec §5.3 digest_issue 三列(content_sha256/relisted_utc/relist_commit+git_commit 注释)。
- **下一步动作**:M1 plan 测试种子=publish-withdraw 验收 2(**W2 断言:副本被人为改动后恢复仍以库内值查找**;W1-W4 各注入中断,评分调用计数为零)/验收 4、5(撤回/重上补记+三态重启复现)。

### 反例 5:旧期恢复可耗尽当日全部运行时间(1800s 挤占新期)

- **修订后状态**:①**恢复阶段总预算 recover_budget_s(默认 600s,config 运行参数)**:耗尽→保存未完期状态、退出恢复循环**继续当天新期**(不退出运行);②**新期保底**:当天新期至少一次完整 collect+生成,与恢复预算互不侵占;仅发布环节可因隔离/推送冲突转人工;③"先恢复后新期"的收益降为期望(旧期大多零成本),**保证来自预算上限+保底**;④**截止锚点唯一化=issue_freeze.frozen_utc**:自动推进限 D 与 D+1 两窗(D=frozen_utc 所在调度日);D+1 窗内已开始的执行可跑完;D+2 起不再自动开始;晚 push/状态更新/续跑次数不延长资格(全部不是锚点);submitted 只读线上确认不受限;到期→通知(去重)+移出自动清单。
- **账本**:恢复预算耗尽=零新增(仅推迟);到期移出清单=停自动零新增;新期照常走自身预算。
- **文件**:units/scheduling-ops.md §3 规则 1/2/3+§6 H;pipeline.md 恢复段(预算上限+新期保底引用);scheduling §9(recover_budget_s 观测项)。
- **下一步动作**:M1 plan 测试种子=scheduling 验收 1b(**旧期评分持续失败退避占满 recover_budget_s→断言新期仍完成 collect+生成**)、验收 2(frozen_utc 锚点+构造 D+1 才首次 push 的期→D+2 仍不自动推进)。

### 反例 6:普通条目失败隔离与占用/组装冲突

- **修订后状态**:①**最终产物集合**=入选集−{普通项失败}(摘要失败/安全失败/截断不可行/评分耗尽/数量裁剪);普通项失败=剔除+按原因分列日志,其余照常组装发布;②就绪判据对**最终集合**执行;强制项未完成或有效强制项>F(15)=唯一暂停类;最终集合空=failed(zero_qualified)非暂停——对齐 digest-design §5.2 基线;③**占用三态化**:中间暂离(override/重判落选/摘要失败/安全失败/裁剪)=状态不动保持 selected+claim;终态统一清算(与 published 同事务):进产物者 used+claim 清,未进者 rejected+claim 清(日志按原因分列:override_excluded/re_eval_rejected/summary_failed/safety_failed/count_capped,不再统一写 override_excluded_at_publish);放弃失败期=全部回 scored+claim 清;不变量=selected⇒claim 非空、无 rejected 持 claim 混合事实。
- **账本**:普通项摘要失败=该条已有评分 attempt 费用保留归期(不退不重算),剔除后不再产生摘要 attempt;发布事务=清算与 published 同一事务,窗口内崩溃重启后幂等重放(used 不重复置)。
- **文件**:units/content-editing.md §3 规则 6/7/9+§2 场景表;units/publish-withdraw.md §3 规则 2(published 行清算)。
- **下一步动作**:M1 plan 测试种子=content-editing 验收 6(**组合场景:普通成功+普通摘要失败+selected 重判落选→正常发布无残留误占用;换强制项失败才暂停**)、publish-withdraw 验收 1(未进产物者 rejected+claim 清+日志原因分列)。

### 反例 7:通知表与重试协议冲突(同 key 先 fail 后 ok→UNIQUE constraint failed)

- **修订后状态**:①同 key 写法=**UPSERT**:首现 INSERT,重试后 UPDATE result/sent_utc——dedup_key 主键即防重,不得另起行(用户内存 SQLite 实测二次 INSERT 必冲突);②**"立即通知"=发送时机**(E1/402/E8/E9/W1 发生即发不等连续 2 期聚合),不是"每次重跑重复发送"——立即类同样入表按 key 去重,与 pipeline 既有"按子类+issue_date 去重"并存;③**崩溃边界写明**:发送成功但结果未落库即崩溃→重启后同 key 重发至多多发一次,DB 主键防同期重复,不承诺外部 exactly-once(接受)。
- **账本**:通知不改变账本与旧站(既有);发送失败有界重试不产生模型费用。
- **文件**:units/scheduling-ops.md §3 规则 7+§6 E;spec §5.3 notify_sent 注释。
- **下一步动作**:M1 plan 测试种子=scheduling 验收 6(同 key 重试成功 UPDATE 原行断言无第二次 INSERT/无主键冲突;立即类同期重跑不重发;崩溃后不无限重发)。

### 反例 8:prompt 设计未完成组(文案留白/类型不一致/赞助规则私加)

- **修订后状态**:①**prompt 初版全文定稿**=content-editing.md 附录 A:score.md(防注入首段+六类型权重表+两清单+硬规则题文不符≤30、赞助≤20+输出契约 `{"attentionScore": 0-100}`)+understand.md(防注入+防幻觉+四字段 JSON 契约),fenced text 可执行非占位;②**类型/轴名统一**:六类型=selection.md 六类(模型发布/产品发布/工具教程/研究论文/行业事件/观点分析),五轴=selection.md 轴名(信息价值/新颖度/可信度/实用度/兴趣相关);③**赞助≤20 上游化**入 selection.md 硬规则(注明 2026-10-05 补入,此前仅存单元三未过编辑规则评审);④改 prompt 文案=版本变化=请求身份变化(logical_key 新建),旧响应不可复用费用保留;⑤权重表真相源=落地 config/prompts/score.md 文件,selection.md 指向;附录含自检样例(工具教程 6/5/7/8/7→7.05→71)。
- **账本**:prompt 版本纳入 request_hash;改文案后旧 attempt 费用保留归原期,新调用新授权。
- **文件**:units/content-editing.md 附录 A;selection.md(评分轴行+硬规则+调整记录)。
- **下一步动作**:M1 plan 把附录 A 文案落为 config/prompts/ 文件;评分质量验证=真实样本(获准试运行后),与"规则已写全"分开,不再合并为同一开放项。

### 反例 9:两处推演数字错误(12 候选→15 摘要;score-2=attempt_no 2)

- **修订后状态**:批量轮 session 末尾追加 **erratum**(不改写历史):①摘要次数按实际入选条目数推算,不由候选数直接推出;②score-2 首次发送 attempt_no=1(logical_key 独立计数)。受影响下游表述已在各单元文档修正。
- **账本**:无实际费用影响(推演数字,非运行事实);作为未来测试输入时不得沿用原数字。
- **文件**:sessions/2026-10-05-m1-units-batch.md(末尾 erratum 节)。
- **下一步动作**:M1 plan 测试种子的期望数字一律按修正后契约计算(摘要次数=入选数;attempt 编号按各 logical_key 独立序列)。

## 决策记录(本轮新增)

| 决策 | 理由 |
|------|------|
| 1 字符=1 token 保守上界(而非离线 tokenizer) | 闭合"实付≤预占"不引依赖;官方换算随分词变化不可作证明;充分性留观测+备选 |
| engine_meta.pay_paused 全局闸门(第 12 表) | 引擎无法自动检测文件级恢复;恢复旧库丢回执的重复付费只能操作纪律+闸门双保险 |
| 占用三态化(中间暂离不动+终态统一清算) | 消除"rejected 持旧 claim"混合事实;清算与 published 同事务不留第四窗口 |
| 截止锚点唯一化 frozen_utc(运行时计算不加列) | 多锚点=资格可被晚 push/状态更新无限延长;单锚点判定廉价 |
| 通知 UPSERT 而非"删旧插新" | 主键即防重;UPDATE 保首现时间线;最小修正 |
| relisted 两列三态判定(而非 withdrawn 单字段) | 单字段承载"已撤回/已重上"两义,重启后无法区分 |
| prompt 全文定稿入附录 A | "规则未写全"与"效果未实测"分离;前者本轮闭环,后者留试运行 |

## open_items

**设计未定(无)**:本轮七组问题+prompt 缺口全部闭环;五单元 §9 仅剩实施验证/观测类(线上轮询参数/缓存时延/通知凭据/备份终值/recover_budget_s 观测/1:1 充分性观测/评分质量真实样本/M2 并发)。

**待用户核验**:上表"修订后状态"是否兑现承诺的恢复行为(用户重点:中断窗口走查是否属实)。

## state

- 本轮全部为文档修正,未编码、未推送;commit 后本地领先 origin(既定模式)。
- 12 表 DDL 定稿(spec §5.3);check_docs expected 同步。
- M1 plan 仍未编写;评审通过≠自动恢复编码。

## verification

| 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
|--------------|----------------|----------------|
| 仓库根 | `python scripts/check_docs.py --snippets --bash … --node …` | 见当轮输出(12 表断言) |
| 仓库根 | `git diff --check` | 通过 |
| 用户侧只读复验 | 通知 UPSERT/Markdown 转义两项 | 用户已实测(UNIQUE 冲突/`<a>` 渲染),本轮为设计修正非复测 |

- **disposition**: continuable(等用户核验关键反例)
- **next_action**: 用户按反例清单核验修订;通过后转 M1 实施计划评审(编码仍需用户明确恢复指示)。
- **omissions**:
  - 本轮未运行任何模型调用/引擎/服务器测试(设计轮);全部验证为文档一致性检查。
  - 用户侧待办不变(skills DNS/ICP/origin 推送/验收目录清理/Task10);线上仍 c8a4567。
