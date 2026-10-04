# 文档系统审查与依据(2026-10-02)

## 范围与当前状态

本轮为文档修订,没有搭建 site/engine、调用付费模型或操作服务器。起点为本仓库 `74c23f8`;M0 Task 1 的提交 `c0e8a84` 存在,Task 2 尚未开始。应用、部署工件与部署 runbook 均未落盘。

目标是修正会导致实施失败、误读历史或过度宣称完成的文档,不扩展 M0/M1/M2 的产品范围。设计变更见 [ADR-0009](../decisions/0009-preimplementation-contracts.md),当前设计仍以 spec 为准。

## 依据与证据等级

| 依据 | 本轮读到什么 | 能证明什么 / 不能证明什么 |
|------|--------------|--------------------------|
| `D:/software/item/nanmuli-blog/docs/new-project-research/2026-08-29-group-wisdom.md` | 历史复盘汇总,包含范围失控、元工作挤占产品工作、自用反馈与止损线 | 支持历史设计动机;其中外部案例、法律结论、价格不作为当前事实继承 |
| `D:/software/item/topic-digest/m0-report.md` | 2026-08-31 的 Node v20.18.1、73 个测试、241MB 构建峰值、正文抽取 74/113 等记录 | 历史验收证据,本轮未重跑、不能保证当前服务器相同 |
| topic-digest 本地 HEAD `f25d187` 下的 `schema.sql`、`src/topic_digest/pipeline.py`、`cluster.py`、`extract.py`、`config.py` | cluster 实际写入、item 变 clustered、无 summary 列、默认数据库路径与环境覆盖 | 本地源码事实;不能证明线上 commit、实时行数或权限 |
| 当前仓库文件清单、Git 历史与所有现有文档 | 文档与基础配置存在,应用目录不存在 | 可确认 Task 1 与文档阶段状态;不能称博客已上线 |
| 官方文档与带 tag 源码(下列链接) | Astro render、分页、版本要求;Git hook;SQLite 只读 WAL/FTS;DeepSeek 价目 | 来源内容已读;目标部署与账户限额仍需实测 |

9 月 720/720、30/30、3,491 条以及 2026-10-02 服务器空闲内存等,本轮未找到随仓库保存的原始巡检输出。保留为上一会话转述的历史记录,不升级为本轮 verified。旧博客 601 行悬置等精确数字也未重做取证。

## 发现与处置

| # | 问题及影响 | 本轮处置 / 后续验证 |
|---|------------|---------------------|
| 1 | README 宣称可开发与自动部署,实际应用不存在;spec 仍称草案;Task 1 未勾选 | 入口写明当前状态,区分未来命令,更新 Task 1;历史 session 保留并由新 session 接续 |
| 2 | 下阶段计划成为当前阶段验收前提;Task 7 前要求不存在的 verify;正常门禁又要求提交坏 main | 明确分阶段验证与进入下一阶段条件;韧性测试改独立验收 bare repo+发布目录,生产 main 始终绿 |
| 3 | Content Layer 示例使用旧的 `entry.render()`;create latest 无法保证 Astro 5;Node 最低版本写死 | 改 `render(entry)`;手动最小脚手架显式安装 Astro 5 并锁版本;Node 以所选包 engines 为准 |
| 4 | 首篇仍 draft 却期待详情输出;冒烟把字符串包含视为 XML 合法,也没检查详情泄漏 | 修正空态预期,补文章列表空态与草稿详情/页面检查;XML 用标准解析器验证,负例不再要求错误必须来自 smoke |
| 5 | hook 标称后台却前台执行;忙时跳过最新 push;部分 dist 可被误当成功;共享 checkout 受 ref 更新影响 | 后台有界锁等待、锁后解析 SHA、按 SHA archive、verify 后发布完整目录、线上 SHA 标记、失败重跑与并发验收 |
| 6 | engine commit 被等同发布 | 区分生成/提交/push/线上确认;专用工作副本,冲突不强推;M1 补发布幂等测试 |
| 7 | cluster 被写成空表;若只选 fresh 将遗漏正常数据 | 修正为已有单条目 cluster;读取 fresh/clustered,排除 dropped;补 JOIN 字段、fetched_utc 与空文本测试 |
| 8 | 正文为空却声称能回退 summary | 明确无独立 summary 列,空文本不自动生成事实摘要;上游长摘要跳过抓页后未写入 content_text 的路径只记录、不修改上游 |
| 9 | 双评分数学解释错误 | 保持平均阈值公式,纠正“一致高分”“更严”表述;不宣称本项目尚未测量的质量收益 |
| 10 | 7 个 CREATE TABLE 却称 8 表;累计 attempts 无法准确统计每次重试窗口;仅次数无法保证金额 | 增 receipt_attempt,窗口计数按尝试时间;补月/期预占、未知费用保留与请求身份要求 |
| 11 | 每小时 100 次与日均 116 条×2 评分不匹配 | 明确候选截断/留出摘要与重试额度,M1 实测调用容量;不把预算正常截断当整期失败 |
| 12 | 全挂退出 0、OnFailure 告警及连续失败规则冲突 | 非成功期退出非零,阈值通知由通知脚本去重;通知使用本项目 env,不修改上游 |
| 13 | 价格、sqlite-vec 固定版本、免费 embedding、性能被当已验证事实 | 价目改为官网读取快照与复核要求;sqlite-vec/bge-m3 保留选型方向,安装版本/免费额度/内存延迟列为阶段前置核查 |
| 14 | RAG 全部内容是否含 draft、中文 FTS 效果、付费问答记账与只读库关系未定义 | 只索引已发布内容;rag.db 只读不等于账本只读;补中文短词/无证据拒答/删改索引/M2 月预算测试入口 |
| 15 | 本地异地 Git 副本被泛化为备份;锁权限与只读 WAL 访问前提遗漏 | 区分源码与数据库备份,补只读权限/WAL探针、timer 时区实测和恢复验收 |

