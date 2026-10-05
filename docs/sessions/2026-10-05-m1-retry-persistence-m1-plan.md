# 2026-10-05 第三轮核验修正(重试持久化契约)+ M1 实施计划待评审稿

## background

- 接续 [review3-fix](2026-10-05-m1-units-review3-fix.md)(第二轮核验修正,fb63674)。用户第三轮核验结论:①输入计量设计路线、③发布操作、④备份恢复、⑤通知承诺**通过关闭**(边界:tokenizer 与校准仍待验证,不得表述为"费用上界已实测成立");②重试授权判定规则通过,**但持久化映射缺最后一处 P1**——"最近失败错误类别/可重试计数/unknown 名额"三输入在 DDL 中无确定落点,400 与 503 同为 `attempt.status=failed` 费用未核清,重启后无法区分禁发与可发。
- 交付范围锁定(用户指定):"②的持久化契约补齐及引用同步 + M1 plan 待评审稿"**同批交付**,不再为单个文字修订单独等待一轮;plan 只编排实施顺序、依赖、验收和失败后的停点,不复制另一套设计。
- 已通过四项保持关闭,不重开;不扩表不新增抽象。

## 交付一:②重试判定持久化契约(唯一 P1,三要素)

### 要素 1:每个 attempt 保存规范化错误类别

- **修订后状态**:receipt_attempt 加三列(**小列方案,12 表数不变**)——`attempt_origin TEXT NOT NULL CHECK(in ('initial','retry','unknown_retry'))`(授权来源,**预占事务写入**:initial=该 logical_key 首行/retry=普通重试/unknown_retry=unknown 通道);`error_class TEXT CHECK(in ('no_retry','retryable','unknown') OR IS NULL)`(成功留 NULL;**失败或 unknown 状态更新同一事务写入**,由 llm.py 响应处理产出,映射自错误矩阵子类:no_retry={E1.request(HTTP 400/401/422), E4.terminal, E5.balance(402)}/retryable={E3.http(429/500/503), E4.parse}/unknown={E3.unknown});`fail_detail_json TEXT`({http_status:int?, matrix_code, message:截断摘要},同事务写)。
- **反例闭环**:同一请求首返回 HTTP 400 或 HTTP 503 后进程退出——两者同为 failed+费用未核清,重启后凭 `error_class` 区分:400=no_retry 断然拒绝(计数未满也拒)、503=retryable 按普通剩余名额判定。**重启仅凭 DB 重放判定,判定函数无内存依赖。**

### 要素 2:名额统计唯一口径

- **修订后状态**(spec §5.3.1 公式,推导对齐 design.md L219"普通共享 max_attempts−1 个重试名额+unknown 另有最多 1 个名额"):
  - **普通名额消耗** = 该 logical_key 中 `attempt_origin IN ('initial','retry') AND error_class='retryable'` 的行数,上限 max_attempts(即首+max_attempts−1 次重试);
  - **unknown 专属名额** = receipt.unknown_retry_used 标志(与 `attempt_origin='unknown_retry'` 行**同事务双写**;判定读标志、审计按行重算);
  - **硬上限** = 该 logical_key 总行数 < max_attempts+1;
  - **"可重试类失败计数"一词统一指本公式,不是简单行数**——spec 前称"行数"、单元二称"可重试类失败计数"的歧义消除:未耗尽判定=再发送三条件,普通与 unknown 名额不互借,score-1/score-2/understand 各自序列,同身份耗尽后重启不重置不重获。

### 要素 3:验收 7d(落库后关闭连接重读判定)

- **修订后状态**:model-calls §7 新增验收 7d(替身 HTTP,零真实付费):同一请求首 attempt 分别注入 HTTP 400 与 HTTP 503 后**落库并关闭连接**→重新打开 DB 仅凭行数据判定(400→拒绝自动重试;503→按普通剩余名额);普通耗尽+unknown 名额未用→仍拒(不互借);**unknown 通道重试后再发生普通可重试失败→该失败 origin='retry' 计入普通名额**(不是 unknown_retry);fail_detail_json 含 http_status 与矩阵子类;判定函数两次独立进程/连接实例断言一致。

### 引用同步清单(本轮文件改动)

| 文件 | 改动 |
|------|------|
| spec §5.3 receipt_attempt DDL | +attempt_origin/error_class/fail_detail_json 三列(含映射注释) |
| spec §5.3.1 | 重试判定持久化段(唯一口径公式+映射+"不是简单行数") |
| spec 变更记录 | 第三轮条目(②补齐+M1 plan 同批交付预告) |
| units/model-calls.md v4 | 三条件块条件 2/3 精确化(读持久化列+公式)、"判定输入全部来自持久化列"段、§5 授权/失败行补写入、§7 验收 7d、状态行、评审提示 |
| engine/pipeline.md | "M1 实现前必须映射的恢复信息"表普通重试计数行→口径与落点(公式+列名) |

## 交付二:M1 实施计划待评审稿

**文件**:[plans/2026-10-05-m1-engine-implementation.md](../superpowers/plans/2026-10-05-m1-engine-implementation.md)。

