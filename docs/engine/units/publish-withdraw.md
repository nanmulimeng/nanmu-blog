# 发布与撤回·单元详细设计(M1 第 3 步·单元四)

> 状态:**设计稿,批量闭环轮**(2026-10-05;五单元之四)。
> 定位:回答"产物如何安全变成线上内容、如何下线与修正"的**实现层设计**——发布链操作序列、Git 与 DB 的中断窗口恢复、跨期隔离、撤回/纠错/重新上线的命令与留痕。功能契约(状态×操作矩阵/重新上线两条)以 [digest-design.md](../digest-design.md) §4.2/§4.5/§5.5/§5.6 为准;发布契约与异常恢复在 [pipeline.md](../pipeline.md) 发布节与期状态节;撤回事实存储=digest_issue.withdrawn_utc/withdraw_commit(spec §5.3,本轮加列)。
> 引用而非复制:E8/E9 错误分类引用 design.md 矩阵;质量门禁(缓存验证)引用 development/quality-gates.md。

## 0. 单元边界与接口交接

| 数据/接口 | 本单元职责 | 相邻单元职责 |
|------|-----------|--------------|
| digest_issue 状态推进 | **唯一写入者**(draft→submitted→published;withdrawn 两列) | 单元三写 draft 起;单元五写 failed 与 last_exit/last_run_utc |
| entry used+claim 清空 | **执行**(确认 published 同事务) | 单元三定义协议(其 §3 规则 7) |
| 专用 Git 工作副本 | **唯一操作者**(commit/push/远端核对) | 个人工作副本不共享;铁律见 pipeline.md |
| 线上证据(release.txt/页面) | **读取判定**(published 唯一证据) | 站点部署链既有(M0 已验收) |
| 费用核清后更新 | **提示**(过期期清单);更新执行=人工纠错提交 | 单元二核清操作产生快照差异 |

## 1. 目标与范围

**解决**:draft 产物到 published 的每一步证据与状态落库;三个中断窗口的恢复;新期与旧期的副本隔离;撤回/纠错/重新上线的完整操作序列与留痕。

**明确延期**:调度触发与自动推进上限(单元五);通知发送(单元五);site 构建部署链(M0 既有)。

## 2. 使用场景

| 场景 | 触发 | 前提 | 正常完成后 |
|------|------|------|-----------|
| 发布 | draft 且 verify 通过 | 副本隔离检查过(§3 规则 4) | push→submitted;线上确认→published+used+claim 清 |
| 状态恢复 | 运行发现 draft/submitted 存量 | — | 三窗口各自补记(§3 规则 3) |
| 纠错 | published 内容有误(人工发现) | — | 新的已校验提交上线;引擎日志补记 |
| 撤回 | 人工决定下线整期 | published | 三处消失+withdrawn 两列落库 |
| 重新上线 | 已撤回且人工确认 | 两条之一 | 原样恢复 / 修正后恢复;均零模型调用 |
| 核清后更新 | 单元二核清致快照变化且该期已发布 | — | 提示清单;人工走纠错式提交改数字/标志/标注 |

## 3. 业务规则(优先级从高到低)

1. **产物与提交身份**:产物=site/src/content/digest/YYYY-MM-DD.md;**内容身份=sha256(文件字节)**;提交身份=git_commit SHA。digest_issue 行持 markdown_path+git_commit;恢复与核验一律从**内容身份**出发(路径存在≠产物正确,pipeline 既有)。
2. **状态推进(每步证据+同事务落库)**:
   | 推进 | 证据 | 事务 |
   |------|------|------|
   | draft(单元三写) | 文件落盘+verify 过 | digest_issue 行 |
   | draft→submitted | push 成功(远端含目标 SHA) | digest_issue= submitted+git_commit |
   | submitted→published | **线上 release.txt 版本包含该提交 且 对应日报 URL 可读且内容身份一致** | digest_issue=published 同事务:该期 claim 的 entry——进产物者→used+claim 清;**未进产物者(组装边界被 override 排除的 selected)→rejected+claim 清**(评分事实保留在 analysis,次日按 discovered_utc 窗口自然可再入围;无清路径则永久误判"他期占用",见单元三 §3 规则 7) |
   published 的证据是线上事实,不是"git 命令成功"(pipeline 既有);构建合并多提交不要求线上 SHA 等于日报 commit,但祖先关系+内容身份都要满足,且排除后续提交删除/修改目标日报(查路径当前内容)。
