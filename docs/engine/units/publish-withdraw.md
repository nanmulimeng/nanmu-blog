# 发布与撤回·单元详细设计(M1 第 3 步·单元四)

> 状态:**设计稿 v2,联合核验修正轮**(2026-10-05;修正:内容身份/提交身份持久化时点、四中断窗口与确定性查找、线上验证证据链三步、撤回/重新上线的远端生效未记恢复、relisted 判定)。
> 定位:回答"产物如何安全变成线上内容、如何下线与修正"的**实现层设计**——发布链操作序列、Git 与 DB 的中断窗口恢复、跨期隔离、撤回/纠错/重新上线的命令与留痕。功能契约(状态×操作矩阵/重新上线两条)以 [digest-design.md](../digest-design.md) §4.2/§4.5/§5.5/§5.6 为准;发布契约与异常恢复在 [pipeline.md](../pipeline.md) 发布节与期状态节;撤回事实存储=digest_issue.withdrawn_utc/withdraw_commit(spec §5.3,本轮加列)。
> 引用而非复制:E8/E9 错误分类引用 design.md 矩阵;质量门禁(缓存验证)引用 development/quality-gates.md。

## 0. 单元边界与接口交接

| 数据/接口 | 本单元职责 | 相邻单元职责 |
|------|-----------|--------------|
| digest_issue 状态推进+发布/撤回身份 | **唯一写入者**(git_commit 回填→submitted→published;withdrawn/relisted 两对列) | 单元三写 draft+content_sha256 起;单元五写 failed 与 last_exit/last_run_utc |
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

1. **产物与提交身份(核验修正:身份持久化时点明确)**:产物=site/src/content/digest/YYYY-MM-DD.md;**内容身份 content_sha256=sha256(文件字节),draft 落盘时计算并随 draft 行同事务写入=不可变预期值**;提交身份 git_commit SHA,**commit 成功即回填 digest_issue(此时仍处 draft,一次 UPDATE;push 后才置 submitted)**。恢复与核验一律从持久化的 content_sha256 出发比对 git 对象内容——**现算工作副本文件不能证明"仍是上次确认准备发布的版本"**(副本可被后续操作改动),必须比"提交树内文件字节"与"库内不可变预期值"。
2. **状态推进(每步证据+同事务落库)**:
   | 推进 | 证据 | 事务 |
   |------|------|------|
   | draft(单元三写) | 文件落盘+verify 过 | digest_issue 行(含 content_sha256) |
   | commit(仍 draft) | 副本提交成功 | digest_issue.git_commit 回填(单 UPDATE) |
   | draft→submitted | push 成功(远端 ls-remote 含 git_commit) | digest_issue=submitted |
   | submitted→published | **线上证据链三步**(下段) | digest_issue=published 同事务:该期 claim 的 entry——**进最终产物者**→used+claim 清;**未进者(中间暂离各原因:override/重判落选/摘要失败/安全失败/裁剪,单元三规则 7)**→rejected+claim 清,日志按原因分列 |
   **线上证据链三步(核验修正:线上是渲染后 HTML,不能直接与 Markdown 文件字节比)**:① 线上 release.txt 部署 SHA 对应 Git 提交树中**目标路径存在,且树内文件字节 sha256=digest_issue.content_sha256**(经 git cat-file 取树内文件计算;构建合并多提交不要求线上 SHA 等于日报 commit,但树内内容身份必须相等);② 排除后续删除/修改(查该 SHA 树的路径当前内容仍在);③ 对应日报 URL HTTP 可读(页面渲染一致性走 site 既有校验)。三步全过才算 published——published 的证据是线上事实,不是"git 命令成功"(pipeline 既有)。
