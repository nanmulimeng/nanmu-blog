# 项目背景:三个前项目与本项目

> 写给零上下文的新读者(agent 或人)。读完本文你会知道:这个项目为什么存在、它从历史里继承什么、拒绝什么。

## 时间线

| 时间 | 事件 |
|------|------|
| 2026-04-03 | nanmuli-blog 启动(全栈博客+AI 内容平台) |
| 2026-06-28 | nanmuli-blog 停摆(12.5 周),带着 601 行未提交修复离场 |
| 2026-08-29 | 确认放弃,5-agent 并行复盘,形成死因结论 |
| 2026-08-31 | topic-digest M0 上线服务器(极简爬取试点),打 tag m0 |
| 2026-09 | topic-digest 全月稳定运行(720/720) |
| 2026-10-02 | nanmu-blog 设计定稿(本项目) |

## 前项目一:nanmuli-blog(废弃,反面教材)

**仓库**:`D:\software\item\nanmuli-blog`(同机不同目录,仅作历史参考,**不再开发**)。

**是什么**:Spring Boot 3.3.5/Java 21/MyBatis Plus/PostgreSQL/Redis/Sa-Token 后端 + Vue 3/Vite/Element Plus 前端 + FastAPI/Crawl4AI 独立爬虫的三端全栈系统。后端 176 个 Java 文件,crawler 1266 个测试。目标是"博客 + Web 采集 + AI 日报 + 自动优化闭环"的一体化平台。

**怎么死的**(复盘死因四段式):

1. **产品错位**:从"写博客"漂移成"AI 内容平台",博客本体始终没上线,核心价值从未交付
2. **高标准劫持"完成"定义**:每轮审计都发现新问题,修复永远追不上发现,没有一条线走到"可用即发布"
3. **零外部反馈回路**:没有真实读者/用户,质量标准只剩自我想象,范围判断失去锚点
4. **运行环境与野心差一个量级**:4GB 内存笔记本跑不动 PG+Redis+Java+crawler 全家,最终死于宿主机内存耗尽冻结验证工作

临终审计还发现:跨日去重从未生效、AI model 配置疑似无效、密钥泄漏进 git 历史、数据库 schema 四轨漂移——文档宣称的"MVP Beta 可试用"被自己的审计证伪。

**本项目继承的教训**(直接写入 spec §2 八条铁律):范围是生死线、里程碑独立可发布、博客本体永远不为 AI 加复杂度、文档过期宁可删除。

**可忽略**:它的代码不再维护;个别实现(请求层、AES 工具、资源守卫)若未来需要可去旧仓库翻,不在本项目依赖里。

## 前项目二:topic-digest(在产,上游数据源 + 运维模式验证)

**仓库**:`D:\software\item\topic-digest`;生产运行于本项目同一台服务器。

**是什么**:多主题 RSS 聚合 + 静态日报站。Python 管线(SQLite + systemd timer + flock)每小时拉取 15 个信源入河,每日构建静态页发布。**刻意极简**:无后台、无框架、无数据库服务,全部运维靠 SSH + systemd。

**成绩**:2026 年 9 月 720/720 小时级 ingest 全绿、30/30 构建成功、零故障,月入库 3,491 条。

**对本项目的两个作用**:

1. **数据上游**:本项目的 AI 引擎(M1)直接只读它的 SQLite 做日报精选——它的实况、schema、已知问题见 [topic-digest-data-source.md](topic-digest-data-source.md)
2. **运维模式验证**:SQLite + systemd timer + flock + 原子 symlink 发布这套栈已被它跑了一个月零故障,nanmu-blog 的 engine 与部署直接复用该模式

## 外部参考:AIHOT 与 PowerContext(借鉴不引入)

**AIHOT**(github.com/KKKKhazix/AIHOT):生产级 AI 资讯聚合开源框架,2026-09-28 创建、4 天约 4.9k★。Node 24/TypeScript/Fastify/PG17/pg-boss 三进程,建议 2 核 4G——对本项目 1.8G 服务器是重装备,**不整体引入**。搬走六个模式(已进 spec §5):URL 归一判重(identity_key)、双次独立评分"和判均显"、付费请求回执+三级预算熔断、编辑策略配置包(代码与口味解耦)、append-only 判断+人工覆盖、失败隔离。有趣的事实:它的官方站 feed(aihot.virxact.com/feed.xml)正是 topic-digest 的信源之一。

**PowerContext**(github.com/oceanbase/powercontext):OceanBase 出品的 agent 跨会话上下文服务器(Scope/Sources/Memory/Handoff)。评估结论**不采用**(问题域是 agent 会话交接而非知识库问答;server 栈 150-250MB;六周三版 breaking change)。搬走的:检索双通道混合 + matched_by 观测、EmbeddingProfile 身份、FTS 降级(spec §6),以及**会话交接纪律**(spec §8.1:omissions/声明分级/接手检查——直击 nanmuli-blog 跨会话断层死因)。

## 输入映射总表

| 来源 | 拿什么 | 拒什么 |
|------|--------|--------|
| nanmuli-blog | 范围铁律、文档纪律、"博客先上线" | 一体化架构、后台、伪需求(标签系统/自动优化闭环/质量趋势) |
| topic-digest | 数据上游(只读)、整套极简运维栈 | —(它保持现状不动) |
| AIHOT | 六个精选/治理模式 | 重装备栈(PG17/队列/三进程) |
| PowerContext | 检索三模式 + 会话交接纪律 | 整体采用 |

## 本项目一句话

极简静态博客(手写)+ AI 引擎自动日报(读 topic-digest 数据)+ 自用 RAG——**博客先上线,AI 是渐进叠加层,任何一层挂掉博客都在线**。
