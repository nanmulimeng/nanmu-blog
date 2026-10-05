# 数据接入与候选管理·单元详细设计(M1 第 3 步·单元一)

> 状态:**设计稿,待用户评审**(2026-10-05;第 3 步五单元之首,以 [digest-design.md](../digest-design.md) v3 为功能输入基线)。
> 定位:回答"上游材料如何变成身份稳定、可追溯、按期冻结的候选"的**实现层设计**——存储映射、写入协议、事务边界、恢复行为、验收场景。功能语义(冻结契约/状态×操作/人工操作)以 digest-design 为准,本文不重复;与上游契约冲突时先改上游再回改本文。
> 引用而非复制:判重规则 R0-R7 与多源平局见 [design.md](../design.md) identity_key 节;上游只读契约与依赖字段清单见 [data-source](../../context/topic-digest-data-source.md);DDL 真相源在 [spec §5.3](../../superpowers/specs/2026-10-02-nanmu-blog-design.md);候选上限公式见 design.md 候选上限节;窗口/阶段划分见 [pipeline.md](../pipeline.md) 阶段表。

## 0. 单元边界与接口交接

| 数据 | 本单元职责 | 相邻单元职责 |
|------|-----------|--------------|
| 上游 topic-digest SQLite | **只读**(mode=ro,48h 窗口 JOIN,data-source 契约) | 任何人不得写上游(铁律 4) |
| engine.db `entry` 表 | **唯一写入者**(创建/判重合并/未发布刷新) | 评分单元改 status(pending→scored→…);发布单元确认后置 used |
| engine.db `issue_freeze` 表 | **唯一写入者**(冻结确认事件) | 全管线只读;调度单元凭该行判定"生成中,已冻结" |
| engine.db `digest_issue` 表 | 仅 E2 时写 failed 行 | 组装写 draft,发布推进 submitted/published(单元三/四) |
| 候选上限 N | 提供 `prescreen(候选, 配置, N)` 纯函数并执行截断 | **N 的计算属模型调用与费用治理单元**(预算公式输入) |
| 预筛输出(入围清单) | 产出:按 manifest 顺序的入围成员 | 评分/摘要单元消费;请求身份用 manifest.content_hash |

## 1. 目标与范围

**解决**:一次 collect 从上游读取→判重入库→冻结确认→预筛截断的完整可恢复链路;entry 台账的创建与刷新规则;期候选快照的存储与重放。

**本单元做到**:窗口读取、判重、多源合并、entry 幂等写入与刷新、冻结确认落库、确定性预筛与截断、E2 失败记录。

**明确延期**(归属后续单元):评分与摘要(单元三);费用授权与 N 的计算(单元二);产物组装与期状态推进(单元三/四);跨期调度编排、补跑顺序、暂停标志存储(单元五);失败原因/重试计数/通知去重键的持久化字段映射(spec §5.3.1 清单,单元五定稿)。

## 2. 使用场景

| 场景 | 触发 | 前提 | 正常完成后 |
|------|------|------|-----------|
| 新期采集 | 调度触发该 issue_date 首次运行 | 上游可达;该期无 issue_freeze 行 | entry 台账就绪;issue_freeze 行落地;预筛输出入围清单交评分 |
| 续跑(同期再次进入) | 调度自动推进或人工重跑 | 该期 issue_freeze 行已存在 | **跳过采集**,直接读 manifest 走预筛及以后(digest-design §4.4) |
| 预筛单独重放 | 排查/配置调整 | 冻结已确认 | 预筛是纯函数:同 manifest+同配置+同 N → 同结果,零付费、无副作用 |
| 状态查询 | `status --issue` | — | 只读展示冻结成员数/入围数/entry 统计(digest-design §3.5 格式) |

## 3. 业务规则(优先级从高到低)

