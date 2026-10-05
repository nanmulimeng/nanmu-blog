# 会话交接:单元一评审修订——占用/N 作用范围、双层窗口、强制项交接、最终平局键(2026-10-05)

- **recorded_at**: 2026-10-05 Asia/Shanghai
- **continues**: [单元一设计交接](2026-10-05-unit1-data-ingestion.md)
- **repository**: main;本轮一个提交(见 git log),未推 origin/server。
- **objective**: 用户评审单元一:接受"独立冻结表+全文快照+单事务写入"方向但**不通过**,指定四组阻塞问题定点修订+对应验收样例,保留已接受的冻结存储方案。本轮只改这四组与非阻塞同步项,修订闭合后进单元二。

## 评审输入(用户裁定)

- 接受:issue_freeze 独立表方向、manifest 全文快照、collect 单事务、discovered_utc 语义、预筛纯函数拆分——但占用/N 的**作用范围**与预筛**完整接口**暂不接受。
- 四组阻塞(逐条映射见下);非阻塞:cost_pending 分层、§4.5 清理、manifest 体积观察项、"数百行毫秒"改待实测、pipeline 8 表→9 表与组装字段补 cost_pending。
- 归属表:费用快照→单元二/三;prompt 权重→单元三;暂停撤回恢复→单元四/五;调度截止→单元五。

## change_scope(全部文档,[units/data-ingestion.md](../engine/units/data-ingestion.md) 为主)

**① 占用与 N_new 作用范围(P1)**:预筛排除拆两层——内容/编辑排除(黑名单/死源/空正文/used/override,适用全体含本期 selected)+占用排除(`selected` 归属期≠本期才排除;=本期→`recoverable` 续跑恢复不截断)。N_new 收窄为**仅限新增付费评分**条目数:N_new=0 → to_score 空而 recoverable 照常(消除与 design.md"N=0 但允许零网络复用"的冲突);scored 条目回执复用归评分单元按请求身份判定,预筛不查 analysis/receipt。纯函数等价输入补占用/override 快照。占用归属存储(entry 建议 `claim_issue` 列)标注为**单元一×单元三联合定稿的未决项**,不标已关闭。验收 8/9 两例锁定。

**② 双层窗口(P1)**:上游 `fetched_utc` 近 48h=读取范围;本地首次 `discovered_utc`=新期候选资格。三落点:manifest 时间取固定 entry.discovered_utc(不取本轮合并行新时间);冻结成员形成前执行资格过滤(超窗记 `candidate_expired`);旧期续跑不复查资格。新键初值=本轮同键行**最早** fetched_utc(与胜出行选择独立)。验收 7 锁定(旧身份今天再进窗口→不进新期,旧期照常续跑)。

**③ 强制项截断交接(P1)**:预筛输出改 **PrescreenResult 四去向**(to_score/recoverable/excluded/capped)+**全覆盖不变量**(并集=manifest 全体、每成员恰一去向)——不遗漏由接口结构保证;单元三组装边界比对有效 force 集合,强制项未完成评分→暂停转人工(动作本体归单元三)。force_include 不在预筛改变排序/截断。验收 10 锁接口(强制项落 capped 可见、不静默发布)。

**④ 最终平局键(P2)**:name 字典序不保证收敛(同源多 URL 归并同 key 时 tier/priority/name 全同正文不同)。规则本体落 [design.md](../engine/design.md) 判重节:平局链末补**上游 item.id 升序(最小者胜)**,行序变化不改选出行/正文/hash;单元文档引用。验收 11 锁定。

**非阻塞同步**:pipeline.md 数据落点 8→9 表(加 issue_freeze)、组装行 frontmatter 补 cost_pending;digest-design.md §7 加回"占用归属持久化"未决项行(预筛消费接口已定,写入/释放协议联合定稿)+评审提示改为"占用归属存储仍开放";collect 单事务耗时改"待 M1 实测"。

验收从 10 例扩到 **13 例**(7 双层窗口/8 预筛矩阵与占用分层/9 N_new=0/10 强制项可见性/11 平局收敛)。

## state

- 四组修订均按用户裁定落盘,**待用户复核**;冻结存储方案(issue_freeze/全文快照/单事务)未动 [verified: 本轮 diff 不含 §5 DDL 变更]
- 预筛接口(prescreen 签名含 issue_date/占用快照/override 快照/N_new;PrescreenResult 四去向)是**修订后的候选契约**,用户明示"不能把当前预筛接口视为已定稿"——单元二引用时按此口径 [declared]
- 单元二可先行整理的费用快照/attempt 结算不依赖本轮四组问题;N_new 计算消费本接口

## verification

| 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
|--------------|----------------|--------------|
| 仓库根 | `python scripts/check_docs.py --snippets --bash … --node …` | 见当轮输出(md/links/DDL/schema 一致) |
| 仓库根 | `git diff --check` | 通过 |

- **disposition**: continuable(修订待用户评审;闭合后进单元二)
- **next_action**: 用户复核四组修订与验收 13 例;确认后进入《模型调用与费用治理》单元(费用快照/attempt 结算可先整理,N_new 消费本接口)。M1 plan 与编码仍暂停。
- **omissions**:
  - 占用归属的写入事务(置 selected 同事务写/发布清/放弃清)留给单元三联合定稿——本轮只定消费接口。
  - 用户侧待办不变(skills DNS/ICP/origin 推送/验收目录清理/Task10);线上仍 c8a4567。
