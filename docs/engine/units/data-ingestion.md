# 数据接入与候选管理·单元详细设计(M1 第 3 步·单元一)

> 状态:**部分通过复核;复用/付费容量交接已由单元二联合定稿并回填;占用写入与释放协议已由单元三定稿(entry.claim_issue,spec §5.3 已同步);整体尚未达到可开发状态**(2026-10-05 批量闭环轮)。第 3 步五单元之首,以 [digest-design.md](../digest-design.md) v3 为功能输入基线。
> 定位:回答"上游材料如何变成身份稳定、可追溯、按期冻结的候选"的**实现层设计**——存储映射、写入协议、事务边界、恢复行为、验收场景。功能语义(冻结契约/状态×操作/人工操作)以 digest-design 为准,本文不重复;与上游契约冲突时先改上游再回改本文。
> 引用而非复制:判重规则 R0-R7 与多源平局见 [design.md](../design.md) identity_key 节;上游只读契约与依赖字段清单见 [data-source](../../context/topic-digest-data-source.md);DDL 真相源在 [spec §5.3](../../superpowers/specs/2026-10-02-nanmu-blog-design.md);候选上限公式见 design.md 候选上限节;窗口/阶段划分见 [pipeline.md](../pipeline.md) 阶段表。

## 0. 单元边界与接口交接

| 数据 | 本单元职责 | 相邻单元职责 |
|------|-----------|--------------|
| 上游 topic-digest SQLite | **只读**(mode=ro,48h 窗口 JOIN,data-source 契约) | 任何人不得写上游(铁律 4) |
| engine.db `entry` 表 | **唯一写入者**(创建/判重合并/未发布刷新;不写 status 与占用归属) | 评分单元改 status(pending→scored→…)并**同事务写占用归属**(见下);发布单元确认后置 used |
| entry 占用归属(selected 的期归属) | 预筛**消费**(本期/他期判定) | **写入协议由单元三定稿**(置 selected 时同事务写、发布确认置 used 时清、放弃失败期人工清);建议形态=entry 加 `claim_issue` 列,不预设 |
| engine.db `issue_freeze` 表 | **唯一写入者**(冻结确认事件) | 全管线只读;调度单元凭该行判定"生成中,已冻结" |
| engine.db `digest_issue` 表 | 仅 E2 时写 failed 行 | 组装写 draft,发布推进 submitted/published(单元三/四) |
| 候选上限 N_new 与复用快照 | 消费:预筛签名 `prescreen(manifest, issue_date, 配置, 占用快照, override 快照, 复用快照, N_new)` 纯函数 | **均由模型调用与费用治理单元提供**([model-calls.md](model-calls.md)):N_new=确需新增付费评分容量(design.md 公式);复用快照=`reusable_scores` 只读判定结果;先复用后截断(§3 规则 8) |
| 预筛输出(PrescreenResult) | 产出:四去向全覆盖的结构化结果(§4) | 评分单元消费 to_score/recoverable(recoverable=**评分网络零新增**,单义,见 §4 输出③);组装单元(单元三)凭全覆盖不变量比对强制项,不遗漏责任在接口结构 |

## 1. 目标与范围

**解决**:一次 collect 从上游读取→判重入库→冻结确认→预筛截断的完整可恢复链路;entry 台账的创建与刷新规则;期候选快照的存储与重放。

**本单元做到**:窗口读取、判重、多源合并、entry 幂等写入与刷新、冻结确认落库、确定性预筛与截断、E2 失败记录。

**明确延期**(归属后续单元):评分与摘要(单元三);费用授权与 N 的计算(单元二);产物组装与期状态推进(单元三/四);跨期调度编排、补跑顺序、暂停标志存储(单元五);失败原因/重试计数/通知去重键的持久化字段映射(spec §5.3.1 清单,单元五定稿)。

## 2. 使用场景