1. **只读上游**:mode=ro、不加索引、不改 schema;依赖字段清单以 data-source 固化,schema 漂移由依赖测试先红→按 E2 处理(data-source 只读契约)。
2. **窗口**:`fetched_utc` 近 48h;JOIN `item.source_id=source.id`,取 `source.enabled=1` 且 `item.status IN ('fresh','clustered')`,排除 dropped(data-source 实施读取契约)。窗口锚定 `fetched_utc`(采集事实),展示排序才用 `published_utc`。
3. **判重与合并**:identity_key 归一按 design.md R0-R7;同 identity_key 多源多行在内存合并为一条,平局依据 tier(T1 优先)→ sources.yaml priority(小者优)→ source.name 字典序,选择依据写日志;**合并不提高可信度**。
4. **entry 台账**(写入规则见 §5):`INSERT OR IGNORE` 创建;已存在且 `status != 'used'` 且正文变化时刷新;`used` 条目永不刷新(data-source"M1读取与快照补充")。
5. **discovered_utc 锚定(决策)**:取该 identity_key **首次**发现时的上游 fetched_utc,后续再读取**不刷新**。理由:48h 窗口滑动淘汰(digest-design §4.6)需要确定锚点;若随内容刷新前移,老条目可借小改动无限续命,与"日报以新事件为主"相悖。正文刷新只改善近期评估输入质量,不延长候选寿命。
6. **冻结**(功能契约=digest-design §4.4,物理实现见 §5):collect 结束写入 issue_freeze;允许空集合;半成品不算冻结。
7. **预筛排除**(顺序固定,全部本地零成本;输入=冻结 manifest 成员):
   1. 标题命中 selection.yaml `title_blacklist`;
   2. 来源命中 sources.yaml `exclude`(死源清单——上游 enabled=1 但 feed 已坏);
   3. `content_text` 为空或纯空白(data-source 实测约 30%);
   4. `entry.status = 'used'`(已上过日报);
   5. `entry.status = 'selected'`(被其他未完成期占用;failed 期人工放弃后由那时的释放操作改回可评估,本单元只读现状);
   6. override 表 `exclude` 命中(identity_key 精确匹配,阶段边界生效)。
8. **截断**:排除后按 T1 优先 → discovered_utc 降序 → identity_key 升序(确定性排序,与展示排序不同用途)截断到 N;N 由调用方按 design.md 候选上限公式代入预算参数得出,本单元不查账本。**force_include 不在本单元生效**——override 的 force/score 阶段边界在评分与组装(单元三),预筛只看 exclude。
9. **淘汰**:rejected/落选条目次日自然可再入围(无冷却);discovered_utc 滑出 48h 即不再成为候选(digest-design §4.6)。

## 4. 输入输出

**输入**:
- 上游 CandidateRow(design.md collect.py 契约):url / title / published_utc / fetched_utc / content_text / source_name;
- sources.yaml(tier 映射、priority、exclude、unknown_source_tier)、selection.yaml(title_blacklist);
- override 表(exclude 键集);
- entry 表现状(status、既有正文);
- 候选上限 N(调用方提供,≥0;N=0 合法=本期不新增评分)。

**输出①:entry 行**(spec §5.3 DDL,本单元只写身份与内容字段,不碰 status):
- 新 identity_key → 插入:identity_key / url(原始 URL 展示用)/ title / source_name / source_tier(多源合并后被选源的档位;未登记或 name 空 → unknown_source_tier 默认 T2,记 warning)/ published_utc(可空)/ discovered_utc(=首次 fetched_utc)/ content_text(可空)/ status 默认 'pending'。
- 已存在且未 used 且(content_text 由空变非空或内容变化)→ UPDATE content_text、title;**不改** identity_key/url/discovered_utc/source_*。
- 已存在且 used → 不动。

**输出②:issue_freeze.manifest_json 成员**(冻结快照,自足重放的最小字段集):

| 字段 | 来源 | 说明 |
|------|------|------|
| identity_key | 归一 | 判重键,成员唯一标识 |
| entry_id | entry 表 | 链接台账(status 查询/占用核对) |
| url / title | 合并行 | url 保留原始形态(R1 只用于判重键) |
| source_name / source_tier | 合并行 | 展示与门槛用 |
| published_utc / discovered_utc | 合并行 | published 可空;排序平局依据 |
| content_text | **冻结时点快照** | 全文;空值允许(进冻结、被预筛剔) |
| content_hash | sha256(content_text) hex | 进入评分请求身份(request_hash 输入之一,单元二/三) |

**输出③:预筛入围清单**:manifest 成员的有序子集(§3 规则 7-8),交评分单元。

**正常样例**(延续 digest-design §3.1 虚构口径):窗口 34 条 → 去重合并 34 条(无同键)→ 冻结 entry_count=34 → 预筛剔空正文 8、黑名单 1、used 2 → 余 23,N=12 → 截断排序取 12 交评分(其中含后入选的展示分 20 强制项?否——强制项不经预筛特殊处理,只要它在冻结集且未被 exclude 剔除,按同规则参与截断;若被截断排除,force 边界在评分/组装阶段处理,见 digest-design §5.2 与单元三设计)。
**非法输入处置**:scheme 非 http/https(R0 invalid)→ 跳过并记日志;上游行缺依赖字段 → 依赖测试红,按 E2;同 identity_key 上游多行平局三依据仍同 → name 字典序必收敛,不存在悬空。