3. **Git 与 DB 之间的四个中断窗口(恢复序列;核验修正:补 SHA 未回填窗口+确定性查找法)**:恢复一律**先查远端与线上、后补记状态**,不凭退出码重新生成:
   | 窗口 | 现场判定 | 恢复动作 |
   |------|----------|----------|
   | W1 commit 成功、DB 未记 draft | 无 draft 行;副本 log 有该期路径提交 | 按目标路径过滤提交,取**树内文件 sha256=现算产物身份**的提交(确定查找,非"最新")→补记 draft(content_sha256+git_commit,复用提交不重组) |
   | W2 draft 在、commit 成功但 SHA 未回填 | draft 行有 content_sha256、git_commit 空 | 同 W1 查找法(以 content_sha256 为预期值)补填 git_commit,仍 draft |
   | W3 push 成功、状态仍 draft | ls-remote 含 git_commit(或 W2 查找到) | 补记 submitted |
   | W4 上线成功、未记 published | 线上证据链三步(规则 2) | 补记 published+终态清算(used/rejected+claim 清;幂等:重复恢复不重复置 used) |
   查找失败(副本历史无内容身份匹配的提交)=未真正 commit→回单元三重组装(评分/摘要全复用零新增);W2/W3 的比对基准一律是**库内 content_sha256**,不是工作副本现状。
4. **跨期工作副本隔离检查(push 前强制)**:新期 push 前核对专用副本——①无**其他期的未推送提交**(git log origin/main..;含待人工旧期的未推送提交,阻塞条件是"提交会被带出"而非"待人工标志存在");②本次 push 的变更集只含本期文件。违反→**不 push、转人工**(digest-design §4.6"一次 push 不得意外带出待人工的旧期内容")。**待人工旧期无未推送提交时不阻塞新期**(撤回已完成 push、暂停期无产物文件等:新期照常生成与发布,旧期保持待人工)。副本同步:开始前仅在**无本地未推送提交**时 fast-forward;否则先识别保存本期提交再检查远端差异,仅无冲突且内容身份保持时同步,否则 E8 转人工(pipeline 既有,此处为执行清单)。
5. **撤回(操作序列,全部留痕)**:①置暂停(issue_freeze.paused=1,防自动重发——单元五存储;**暂停只挡自动动作,不记录人工进度**——撤回推进到哪一步以远端/线上证据为准);②工作副本删该期文件→verify→commit+push;③线上确认三处(列表/详情 404/RSS)消失(Task8a 缓存契约);④digest_issue 写 withdrawn_utc+withdraw_commit(与③后确认同事务;status 保持 published=历史事实)。**恢复路径(push 成功、withdrawn 未记)**:远端 log 中该路径最新的"删除文件"提交=撤回提交(确定查找)+线上三处已消失→补记 withdrawn 两列;线上未消失=push 未完成或缓存未过,按 push 冲突(E8)/等待处理,不预记。
6. **纠错(published)**:专用副本修订该期 markdown→本地 verify→commit+push→线上确认;引擎侧仅结构化日志补记(纠错提交 SHA+变更摘要);条目级错误同时写 override 防再犯(digest-design §5.5)。**修订零模型费用;重写摘要=新请求身份、新费用归该期**。
7. **重新上线(仅已撤回 published,两条,均零模型调用、显式命令+留痕)**:
   - **原样恢复**:从 git 历史取撤回前该期产物(内容身份=撤回提交的父版本),新提交恢复文件→verify→push→线上确认;
   - **修正后恢复**:在离线工作副本修正历史内容→verify→一次新提交上线(不先恢复错误版本,digest-design §4.5);
   - 成功后写 **relisted_utc+relist_commit**(与线上确认同事务);两条均不再动 entry(used 保持);withdrawn_utc/withdraw_commit 保留(撤回史实)。
   **状态判定(核验修正,重启可恢复)**:**当前在线状态=站点内容运行时核验**(URL 可读性),持久事实分三层——withdrawn 非空且 relisted 空=**处于撤回**;relisted 非空=**已重新上线**(最近一次);两者皆空=未撤回过。status 命令据此展示(`published` / `published withdrawn` / `published withdrawn=relisted`),不再用"withdrawn 非空=已撤回"单字段表达两态。**恢复路径(重新上线 push 成功、relisted 未记)**:远端含"恢复该路径且树内身份=预期"提交+线上可读→补记 relisted 两列。
8. **费用核清后的内容更新(闭环)**:单元二核清操作完成后,比对**已发布期**的当前快照与发布时快照——数字或 pending 标志变化→核清命令输出过期期清单+结构化日志;更新**不自动执行**,走人工纠错提交(数字+标志+正文标注三处一起,digest-design §3.4;不另发模型请求)。理由:自动改已发布内容的风险(构建失败/误改)大于数字滞后的影响;M1 接受滞后窗口,runbook 记巡检项。
9. **禁止事项(既有铁律重申)**:不 force push、不覆盖个人文章、不 rewrite 历史;坏 markdown 必须在 push 前 verify 拦截;部署失败不使旧站离线;撤回期间暂停标志未解除不得有自动发布路径。