### 结构与边界

- writing-plans 结构(header/Global Constraints/Review Focus/任务 Files+Interfaces+TDD 步骤+停点);**设计真相源=spec+engine 四文档+五单元**,plan 只引用编号不复制规则——每任务"验收种子"=所引单元 §7 场景编号+代表性断言代码。
- Global Constraints 数值逐字引用(月 ¥50=50000000 微元/期 ¥1/预警 ¥40/10/100/400/max_attempts=2/4000/200 等);DDL 真相源=spec §5.3;发现文档冲突→停,先修文档。
- 头部显著声明:**待评审稿;评审通过≠自动开始实施;实施开始须用户明确解除暂停**(spec §9.1 启动行)。

### 任务序列(26 任务,依赖总览见 plan 内图)

Task 1 [V1]tokenizer 核对→2 config→3 db(12 表迁移,建库即写 pay_paused=0)→4 llm 替身(错误分类映射)→5 ledger 闸门→6 重试判定(验收 7/7b/7c/7d)→7 结算/unknown/核清/快照→8 复用/N_new→9-12 采集侧(normalize/collect/冻结/预筛)→13-16 评分摘要入选组装(score+E4 验证器/understand/claim 协议/安全输出渲染后断言)→17-18 发布(publish 四窗口+ops_json/撤回重上纠错)→19-22 运维(run 运行序/notify UPSERT/ops status+restore-backup [V2]/calibrate [V1])→23 site schema→24 替身端到端→25 部署对接(⚠️需授权)→26 真实付费链路启用(⚠️需授权+前置=校准真实通过)。

### 用户指定两项验证任务的落实

- **[V1] tokenizer 验证在付费链路启用之前**(Task 1+22+26 前置):资源与版本=Task 1 核对模型方发布渠道并锁定(config 映射;官方无离线资源→备选=已核对近似资源+保守初始校准系数 1.2+下调预算余量,两分支都使"计数不可得→不出网"可测);消息结构计数方式=完整请求消息数组含 role/结构开销;**校准样本来源(执行循环解法)=两阶段**:阶段 A 零付费(本地 topic-digest 90 条正文构造请求,验证计数函数),阶段 B 受控付费(calibrate 命令:固定小样本**走完整账本流程**——purpose='calibration' 经授权闸门预占/attempt/结算,单列 calibration_budget_micro_cny=¥0.05;正式管线要求 engine_meta 校准状态=passed,**calibration purpose 本身不受该检查限制**——否则"未校准不得调用,却必须先调用才能校准"死锁;校准调用不绕账本,恰是走账本的受控小额授权);通过条件=零超预占(任一 usage.prompt_tokens>预占计数→停新增+上调系数)。
- **[V2] 备份切换验收覆盖实际 SQLite 文件状态**(Task 21):真实文件系统非内存库;**读回校验前强制 PRAGMA wal_checkpoint(FULL) 并关闭连接,以全新连接重开副本**读 pay_paused=='1'(WAL 未合并会漏);切换边界中断各点注入(①③后=活动库未动可重试;④后=新库已含标志;断言任何中断点不存在"已启用旧库且付费未暂停");裸恢复删键→闸门拒+status 提示。**计划内显式声明:设计轮顺序审查≠恢复功能已验收,该结论只能由本任务运行证据给出。**

### 停点设计(失败后的停点)

任何任务测试红且两轮修复无效→停当前任务报告卡点;Task 1 无可用 tokenizer 资源→停等裁决;Task 13 若需持久化"停新增"标志→先回 spec 补契约再实现(不得静默扩表);Task 21 文件级测试暴露顺序审查未见的窗口→先修文档再改实现;Task 25/26 服务器与真实付费各需当次显式授权;真实运行中任何超预占/重复付费迹象→立即置 pay_paused=1→停,报告账本证据。

## 验证

- `python scripts/check_docs.py --snippets --bash ... --node ...`:**通过**——66 md/238 local_links/DDL 12 表/schema 一致/snippets(bash 2/js 4/json 2/smoke 6)/errors 与 warnings 均为空(首次跑出 plan 内 spec 相对路径错误一处,已修正后复跑全绿)。
- `git diff --check`:通过(仅既有 LF→CRLF 常规警告)。
- 未做:任何 engine/ 代码、服务器操作、真实付费调用、推送(均在暂停边界内);plan 的 Self-Review 四项(覆盖/占位符/类型一致/Review Focus 持有)已在 plan 内执行并记录结论。

## 下一步

- 等用户评审:①②持久化契约三要素(三列/唯一口径/验收 7d)是否闭合 400 vs 503 反例;②M1 plan(任务序列/两项验证任务落实/停点)是否可经评审。
- plan 评审通过后**仍需用户明确恢复实施指示**才进入编码;届时按 plan Task 1 起(或按评审修订稿)。
- 遗留(用户侧):skills.nanmu.xyz DNS、ICP 备案核实、origin push 授权、验收目录清理、Task 10;线上仍 c8a4567。