## 关键官方来源

- [Astro 5 迁移说明](https://docs.astro.build/en/guides/upgrade-to/v5/#updating-existing-collections):新 Content Layer 使用 `render(entry)`。
- [Astro 5.13.2 paginate 源码](https://github.com/withastro/astro/blob/astro%405.13.2/packages/astro/src/core/render/paginate.ts):`Math.max(1, ...)` 会为空数组保留一页。因此本轮没有将 `paginate([])` 误判成已确认 bug;仍须对实际安装版本做空态构建验收。
- [Astro 5.13.2 package.json](https://github.com/withastro/astro/blob/astro%405.13.2/packages/astro/package.json):Node engines 已不等同旧计划的 `>=18.17.1`;此 tag 是核查样本,不是本项目预先锁定的版本。
- [Git hooks](https://git-scm.com/docs/githooks#post-receive):接收更新触发 post-receive;本地 commit 不能替代 push,hook 失败也不撤回已接收提交。
- [SQLite WAL 只读条件](https://www.sqlite.org/wal.html#read_only_databases):只读 WAL 访问依赖 sidecar/目录访问条件;不能对持续写入的上游使用 immutable 绕过。
- [SQLite FTS5 tokenizer](https://sqlite.org/fts5.html#tokenizers):中文召回、trigram 可用性与短查询需要目标环境测试,不能把“有 FTS5”当作中文降级已验收。
- [DeepSeek 官方价目](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/):本轮读取到 Flash/Pro 与峰谷价,原文档的 chat 固定价不能沿用;快照见 budget.md,实施时再次复核。
- [sqlite-vec 官方说明](https://alexgarcia.xyz/sqlite-vec/):pre-v1 需要锁版本和兼容验证。本轮未取得足够证据确认原文档指定的 0.1.9 安装组合,不保留“已验证稳定版”断言。

## 未闭合项与处理时点

| 时点 | 必查项 | 通过证据 |
|------|--------|----------|
| M0 Task 2–7 | Node/所选 Astro 5 和 RSS 精确版本;空 feed/分页;详情 render;零 JS;RSS XML | package-lock + engines + 本地 build/smoke + XML 解析 + 人工视觉结果 |
| M0 Task 8–10 | Linux hook 权限/锁/超时;同机 Caddy;SSH;DNS;失败与并发发布;回滚 | 独立验收目标日志、SHA 与 HTTP 结果;生产首篇发布计时 |
| M1 plan 启动 | 线上上游版本/只读权限/正文覆盖率;候选预算;URL 归一语义;计价/请求上限;发布冲突恢复 | 只读探针 + 样本评估 + 故障测试计划;API key 仅服务器 env |
| M2 plan 启动 | embedding 可用/计价/维数;Python SQLite 实际能力;中文 FTS;来源拒答与索引更新;延迟 | 少量固定问题集 + 目标机试验 + p95 延迟/峰值内存 |

文档修正不等于这些能力已实现。正文各责任文件同步本轮结论;此表负责审查证据,不另造一套设计真相源。

## 本轮实际验证

临时验证器共22项检查通过(验证器使用后移除,未增加项目运行依赖):

- 扫描33份Markdown,56个本地相对链接全部存在;忽略代码示例与外部URL。
- 从spec提取SQL,在Python SQLite内存库完整执行,确认8张业务表及调用尝试字段。
- 从M0计划提取两份部署脚本,Git Bash执行`bash -n`通过;这是语法检查,未运行Linux部署。
- 四段JavaScript用`node --check`通过,两段JSON能解析。
- 从计划提取smoke.mjs,在临时静态产物中验证:完整空站通过;缺RSS、草稿详情、script标签、草稿链接分别失败;恢复后通过。
- 核对Task1四项勾选、旧render方法消除、未创建site/engine/deploy。

`git diff --check`通过。未执行实际Astro build、服务器并发/回滚或付费模型请求,因此未勾选对应实施任务。