## 4. 输入输出

**输入**:draft 产物路径+内容身份、工作副本状态、远端/线上证据、撤回/重新上线/纠错命令参数(期+原因)、核清后过期清单(单元二)。
**输出**:digest_issue 状态/withdrawn 字段更新、entry used/claim 更新、git 提交、结构化日志(纠错/撤回/重新上线留痕)、转人工事件(E8/E9/隔离失败→单元五通知)。
**非法输入处置**:verify 失败→不 push(产物回单元三);远端已存在同期不同内容→E8 转人工;线上确认超时→E9 保持 submitted 只重查。

## 5. 数据与状态

- digest_issue 扩列已落 spec §5.3(**content_sha256 本单元消费(单元三写)**;fail_reason/updated_utc/last_exit/last_run_utc 由单元五写;**git_commit commit 即回填;withdrawn_utc/withdraw_commit/relisted_utc/relist_commit 本单元写**);
- 撤回暂停标志=issue_freeze.paused(单元五存储,本单元置位);
- engine.db 现 12 表(engine_meta 由单元五管理);所有操作命令化(`publish/withdraw/relist/correct` 形态属 M1 plan 任务域,本文定序列与留痕)。

## 6. 异常与恢复

| # | 场景 | 现场状态 | 恢复判定与动作 | 费用 |
|---|------|----------|----------------|------|
| A | push 冲突(E8) | 产物在,远端前进 | 保留 draft+暂停自动发布+转人工 | 零 |
| B | 上线确认超时(E9) | submitted | 只重查线上,不重做评分/摘要/重组 | 零 |
| C | 四窗口(规则 3) | 见表 | 先查证据后补记;W2 比对基准=库内 content_sha256 | 零 |
| D | 撤回中 push 失败 | 文件已删未上线 | 按 A 处理;暂停标志已在,无重发风险 | 零 |
| E | 重新上线后构建失败 | 文件在,线上旧 | 部署恢复(M0 既有);不自动回滚重试 | 零 |
| F | 撤回/重新上线 push 成功、DB 未记 | 远端已生效 | 规则 5/7 恢复路径:按远端内容证据确定提交补记两列 | 零 |

## 7. 验收场景(M1 plan 强制测试种子)

1. **发布推进**:draft(含 content_sha256)→commit 回填 SHA→push→submitted→线上证据链三步→published;断言 used+claim 清空与 published 同事务;**同期未进最终产物的 selected(中间暂离各原因)→rejected+claim 清**,日志按原因分列(否则它在新期被永久误判他期占用)。
2. **窗口 C(四窗口)**:W1-W4 各注入中断(kill 于 commit/回填/push/确认之间)→恢复只补记不重生成(评分调用计数零);**W2 断言:工作副本文件被人为改动后,恢复仍以库内 content_sha256 在 git 历史中查找,不受副本现状影响**;查找失败路径→重组装零新增。
3. **隔离检查**:副本存在他期未推送提交→新期不 push+转人工断言;无未推送→正常。
4. **撤回**:全序列→三处消失+withdrawn 落库+暂停置位;重启后无自动重发(frozen 恢复仍撤回);**push 成功后 kill(未记)→恢复按远端删除提交补记 withdrawn 两列**。
5. **重新上线两条**:原样恢复内容身份=撤回父版本;修正后恢复=新提交;均零模型调用(计数断言);**成功写 relisted 两列;三态判定(未撤回/撤回中/已重上)重启后仅凭 DB+站点核验可复现;重上 push 成功未记→补记**。
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

v2 落实联合核验修正:content_sha256 随 draft 同事务持久化(恢复比对的**不可变预期值**,现算副本不作数)、git_commit commit 即回填、四中断窗口(W1-W4,SHA 未回填窗口补上,查找=按内容身份非"最新")、线上证据链三步(树内文件身份→排除后续删除→URL 可读,渲染 HTML 不与 Markdown 字节直比)、撤回/重新上线各补"远端生效未记"恢复路径、relisted 两列三态判定(未撤回/撤回中/已重上,重启可复现)。占用终态清算泛化到全部未进产物原因。开放项仅实测类。
