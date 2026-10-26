# ADR-0012: 上游数据源变更——td 聚合链退役,engine 多 feed 直连轻量采集

- 状态:已接受(2026-10-26 用户拍板:爬虫 MVP 按 aihot 路线,采集不自研全网抓取,直接消费在线聚合站,轻量化,服务器资源受限;同日经用户指令扩展为多 feed——「调研一批和 aihot 一样的高质量信息收集网站集成进爬虫」)
- 日期:2026-10-26
- 关联:spec §5(上游契约)/[ADR-0002]/[topic-digest-data-source.md](../context/topic-digest-data-source.md)(旧契约,自此为历史)
- 取代范围:上游=td SQLite 快照(方案 A)的运行时依赖;spec 六模式借鉴(AIHOT 项目)不变

## 背景

原设计 engine 只读 td 的 SQLite 快照(方案 A)。真实运行暴露:td 上游多源 RSS 停更(量子位 10-23 起)、死源长期失败,engine 池子被弱内容淹没;而用户判定 td 属可退役的过渡系统,要求 MVP 按 AIHOT 路线走且**采集不自研**——直接消费在线聚合站的 RSS。单源 aihot.news 断粮风险高,故同日多源化。

## 决策

1. engine 新增轻量模块 `ingest`:多 feed 直连(清单见下表)→ identity_key 归一判重(既有 normalize)→ 写 entry 表;discovered_utc=首次入库时刻(48h 资格语义保持);published 滑出 7 天窗口的条目不入库(防全量历史 feed 污染资格池)。
2. **失败隔离**:单 feed 失败=告警跳过(其余源继续);全部 feed 失败才 E2(CollectError,与 collect 同语义)。hourly 落库,单源下小时自动重试。
3. sources.yaml:ingest 源显式登记(tier 真相源);未登记源落 unknown_source_tier(T2 保守档)并告警留痕。
4. 编排:环境变量 `NANMU_INGEST=1` 时 run 走 ingest 路径(写 entry+freeze),不再读上游快照;原 collect(td 路径)代码保留,双轨可切。
5. 定时:ingest_entries 挂 hourly timer(独立 unit);run 维持每日 08:30。
6. **td 退役**(用户方向):engine 不再依赖后,td 侧动作(停 timer/下线)另行按授权执行;在其确认退役前不删任何 td 数据。

## 源清单(2026-10-26 服务器实测)

| 源 | feed | tier | 实测 |
|---|---|---|---|
| AIHOT | aihot.news/feed.xml | T1 | 50 条/日更,desc 179-295 |
| Techmeme | techmeme.com/feed.xml | T2 | 15 条,desc 324-515 |
| MarkTechPost | marktechpost.com/feed/ | T2 | 10 条,desc 281-510 |
| Hacker News | hnrss.org/frontpage?points=100 | T2 | 10 条,desc 134-571(短条目被预筛自然过滤) |
| MIT Tech Review AI | technologyreview.com/topic/artificial-intelligence/feed/ | T2 | 10 条,desc 352-405 |

调研淘汰(及理由):OpenAI Blog(全量历史 1318 条+正文 <200 字全被预筛灭)、TLDR AI(feed 404)、VentureBeat AI(HTTP 429 反爬)、The Verge(Atom 且非 AI 专属)、机器之心(无 RSS)、TechCrunch AI/少数派/小众软件(RSS 摘要 <200 字,预筛全灭——td 时代有全文抓取管道故可用,ingest 直连不可)。

## 后果与边界

- 多源互备:单源停更/改版不再断粮(单源风险=本 ADR 初版的已知边界,多 feed 化后缓解)。
- content_text 质量为 feed 摘要级(200-500 字)——预筛「正文>200 字」仍生效,过短如实跳过;HN 短条目被自然过滤属设计行为(2026-10-26 本机 E2E 实测:单源网络失败不影响其余源落库)。
- 服务器资源:5 feed × 每小时一次 HTTP(合计 ~500KB/h),可忽略;不部署任何新常驻进程。
- 「AIHOT 式归一」等六模式借鉴不变;本 ADR 只换数据来源,不动评分/预算/发布契约。