| 场景 | 触发 | 前提 | 正常完成后 |
|------|------|------|-----------|
| 新期采集 | 调度触发该 issue_date 首次运行 | 上游可达;该期无 issue_freeze 行 | entry 台账就绪;issue_freeze 行落地;预筛输出入围清单交评分 |
| 续跑(同期再次进入) | 调度自动推进或人工重跑 | 该期 issue_freeze 行已存在 | **跳过采集**,直接读 manifest 走预筛及以后(digest-design §4.4) |
| 预筛单独重放 | 排查/配置调整 | 冻结已确认 | 预筛是纯函数:同 manifest+同 issue_date+同配置+**同占用/override/复用快照**+同 N_new → 同结果,零付费、无副作用 |
| 状态查询 | `status --issue` | — | 只读展示冻结成员数/入围数/entry 统计(digest-design §3.5 格式) |

## 3. 业务规则(优先级从高到低)

1. **只读上游**:mode=ro、不加索引、不改 schema;依赖字段清单以 data-source 固化,schema 漂移由依赖测试先红→按 E2 处理(data-source 只读契约)。
2. **窗口**:`fetched_utc` 近 48h;JOIN `item.source_id=source.id`,取 `source.enabled=1` 且 `item.status IN ('fresh','clustered')`,排除 dropped(data-source 实施读取契约)。窗口锚定 `fetched_utc`(采集事实),展示排序才用 `published_utc`。
3. **判重与合并**:identity_key 归一按 design.md R0-R7;同 identity_key 多源多行在内存合并为一条,平局依据 tier(T1 优先)→ sources.yaml priority(小者优)→ source.name 字典序,选择依据写日志;**合并不提高可信度**。
4. **entry 台账**(写入规则见 §5):`INSERT OR IGNORE` 创建;已存在且 `status != 'used'` 且正文变化时刷新;`used` 条目永不刷新(data-source"M1读取与快照补充")。
5. **双层窗口(决策,2026-10-05 评审修订)**:**上游 `fetched_utc` 近 48h 决定本轮读取哪些行;本地 identity_key 的首次 `discovered_utc` 决定是否仍有新期候选资格**(两者是不同的检查,不能混用)。
   - 首次时间:新 identity_key 在本轮出现多行时,`discovered_utc` 初值=**本轮同键行最早的 fetched_utc**;已存在 entry 沿用其固定值,**不取本轮合并行的新时间**——不让来源胜出规则隐含决定候选寿命。
   - 资格判定:在**冻结成员形成前**执行——`entry.discovered_utc` 距本期冻结确认时刻不足 48h 才可进入本期 manifest;超窗身份记日志(`candidate_expired`)排除,不进冻结。正文刷新规则照常执行(台账事实与候选资格互不影响)。
   - **旧期续跑不做资格复查**:冻结成员以 manifest 为准,不按续跑时刻的当前时间重新淘汰,否则跨天恢复会再次破坏冻结语义(digest-design §4.4)。
   - 理由:防止同一身份借再抓取/URL 变体反复进入新期,让"不延长候选寿命"落在判定路径上而非文字说明。
6. **冻结**(功能契约=digest-design §4.4,物理实现见 §5):collect 结束写入 issue_freeze;允许空集合;半成品不算冻结。
7. **预筛排除**(顺序固定,全部本地零成本;输入=冻结 manifest 成员+占用快照;规则分两层):
   **内容/编辑排除**(适用于**全体**成员,含本期已选中条目——运营参数与 override 在续跑时可能已变化,变化结果交下游按组装边界处理):
   1. 标题命中 selection.yaml `title_blacklist`;
   2. 来源命中 sources.yaml `exclude`(死源清单——上游 enabled=1 但 feed 已坏);
   3. `content_text` 为空或纯空白(data-source 实测约 30%);
   4. `entry.status = 'used'`(已上过日报);
   5. override 表 `exclude` 命中(identity_key 精确匹配,阶段边界生效)。
   **占用排除**(只排除其他期,不排除本期——2026-10-05 评审修正,对齐 pipeline 预筛契约"含可恢复的 scored/selected"):
   6. `entry.status='selected'` **且归属期 ≠ 本期 issue_date** → 排除(被其他未完成期占用);**归属期=本期 → 不被占用排除**,其去向由规则 8 的复用判定决定(身份未变的常态进 recoverable;当前请求身份已变化时按确需新增付费参与排序,见规则 8)。归属的存储形态由单元三定稿(建议 entry.`claim_issue` 列);failed 期人工放弃时由释放操作清除归属,本单元只读现状。
