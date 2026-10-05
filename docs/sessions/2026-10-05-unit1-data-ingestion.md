# 会话交接:第 3 步启动——契约同步+数据接入与候选管理单元设计(2026-10-05)

- **recorded_at**: 2026-10-05 Asia/Shanghai
- **continues**: [digest-design v3 交接](2026-10-05-digest-design-v3.md)
- **repository**: main;本轮一个提交(见 git log),未推 origin/server。工作区干净。
- **objective**: 用户确认 v3 收口后,按其指示进入第 3 步:①同步已裁定契约(cost_pending→spec/pipeline/schema 说明,不改 site 代码);②清理 §4.5 非阻塞文字残留;③产出五单元之首《数据接入与候选管理单元详细设计》。不编写 M1 plan,不恢复编码。

## change_scope

**① 已裁定契约同步(cost_pending 三约束)**:

- [spec §4.1](../superpowers/specs/2026-10-02-nanmu-blog-design.md):digest schema 示例加 `cost_pending: z.boolean().default(false)`(与 M0 plan 示例保持逐字段一致,check_docs contracts 空白归一比较);新增 bullet 明确**待实施契约 vs 当前 site 实现**两层(M0 未实施该键,消费代码待实施许可)。
- spec §5.3.1:公开成本段补 cost_pending 三约束句;§1.3/§4 内容模型字段列举同步。
- [pipeline.md](../engine/pipeline.md):产物模板 frontmatter 加 `cost_pending: false`(六字段计数自此与文本一致);要点与公开成本口径改为"未决=所有 actual 未核清 attempt(不限于 unknown)+同时点同源快照+显式布尔+核清三处一起更新"。
- [M0 plan](../superpowers/plans/2026-10-02-m0-blog-launch.md):schema 块与全局约束 bullet 同步,注明 M1 待实施契约属性。
- [digest-design.md](../engine/digest-design.md):§3.1 基准样例 frontmatter 补显式 `cost_pending: false`(对齐约束③);§7 评审提示更新。

**② §4.5 文字残留(用户本轮指定)**:"重新上线"行费用列收敛为"零新增模型费用;原有费用记录保留",补缺失的候选集单元格 `—`;不扩大能力、不重开评审。

**③ 单元一设计(新文档 [engine/units/data-ingestion.md](../engine/units/data-ingestion.md),设计稿待评审)**:

- 关闭 digest-design §7 存储映射未决项:**issue_freeze 表**(spec §5.3 已加,9 表;check_docs expected 同步)——行存在=冻结确认事件,manifest_json 含每成员**全文快照+content_hash**;digest_issue 不加 generating 状态(枚举与 CHECK 不动),"生成中已冻结"由 freeze 行承载。
- collect 本地写单事务(entry upsert+freeze INSERT 原子提交)→ 写入中断=无行=未冻结。
- 新决策 5 处:issue_freeze 独立表 / manifest 含全文(最小重放方案,不引入版本表) / digest_issue 不动枚举 / discovered_utc 锚定首次发现不随刷新前移 / 预筛六排除+截断纯函数(N 由单元二提供,force_include 不在预筛生效)。
- 四场景(正常冻结/空集合/写入中断/entry 刷新后旧期续跑)恢复表+10 条验收测试种子;接口交接表(entry 唯一写入者、N 归属单元二、E2 落 failed 行但恢复字段存储留单元五)。
- 未决项 3 条:恢复字段映射(单元五)、上游线上分布(M1 部署实测)、服务器 DB 权限(M1 启动核查)。

spec §8 文档树补 engine/digest-design.md 与 engine/units/;变更记录加 2026-10-05 条目。

## state

- v3 收口由用户确认(核验表+三处关闭结论,见其当轮消息);本轮所有改动仅文档与检查脚本,**site/engine 代码零改动** [verified: git show --stat]
- issue_freeze DDL 与 spec/check_docs 同步落盘 [verified: check_docs ddl_tables=9]
- 单元一设计的新决策(5 处)为**待评审状态**,用户未确认前不作为后续单元的既成事实 [declared]
- 带入后续单元的事项归属按用户当轮表:费用快照→单元二/三;prompt 权重→单元三;暂停撤回恢复→单元四/五;调度截止/任务顺序→单元五

## verification

| 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
|--------------|----------------|--------------|
| 仓库根 | `python scripts/check_docs.py --snippets --bash … --node …` | 53+ md/links 通过,errors/warnings 空;ddl_tables=9,schema_examples_match=true |
| 仓库根 | `git diff --check` | 通过 |
| spec/M0 plan | check_docs contracts 空白归一比较 | 两份 schema 示例加了 cost_pending 后仍逐字一致 |

- **disposition**: continuable(单元一待用户评审;评审通过后依序做单元二~五)
- **next_action**: 用户评审 [units/data-ingestion.md](../engine/units/data-ingestion.md)(阻塞点=四场景推演与 DDL 是否成立);通过后进入《模型调用与费用治理》单元设计(N 计算与费用快照口径在此收口),或按用户指定顺序。M1 plan 与编码仍暂停。
- **omissions**:
  - manifest 体积(600KB/期)是本地样本外推估算,服务器实测前标记为估值;保留策略(终态期清理正文)未设计,留运维观察。
  - check_docs.py 的 expected 表集改为 9 张属检查脚本维护,已与本轮提交一起落盘;若用户不认可 issue_freeze 表设计,回滚点=本提交。
  - 用户侧待办不变(skills DNS/ICP/origin 推送/验收目录清理/Task10);线上仍为 c8a4567;本地领先 origin 9 个提交未推。
