# 2026-10-05 第四轮核验修正(M1 plan 评审轮:4 组 P1+计划校正表)

## background

- 接续 [retry-persistence-m1-plan](2026-10-05-m1-retry-persistence-m1-plan.md)(954f574)。用户第四轮核验:三列持久化方案通过、26 任务覆盖主流程,但 plan 转写引入影响费用/恢复/验收的矛盾,**不批准按原稿实施**;4 组 P1+计划校正表一次修正,不重开五单元。
- 用户验证基线:HEAD=954f574 干净;check_docs 67md/245links/12 表通过;git diff --check 通过;已读实际 site schema 与消费页面;未重跑 --snippets(本轮已代跑)。

## 修正清单(逐项:修订后状态 / 账本 / 文件 / 下一步动作)

### P1-1:attempt_origin 必须保持授权时的含义,不能按返回错误改写(原 7d"unknown 通道后普通失败计 origin='retry'"可读作改写历史)

- **修订后状态**:`attempt_origin`=授权时确定的来源,**写入后不可改写**。用户三行序列表落实进验收 7d:attempt1 首次超时未知→`initial/unknown`;attempt2 unknown 额外重试返回 503→**保持 `unknown_retry/retryable`**;attempt3 普通名额仍剩而继续→新授权 `retry/retryable`。**名额公式简化(用户拍板)**:普通尝试已用数=`origin IN ('initial','retry')` 行数,**不按 error_class 过滤**——名额按授权消耗,不因响应结果保留或改写;error_class 只决定能否再发送与走哪个通道(no_retry 拒、计数未满也拒/retryable→普通通道/unknown→满足等待走 unknown 通道);unknown 名额(标志同事务双写)与硬上限(总行数<max_attempts+1)不变。失败更新事务只写 error_class/fail_detail_json,断言不改 origin。
- **账本**:每次授权即消耗对应通道一个名额(无论返回);initial/unknown 与 initial/retryable 同样各占一个普通名额;不能通过获得某类结果保留名额;重启判定不变。
- **文件**:units/model-calls.md v5(状态行/规则 5 三条件块/验收 7d 重写/评审提示);spec §5.3.1(公式段+授权语义);engine/pipeline.md(口径行);plan(Global Constraints/Task 6 公式与测试:新增 `test_7d_origin_immutable_*`、`test_6_quota_counts_attempts_not_error_classes`)。
- **下一步动作**:Task 6 测试种子=7d 第四轮序列表(三行 origin/error_class 逐行断言)+不按 error_class 过滤的计数断言。

### P1-2:校准通道是新的付费契约,不能只在 plan 中新增例外(+1.2 无覆盖依据)

- **修订后状态**:**契约入单元二(model-calls §3 规则 11,不再只在 plan 设例外)**——例外范围唯一(purpose='calibration' 是"校准未完成不出网"唯一例外,解执行循环);**走完整账本不设免检**(逐过闸门,月预算与窗口限额照常适用;`calibration.budget_micro_cny` 预占合计上限,耗尽中止;小额只限"按预占值批准的调用量",不自动保证实付不超,仍受对账硬失败约束);**校准记录绑定配置不可跨配置沿用**(engine_meta 记 {model, tokenizer 资源与版本, 消息计数方式, 校准系数, 样本结果, 判定时刻},任一变化即失效须重校准);**初始系数依据**——官方资源=1.0(资源即服务端分词器),**无官方资源不预设默认系数(1.2 已删)**,必须先建立"近似资源+系数能覆盖目标 API 输入计量"的依据,建立不了则停;近似小额探索(如进行)表述为"尚未验证上界的小额实验",不得称"已建立保守上界"(四个样本通过只证明这四个样本,不升格为已证明上界)。通过条件=全部样本 usage≤预占;任一超出→置 pay_paused 停新增+人工确认后重校准。
- **账本**:校准 attempt 计入窗口与月预算;预算上限耗尽即止;配置指纹比对决定校准状态有效性。
- **文件**:units/model-calls.md(规则 11 新增+规则 2 例外引用+§5 校准行+验收 11 新增+§9 tokenizer 行+状态行+评审提示);design.md budget.yaml(示例+字段表加 calibration.budget_micro_cny);spec §5.3.1(engine_meta 括号内校准契约引用)+变更记录;plan(头部 [V1]/Task 1 分支②/Task 22 重写为契约引用版)。
- **下一步动作**:Task 22 测试种子=验收 11(含"换资源/版本/系数/模型任一→状态失效"与"计入月预算不绕闸门"断言)。

### P1-3:预占公式漏输出上限;停新增机制留为实现者选择(Task 5 只写输入×价;Task 13"engine_meta,仅内存+日志?")