## 5. 数据与状态(存储映射定稿)

**新增 `issue_freeze` 表**(DDL 已同步 spec §5.3,第 9 张表;check_docs expected 同步):

```sql
CREATE TABLE issue_freeze (
  issue_date TEXT PRIMARY KEY,            -- YYYY-MM-DD;一期恰好一条,已存在则不覆盖
  frozen_utc TEXT NOT NULL,               -- 确认写入时间(=事件发生时间)
  entry_count INTEGER NOT NULL CHECK(entry_count >= 0),  -- 允许 0(空集合是合法冻结)
  manifest_json TEXT NOT NULL             -- 成员清单 JSON(字段见 §4 输出②)
);
```

**关键决策与理由**:

- **行存在且完整 = 冻结确认事件**(digest-design §4.4 的物理化)。单行 INSERT 原子提交,不存在"半个冻结";半途中断 = 行不存在 = 未冻结,下次从头采集。空集合 = entry_count=0 的行,与"无行"语义不同。
- **digest_issue 不新增 generating 状态**:"生成中(已冻结)"由 issue_freeze 行承载;digest_issue 行仅在产出产物(draft 起)或记失败(E2/零候选/零合格)时创建——spec §5.3 的 `CHECK(status='failed' OR markdown_path IS NOT NULL)` 与四值枚举保持不动,DDL 改动最小。
- **manifest 含全文快照而非仅 hash(决策)**:entry.content_text 会被后续期的正常采集刷新(v3 快照边界),旧期续跑必须读旧输入才能保持请求身份不变、回执复用成立(digest-design §4.6);只存 hash 将无法重放已被覆盖的正文。这是满足四场景的**最小**存储方案——不引入 entry 版本表或通用版本管理。
- **collect 本地写单事务**:上游读取(只读连接)完成后,entry 全部 upsert + issue_freeze INSERT 在**同一写事务**内提交。崩溃 → 整体回滚 → 无冻结行;entry 幂等使重跑无损。WAL + flock 单实例下长事务可接受(数百行级,毫秒)。

**写入协议(collect_once)**:

```text
输入: issue_date, 上游DB, 配置, now
1. issue_freeze 已有该期行? → 返回 frozen(跳过采集,幂等入口)
2. 只读查询窗口候选(data-source JOIN 契约);记录 item_total/query_ms(规模护栏)
3. 逐条 normalize → R0 invalid 跳过记日志;同 identity_key 内存合并(平局规则,记日志)
4. BEGIN IMMEDIATE:
     a. 逐成员 entry upsert(INSERT OR IGNORE / 未used且变化则 UPDATE)
     b. 组装 manifest(含 content_hash),INSERT issue_freeze(单行)
     COMMIT                          ← 冻结确认事件在此刻发生
5. 预筛(纯函数,读 manifest + 配置 + override/entry 现状) → 入围清单
```

失败原因持久化:E2 时写 digest_issue failed 行(entry_ids='[]',无 markdown_path)+ 结构化日志 `stage=collect event=collect_failed`;**失败阶段/原因等恢复字段的位置属期状态存储映射(spec §5.3.1),未决项见 §9,本单元以日志为最小证据**。

## 6. 异常与恢复(四场景 + E2)

| # | 场景 | 现场状态 | 恢复判定与动作 | 费用 |
|---|------|----------|----------------|------|
| A | 正常冻结后中断(评分/摘要阶段崩溃) | issue_freeze 行在;可能已有回执 | 重跑:幂等入口命中步骤 1 → 读 manifest 续跑;已收响应按请求身份复用 | 不重复付费 |
| B | 冻结空集合 | issue_freeze 行在,entry_count=0 | 下游零候选 → digest_issue failed(no_candidates);零 attempt | 零 |
| C | 写入中断(collect 事务中崩溃) | **无 issue_freeze 行**;entry 可能残留部分?否——单事务已回滚 | 该期零回执 → 冻结未发生 → 重新 collect(窗口=重跑时刻;digest-design §4.4 判定规则);"无行但有回执"=数据异常,拒绝续跑转人工排查(理论不可能:评分仅在冻结后) | 已有回执照常复用 |
| D | entry 已被新期刷新,旧期续跑 | entry.content_text 为新值;旧期 manifest 为旧值 | 旧期一切续跑**只读 manifest**(content_text/content_hash 用快照),不读 entry 现值;entry_id 链接仍有效 | 旧请求身份不变 → 旧回执复用 |
| E2 | 上游打不开/权限/schema 红 | 无冻结行;digest_issue failed | 退出码 3;通知连续 2 期去重;修复后人工显式重跑=重新 collect | 无 |