3. **Git 与 DB 之间的三个中断窗口(恢复序列)**:恢复一律**先查远端与线上、后补记状态**,不凭退出码重新生成:
   | 窗口 | 现场判定 | 恢复动作 |
   |------|----------|----------|
   | commit 成功、DB 未记 draft | 副本 git log 有该期内容身份提交、无 draft 行 | 补记 draft(复用提交,不重组) |
   | push 成功、状态仍 draft | ls-remote 含 git_commit | 补记 submitted |
   | 上线成功、未记 published | 线上证据齐(规则 2) | 补记 published+used+claim 清(幂等:重复恢复不重复置 used) |
4. **跨期工作副本隔离检查(push 前强制)**:新期 push 前核对专用副本——①无**其他期的未推送提交**(git log origin/main..;含待人工旧期的未推送提交,阻塞条件是"提交会被带出"而非"待人工标志存在");②本次 push 的变更集只含本期文件。违反→**不 push、转人工**(digest-design §4.6"一次 push 不得意外带出待人工的旧期内容")。**待人工旧期无未推送提交时不阻塞新期**(撤回已完成 push、暂停期无产物文件等:新期照常生成与发布,旧期保持待人工)。副本同步:开始前仅在**无本地未推送提交**时 fast-forward;否则先识别保存本期提交再检查远端差异,仅无冲突且内容身份保持时同步,否则 E8 转人工(pipeline 既有,此处为执行清单)。
5. **撤回(操作序列,全部留痕)**:①置暂停(issue_freeze.paused=1,防自动重发——单元五存储);②工作副本删该期文件→verify→commit+push;③线上确认三处(列表/详情 404/RSS)消失(Task8a 缓存契约);④digest_issue 写 withdrawn_utc+withdraw_commit(与③后确认同事务;status 保持 published=历史事实)。
6. **纠错(published)**:专用副本修订该期 markdown→本地 verify→commit+push→线上确认;引擎侧仅结构化日志补记(纠错提交 SHA+变更摘要);条目级错误同时写 override 防再犯(digest-design §5.5)。**修订零模型费用;重写摘要=新请求身份、新费用归该期**。
7. **重新上线(仅已撤回 published,两条,均零模型调用、显式命令+留痕)**:
   - **原样恢复**:从 git 历史取撤回前该期产物(内容身份=撤回提交的父版本),新提交恢复文件→verify→push→线上确认;
   - **修正后恢复**:在离线工作副本修正历史内容→verify→一次新提交上线(不先恢复错误版本,digest-design §4.5);
   - 两条均不清 withdrawn 之外再动 entry(used 保持);成功后 withdrawn_utc/withdraw_commit 保留(撤回史实),可见性由站点内容决定——status 命令展示 `published withdrawn=relisted`。
8. **费用核清后的内容更新(闭环)**:单元二核清操作完成后,比对**已发布期**的当前快照与发布时快照——数字或 pending 标志变化→核清命令输出过期期清单+结构化日志;更新**不自动执行**,走人工纠错提交(数字+标志+正文标注三处一起,digest-design §3.4;不另发模型请求)。理由:自动改已发布内容的风险(构建失败/误改)大于数字滞后的影响;M1 接受滞后窗口,runbook 记巡检项。
9. **禁止事项(既有铁律重申)**:不 force push、不覆盖个人文章、不 rewrite 历史;坏 markdown 必须在 push 前 verify 拦截;部署失败不使旧站离线;撤回期间暂停标志未解除不得有自动发布路径。

## 4. 输入输出