8. **截断与 N_new 的作用范围(2026-10-05 评审修正,经单元二联合定稿回填)**:内容/编辑排除、占用分层后,**先做复用判定,再截断**——
   - **复用判定(输入,非本单元职责)**:编排层调用单元二 `reusable_scores(manifest 成员, 请求身份上下文)` 只读接口,得出**复用快照**(每成员 score-1/score-2 有效性+`needs` 待补清单;完成度三分=全部/部分/均未,契约见 [model-calls.md](model-calls.md) §3 规则 3/5);预筛不查 receipt,保持纯函数。
   - `recoverable` = **通过内容/编辑/占用检查且至少一条当前请求身份有效的评分响应**的成员(全部完成 needs=∅;部分完成 needs=缺失项;含本期 selected 的常态、评分完成写入入选前中断的成员、跨期同身份成员)——不占 N_new、不被截断。**recoverable 的承诺=评分进度保留、不为恢复重发已收到的请求**;needs 补全与摘要等新增调用逐次经费用授权,组装就绪另判(单元三判据)。
   - 其余合格成员=**确需新增付费评分**(score-1 与 score-2 均无有效响应),按 T1 优先 → discovered_utc 降序 → identity_key 升序(确定性排序,与展示排序不同用途)排序:`to_score` = 前 N_new 条,`capped` = N_new 之外(带序号)。**N_new=0 → to_score 空,recoverable 照常输出,capped 全可见——不因截断丢失任何可恢复工作**(对齐 design.md"N=0 但允许零网络复用"与 E5.limit"已有合格条目可继续组装")。
   - **当前请求身份已变化的本期 selected**(如 prompt 版本升级)两条响应均失效 → 按确需新增付费参与排序;被截断落 capped 可见,组装边界按"曾 selected 而无当前有效评分"暂停联动(动作归单元三)。
   - N_new 由调用方按 design.md 候选上限公式得出,本单元不查账本。**force_include 不在预筛改变排序或截断**——强制项与普通成员同规则;被 cap 或被排除的强制项由 PrescreenResult 全覆盖不变量保证可见(§4 输出③),组装边界暂停转人工归单元三(digest-design §5.2)。
9. **淘汰**:rejected/落选条目次日自然可再入围(无冷却);discovered_utc 滑出 48h 即不再成为候选(digest-design §4.6)。

## 4. 输入输出

**输入**:
- 上游 CandidateRow(design.md collect.py 契约):url / title / published_utc / fetched_utc / content_text / source_name(同轮同键多行时另需上游 item.id 作最终平局键);
- 本期 issue_date(占用分层与续跑判定的输入);
- sources.yaml(tier 映射、priority、exclude、unknown_source_tier)、selection.yaml(title_blacklist);
- override 表(exclude 键集快照);
- entry 表现状快照(status、占用归属、既有正文、固定 discovered_utc);
- 单元二提供的**复用快照**(`reusable_scores` 只读判定结果)与候选上限 N_new(≥0;N_new=0 合法=本期不新增付费评分,可复用结果照常;[model-calls.md](model-calls.md) §4)。

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
| published_utc / discovered_utc | published 取合并胜出行(可空);discovered 取**固定值**:已存在 entry 用其首次 discovered_utc,新键用本轮同键行最早 fetched_utc(§3 规则 5) | 排序平局依据;候选寿命锚点 |
| content_text | **冻结时点快照** | 全文;空值允许(进冻结、被预筛剔) |
| content_hash | sha256(content_text) hex | 进入评分请求身份(request_hash 输入之一,单元二/三) |