**边界区分**:`no_candidates`(冻结空集合)与"预筛全剔但冻结非空"不同——后者走零入围→评分零过线→组装记零合格 failed,不属本单元落库。两条失败路径的期行都由下游创建,本单元仅 E2 落 failed 行。

## 7. 验收场景(M1 plan 强制测试种子;输入→期望)

1. **判重样例**:design.md 五个 URL 期望表逐条断言 identity_key;多源同 key(T1+T2 同 URL)→ 选 T1 行,tier 记 T1,选择依据在日志。
2. **冻结原子性**:在步骤 4 事务内注入中断(kill)→ issue_freeze 无行、entry 无半写;重跑成功且结果与未中断一致。
3. **幂等入口**:同 issue_date 二次 collect_once → 直接返回 frozen,上游查询次数=0(可用查询计数替身断言)。
4. **空集合**:窗口内 0 条 → freeze(entry_count=0,manifest='[]')落地;零 attempt;digest_issue failed(no_candidates)由下游写入。
5. **快照刷新**:同 key 二次读取正文空→非空且未发布 → entry 更新;**新一期** manifest 用新 content_hash;**旧期** manifest 不变,旧期续跑请求身份=旧 hash(回执复用)。
6. **used 不刷新**:status='used' 条目再读取 → entry 与 manifest 均不反映新正文。
7. **discovered_utc 锚定**:内容刷新再读 → discovered_utc 不变;滑出 48h 后不再入围。
8. **预筛矩阵**:黑名单/死源/空正文/used/selected/override-exclude 各一例被剔;截断排序确定性(同输入两次运行同输出);N=0 → 空入围,无异常。
9. **E2**:上游文件以拒绝只读方式打开 → digest_issue failed 行落地、退出 3、collect_failed 日志。
10. **规模护栏**:item_total>50k 或 query_ms>1000 → warning 日志(design.md collect 契约)。

## 8. 依赖与维护成本

- **零新增依赖**:Python 标准库(sqlite3/json/hashlib)+ 既有 config 契约;不引入版本管理库/平台。
- **manifest 体积**:估算 ~200 条/期 × 平均 3KB ≈ 600KB/期,年 ~220MB,随 engine.db 每日备份(spec §7)。M1 接受;终态期(published)超 30 天后可清理正文只留成员与 hash——**运维观察项,不预先实现**(触发条件写入 runbook 时再定)。
- **可复用**:normalize 规则表与 design.md 样例共享一份测试夹具;预筛纯函数可独立单测。

## 9. 未决项(按设计评审规范写法)

| 未决项 | 验证方法 | 通过条件 | 失败后的备选 | 定位 |
|--------|----------|----------|--------------|------|
| 失败阶段/原因等恢复字段的存储映射(E2 落行时仅日志) | 单元五按 spec §5.3.1 清单设计 | §6 各中断窗口后状态可判定且原因可查 | digest_issue 扩列(如 reason/updated_utc)或独立 run 记录表 | 调度与运行维护(本单元消费其结论) |
| 上游 15 源线上 fetched_utc 分布与正文覆盖率(本地库 12 源/90 条为样本) | M1 部署期服务器实测,回填 data-source | 48h 窗口候选量级与 manifest 体积估算被证实或修订 | 调整窗口/预筛参数(运营参数,不动结构) | 本单元(观测)/部署核查 |
| 服务器侧 DB 路径、只读 WAL 权限 | M1 启动前核查清单(spec §11) | mode=ro 以 engine 运行用户验证通过 | 调整部署路径/权限,不改契约 | 部署核查 |

## 评审提示

本设计关闭了 digest-design §7 原"冻结确认标志/候选清单/输入版本快照/期归属的存储映射"未决项(issue_freeze);新增决策共 5 处(§5 关键决策 4 处 + discovered_utc 锚定)。阻塞问题=四场景推演与 DDL 是否成立;manifest 体积与保留策略是运维观察项,不阻塞。