**输入**:draft 产物路径+内容身份、工作副本状态、远端/线上证据、撤回/重新上线/纠错命令参数(期+原因)、核清后过期清单(单元二)。
**输出**:digest_issue 状态/withdrawn 字段更新、entry used/claim 更新、git 提交、结构化日志(纠错/撤回/重新上线留痕)、转人工事件(E8/E9/隔离失败→单元五通知)。
**非法输入处置**:verify 失败→不 push(产物回单元三);远端已存在同期不同内容→E8 转人工;线上确认超时→E9 保持 submitted 只重查。

## 5. 数据与状态

- digest_issue 扩列已落 spec §5.3(fail_reason/updated_utc/last_exit/last_run_utc 由单元五写;withdrawn_utc/withdraw_commit 本单元写);
- 撤回暂停标志=issue_freeze.paused(单元五存储,本单元置位);
- 无新表;所有操作命令化(`publish/withdraw/relist/correct` 形态属 M1 plan 任务域,本文定序列与留痕)。

## 6. 异常与恢复

| # | 场景 | 现场状态 | 恢复判定与动作 | 费用 |
|---|------|----------|----------------|------|
| A | push 冲突(E8) | 产物在,远端前进 | 保留 draft+暂停自动发布+转人工 | 零 |
| B | 上线确认超时(E9) | submitted | 只重查线上,不重做评分/摘要/重组 | 零 |
| C | 三窗口(规则 3) | 见表 | 先查证据后补记 | 零 |
| D | 撤回中 push 失败 | 文件已删未上线 | 按 A 处理;暂停标志已在,无重发风险 | 零 |
| E | 重新上线后构建失败 | 文件在,线上旧 | 部署恢复(M0 既有);不自动回滚重试 | 零 |

## 7. 验收场景(M1 plan 强制测试种子)

1. **发布推进**:draft→push→submitted→线上确认→published;断言 used+claim 清空与 published 同事务;**同期被 override 排除的 selected→rejected+claim 清**(否则它在新期被永久误判他期占用)。
2. **窗口 C**:三窗口各注入中断(kill 于 commit/push/确认之间)→恢复只补记不重生成(评分调用计数零)。
3. **隔离检查**:副本存在他期未推送提交→新期不 push+转人工断言;无未推送→正常。
4. **撤回**:全序列→三处消失+withdrawn 落库+暂停置位;重启后无自动重发(frozen 恢复仍撤回)。
5. **重新上线两条**:原样恢复内容身份=撤回父版本;修正后恢复=新提交;均零模型调用(计数断言)。
6. **纠错**:新提交替换旧版本,历史保留;entry_count 如实变化。
7. **核清后提示**:核清致快照变→过期清单含该期;更新走纠错提交后三处一致。
8. **published 证据**:线上 SHA 含提交但路径 404(后续提交删除)→不判 published/触发补恢复。

## 8. 依赖与维护成本

- 零新增依赖/表;命令形态留 M1 plan;巡检项(核清过期清单检查)入 runbook。

## 9. 未决项

| 未决项 | 验证方法 | 通过条件 | 失败后的备选 | 定位 |
|--------|----------|----------|--------------|------|
| 线上确认轮询参数(间隔/窗) | M1 实测 | E9 窗口内可判定 | 调 timeout 配置 | 待实施验证 |
| 撤回期 RSS/列表缓存时延 | M1 实测(Task8a 契约内) | 三处在可接受时限消失 | 缓存策略调整(site 侧) | 待实施验证 |

## 评审提示

本单元把 digest-design §4.2/§4.5/§5.5/§5.6 的功能契约落成操作序列:三窗口恢复表(先证据后补记)、隔离检查清单、撤回四步(暂停→删→三处验证→withdrawn 落库)、重新上线两条零模型、核清后提示+人工纠错(不自动改已发布内容的决策+理由)。撤回存储=withdrawn 两列、暂停=issue_freeze.paused,均已入 spec DDL。开放项仅实测类。