- **修订后状态**:①**预占公式逐字入 plan**(budget.md"峰时未缓存输入价与完整输出上限"策略):预占金额=向上取整后的输入预占 token 数×峰时未缓存输入价+`max_output_tokens`×输出价,最终向上取整为整数微元(Global Constraints 与 Task 5 双落);②**停新增持久化定稿**——对账硬失败(usage 超计数/供应商实付>预占/校准样本超计数)=**置 engine_meta.pay_paused='1' 并记录原因**,复用既有闸门不另建暂停系统(删除 halt_new_charges/内存态选项);重启继续拒绝,人工核对(对账修正/账单核对)后显式置 0;复用/结算/只读照常。
- **账本**:预占含输出分量(保守上界完整);停新增跨重启有效,解除仅人工。
- **文件**:units/model-calls.md(规则 2/规则 8 停新增持久化);units/scheduling-ops.md(规则 9 置位来源段:restore-backup 步骤②+单元二对账硬失败,同一闸门同一解除协议);spec §5.3.1(pay_paused 置位来源)+变更记录;plan(Global Constraints 预占公式行+pay_paused 置位来源/Task 5/Task 13 停点定稿)。
- **下一步动作**:Task 5 断言预占=输入+输出两分量;Task 13 断言超预占置位后重启仍拒、复用照常。

### P1-4:Task 26 授权顺序循环("前置=校准已真实通过"vs"Step 1 才执行校准");部署期 timer 边界;机械请示

- **修订后状态**:**五步不得倒置**——①本地与替身验证通过、校准方案与预算明确→②获**真实校准授权**→③执行校准并检查结果(失败→停在付费暂停态等人工,不得进入后续)→④校准通过后获**正常付费运行授权**→⑤首期+启用 timer+连续 3 天验收。Task 25:**timer 安装但保持 disabled(不 enable/start)直至 Task 26 Step 3 完成**,引擎侧校准状态检查为第二道闸门;OnFailure 链路用手动触发 service 验证,不启动定时付费。授权方式改为:**一次授权覆盖列明范围,范围内直接执行;范围变化或遇未列操作再确认**。
- **账本**:部署期间零定时付费;付费启用分两段授权(校准/正式运行),每段有独立停点。
- **文件**:plan(Task 26 重写为五步两授权;Task 25 授权方式+timer disabled);spec 变更记录(④)。
- **下一步动作**:实施时按五步执行,Step 3 失败即停。

### 计划校正表(同批落实)

| 项 | 修订 |
|----|------|
| Task 10/11 事务 | 明确 entry upsert 与 freeze INSERT 由**同一事务拥有者(collect_once)一次提交**;Task 10/11 是测试关注点拆分不是事务拆分;验收 2(冻结原子性)抓跨事务半写 |
| Task 23 路径 | 修正为 `site/src/content.config.ts`(实际文件,已核实);**职责分工**:schema `z.boolean().default(false)` 仅旧文件兼容,site 验证旧文件可过;**"新生成文件必须显式写布尔值"由 engine 组装测试断言(Task 16)**,不混在 schema;补两消费页面 `site/src/pages/digest/[...page].astro`(L24 成本行)与 `[id].astro`(L16 成本行)——cost_pending=true 时同步显示"(含未决预占,为保守上界)";ai_model 示例 ID 拒绝属 engine 断言,schema 保持 min(1) |
| Task 24 重放断言 | "任意阶段 kill 后零新增付费"删除,改**分窗口断言**:有效响应不重发(复用)/缺失评分可按授权补发(允许新增付费)/unknown 保留预占遵循等待与名额/发布恢复零模型调用 |
| Task 1 前置 | 新增 **Task 0 工程初始化**(requirements/pyproject src 布局/`pip install -e ".[dev]"`/conftest 冒烟);依赖总览与 [V1] 标记更新为 Task 0/1/22/26 |

## 验证

- `python scripts/check_docs.py --snippets --bash ... --node ...`:**通过**——67 md/245 local_links/DDL 12 表/schema 一致/snippets(bash 2/js 4/json 2/smoke 6)/errors 与 warnings 均空。
- `git diff --check`:通过(仅既有 LF→CRLF 常规警告)。
- plan 残留 grep:无 1.2 默认系数/halt_new_charges/旧公式/"Task 1-24"/错误路径残留(命中处均为修正说明文本)。
- 未做:engine 代码、服务器操作、真实付费、推送;model-calls v5 评审提示中 v4 段已标注"名额公式已被第四轮修订"避免文内自相矛盾。

## 下一步

- 等用户第五轮核验(范围=本轮列明差异与引用同步):P1-1 origin 序列表与名额口径、P1-2 规则 11 契约、P1-3 预占公式与停新增持久化、P1-4 五步授权、校正表四项。
- 通过后 plan 交开发者执行;实施开始仍须用户明确解除暂停。
- 遗留(用户侧):skills.nanmu.xyz DNS、ICP 备案核实、origin push 授权、验收目录清理、Task 10;线上仍 c8a4567。