**输出③:PrescreenResult(结构化四去向,2026-10-05 评审修订)**:

| 去向 | 内容 | 消费者 |
|------|------|--------|
| `to_score` | **无可复用评分进度**(score-1 与 score-2 均无有效响应)、确需新增付费、排序前 N_new 的合格成员(有序) | 评分单元(新增付费) |
| `recoverable` | **至少一条当前请求身份有效的评分响应**的成员,附 `needs` 待补清单(全部完成 needs=∅/部分完成只补缺失、计数不重置;常态=本期 selected;含评分完成未写入入选的成员与跨期同身份成员;不占 N_new 不截断;仍过内容/编辑排除,命中者移入 excluded)——承诺=**评分进度保留、不重发已收到的请求**;needs 补全/摘要逐次过闸门,组装就绪另判 | 评分/组装单元(needs 补全与摘要按授权逐次) |
| `excluded` | [(identity_key, reason)]——规则 1-5 命中者(含被新命中的本期 selected)与他期占用 | 组装单元(阶段边界处理,如 §5.1 排除的重组装) |
| `capped` | [(identity_key, rank)]——排序在 N_new 之外的合格成员 | 组装单元(强制项比对,见下) |

**全覆盖不变量(接口契约)**:`to_score ∪ recoverable ∪ excluded ∪ capped` = manifest 全体成员,每个成员**恰有一个**去向。不遗漏由本结构保证——组装单元(单元三)在组装边界取有效 force_include 集,凡成员 ∉ 已完成评分集(to_score 已评完 ∪ recoverable)——即落在 capped 或 excluded——则按 digest-design §5.2 暂停组装转人工。预筛不解读 force,单元三不重算去向:双方各做一半,漏项在结构上不可能。

**正常样例**(延续 digest-design §3.1 虚构口径):窗口 34 条 → 去重合并 34 条(无同键)→ 资格过滤 0 剔 → 冻结 entry_count=34 → 预筛剔空正文 8、黑名单 1、used 2(均进 excluded 带原因)→ 复用判定:本期 selected 3(上次续跑遗留,身份未变)+ 上期已评分本轮入围且身份未变的 1 条 → **recoverable 4** → 其余 19 条确需新增付费,排序后 N_new=12 → **to_score 12 + capped 7** → 交评分。其中展示分 20 的强制项若落入 capped:to_score 完成后组装边界发现该 force 成员未完成评分 → 暂停转人工(接口保证它作为 capped 条目可见,不会被静默丢失)。

**非法输入处置**:scheme 非 http/https(R0 invalid)→ 跳过并记日志;上游行缺依赖字段 → 依赖测试红,按 E2;同 identity_key 多行 tier/priority/name 全同(同源多 URL 归并为同键)→ 按上游 **item.id 升序**最终平局键收敛(2026-10-05 评审补,规则本体在 design.md 判重节),输入行序变化不改变选出的正文与 hash。

## 5. 数据与状态(存储映射定稿)

**新增 `issue_freeze` 表**(DDL 已同步 spec §5.3——11 表中第 9 张,后续 summary/notify_sent 由单元三/五追加;check_docs expected 同步):

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
- **collect 本地写单事务**:上游读取(只读连接)完成后,entry 全部 upsert + 候选资格过滤 + issue_freeze INSERT 在**同一写事务**内提交。崩溃 → 整体回滚 → 无冻结行;entry 幂等使重跑无损。WAL + flock 单实例下长事务可接受(预期数百行级、毫秒级,**待 M1 实测**,不作已验证性能承诺)。

**写入协议(collect_once)**:

```text
输入: issue_date, 上游DB, 配置, now
1. issue_freeze 已有该期行? → 返回 frozen(跳过采集,幂等入口)
2. 只读查询窗口候选(data-source JOIN 契约,含上游 item.id);记录 item_total/query_ms(规模护栏)
3. 逐条 normalize → R0 invalid 跳过记日志;同 identity_key 本轮多行内存合并:
   - 胜出行(正文/title 来源)= design.md 平局规则(tier→priority→name→item.id 升序)
   - 新键:discovered_utc 初值 = 本轮同键行最早 fetched_utc
   - 已存在键:manifest 将沿用固定 entry.discovered_utc,不取本轮合并行时间
4. BEGIN IMMEDIATE:
     a. 逐成员 entry upsert(新键 INSERT;已有键未 used 且内容变化 → UPDATE 正文/title,
        不动 discovered_utc)
     b. 候选资格过滤:entry.discovered_utc 距 now 不足 48h 才进 manifest;
        超窗记 candidate_expired(正文刷新照常执行,资格与台账互不影响)
     c. 组装 manifest(含 content_hash 与固定 discovered_utc),INSERT issue_freeze(单行)
     COMMIT                          ← 冻结确认事件在此刻发生
5. 预筛(纯函数:manifest + issue_date + 配置 + 占用/override 快照 + 单元二复用快照 + N_new)
   → PrescreenResult(to_score / recoverable / excluded / capped,§4 输出③)
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

**预算耗尽续跑(N_new=0)**:to_score 空,复用快照命中的成员(含本期 selected、评分已持久化未写入入选者)照常输出 recoverable、不被截断——已有成果不因预算耗尽丢失;其中摘要未完成者由摘要阶段按授权决定能否补齐,组装就绪以实际结果为准(E5.limit 既有口径,design.md"N=0 但允许零网络复用");未评分条目停增(capped 可见),不阻塞组装。

## 7. 验收场景(M1 plan 强制测试种子;输入→期望)

1. **判重样例**:design.md 五个 URL 期望表逐条断言 identity_key;多源同 key(T1+T2 同 URL)→ 选 T1 行,tier 记 T1,选择依据在日志。
2. **冻结原子性**:在步骤 4 事务内注入中断(kill)→ issue_freeze 无行、entry 无半写;重跑成功且结果与未中断一致。
3. **幂等入口**:同 issue_date 二次 collect_once → 直接返回 frozen,上游查询次数=0(可用查询计数替身断言)。
4. **空集合**:窗口内 0 条 → freeze(entry_count=0,manifest='[]')落地;零 attempt;digest_issue failed(no_candidates)由下游写入。
5. **快照刷新**:同 key 二次读取正文空→非空且未发布 → entry 更新;**新一期** manifest 用新 content_hash;**旧期** manifest 不变,旧期续跑请求身份=旧 hash(回执复用)。
6. **used 不刷新**:status='used' 条目再读取 → entry 与 manifest 均不反映新正文。
7. **双层窗口与寿命锚定**:已有 entry 内容刷新再读 → discovered_utc 不变;首次发现超 48h 的身份今天经另一源/URL 变体再次进入上游窗口 → 不进入新期 manifest(candidate_expired 日志、entry 首次时间不变),且已冻结该身份的旧期 manifest 完好、续跑照常;新键同轮多行 → discovered_utc 初值=最早 fetched_utc,与胜出行选择无关。
8. **预筛矩阵与占用分层**:黑名单/死源/空正文/used/override-exclude 各一例被剔(含"本期 selected 新命中 override-exclude → 移入 excluded 带原因");**本期 selected 续跑保留为 recoverable,他期 selected 排除为 excluded(占用原因)**;截断排序确定性(同 manifest+同占用/override 快照两次运行同输出);断言全覆盖不变量(四去向并集=manifest 全体、无重叠无遗漏)。
9. **N_new=0 不裁已有成果(2026-10-05 复核扩为四子场景,单元二联合定稿)**:
   - a. 本期 selected 评分与摘要均完成、N_new=0 → 全部 recoverable,零新增网络调用,组装就绪;
   - b. 评分响应已持久化(一条或两条)、尚未写入 selected、N_new=0 → 复用快照命中 → recoverable(部分完成者 needs 只补缺失且计数不重置),不因截断丢失,下游消费已有响应重新判断入选;
   - c. 本期 selected 但摘要未完成 → recoverable 保留已完成工作;摘要仅在授权通过时调用;**接口断言 recoverable 不被当作可组装证明**(组装就绪以实际摘要结果为准);
   - d. entry 状态看似可恢复但当前完整请求身份已变化(prompt 版本升级/正文 hash 变)→ 复用判定不命中 → 参与排序落 to_score/capped,旧响应不冒充当前结果,新调用照常受 N_new 与授权限制。
10. **强制项截断可见性**:有效 force_include 成员排序在 N_new 之外(落入 capped)或被内容排除(落入 excluded)→ PrescreenResult 中该成员带去向与原因可见;接口测试断言组装消费方能据此识别"强制项未完成评分"并暂停,不静默发布缺少该强制项的日报(暂停动作本体属单元三,此处锁接口)。
11. **平局收敛**:同 identity_key 两行 tier/priority/name 全同而正文不同 → item.id 小者胜出;输入行序颠倒 → 选出行、正文与 content_hash 不变。
12. **E2**:上游文件以拒绝只读方式打开 → digest_issue failed 行落地、退出 3、collect_failed 日志。
13. **规模护栏**:item_total>50k 或 query_ms>1000 → warning 日志(design.md collect 契约)。

## 8. 依赖与维护成本

- **零新增依赖**:Python 标准库(sqlite3/json/hashlib)+ 既有 config 契约;不引入版本管理库/平台。
- **manifest 体积**:估算 ~200 条/期 × 平均 3KB ≈ 600KB/期,年 ~220MB,随 engine.db 每日备份(spec §7)。M1 接受;终态期(published)超 30 天后可清理正文只留成员与 hash——**运维观察项,不预先实现**(触发条件写入 runbook 时再定)。
- **可复用**:normalize 规则表与 design.md 样例共享一份测试夹具;预筛纯函数可独立单测。

## 9. 未决项(按设计评审规范写法)

| 未决项 | 验证方法 | 通过条件 | 失败后的备选 | 定位 |
|--------|----------|----------|--------------|------|
| ~~入选中选的占用归属存储~~ | **已定稿(单元三 §3 规则 7)**:entry.`claim_issue` 列,置 selected 同事务写、published 清、人工释放清,spec §5.3 已同步 | — | — | 已闭环 |
| ~~失败阶段/原因等恢复字段的存储映射~~ | **已定稿(单元五)**:digest_issue 扩列(fail_reason/updated_utc/last_exit/last_run_utc),spec §5.3 已同步 | — | — | 已闭环 |
| 上游 15 源线上 fetched_utc 分布与正文覆盖率(本地库 12 源/90 条为样本) | M1 部署期服务器实测,回填 data-source | 48h 窗口候选量级与 manifest 体积估算被证实或修订 | 调整窗口/预筛参数(运营参数,不动结构) | 本单元(观测)/部署核查 |
| 服务器侧 DB 路径、只读 WAL 权限 | M1 启动前核查清单(spec §11) | mode=ro 以 engine 运行用户验证通过 | 调整部署路径/权限,不改契约 | 部署核查 |

## 评审提示

2026-10-05 复核:采集、冻结、窗口、去重及预筛排除规则(含本期/他期占用区分)**已通过**;②③④组关闭。**复用识别与新增付费容量的交接已由 [model-calls.md](model-calls.md) 联合定稿并回填本文**(批量闭环轮更新:recoverable=至少一条有效响应+`needs` 待补清单,承诺"进度保留、不重发已收到的请求";to_score=均无有效响应的确需新增付费)。**占用写入与释放协议已由单元三定稿**(entry.`claim_issue`,spec §5.3 已同步,§9 对应未决项闭环)。**整体尚未达到可开发状态**。manifest 体积与保留策略、事务耗时是运维观察/实测项,不阻塞。
