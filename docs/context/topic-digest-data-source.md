# 上游数据源:topic-digest 实况

> engine(M1)只读它的 SQLite。本文固化:它是什么、跑得怎么样、schema 契约、信源清单、已知坑。schema 部分逐字来自其仓库 `schema.sql`(2026-10-02 实读核实)。

## 它是什么

多主题 RSS 聚合静态日报站(Python + SQLite + systemd timer + flock + Astro 静态发布),2026-08-31 上线,**刻意无后台无框架**。AI 摘要能力(schema 已预留三表)从未动工——所以本项目的 engine 自建评分/摘要管线,不复用其空表。

仓库:`D:\software\item\topic-digest`;生产运行状态见 [server-environment.md](server-environment.md)。

## 运行节奏与数据量(2026-09 实测)

- hourly ingest:720/720 全绿,零故障
- 每日 release 构建:30/30
- 月入库 3,491 条(日均 116,无断档);页面滞后数据流 0~24h(实测约 13h)
- 数据新鲜度:小时级。engine 每天 08:30 读近 24-48h 窗口足够

## schema 契约(engine 依赖的就是这些)

```sql
CREATE TABLE IF NOT EXISTS item(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER NOT NULL REFERENCES source(id),
  url_hash TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  published_utc TEXT,
  fetched_utc TEXT NOT NULL,
  content_text TEXT,
  translated_title TEXT,
  status TEXT NOT NULL DEFAULT 'fresh'
    CHECK(status IN ('fresh','clustered','dropped'))
);

CREATE TABLE IF NOT EXISTS source(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic_id INTEGER NOT NULL REFERENCES topic(id),
  feed_url TEXT NOT NULL UNIQUE,
  name TEXT,
  kind TEXT NOT NULL DEFAULT 'rss' CHECK(kind IN ('rss','hackernews')),
  weight REAL NOT NULL DEFAULT 1.0 CHECK(weight BETWEEN 0.1 AND 3.0),
  enabled INTEGER NOT NULL DEFAULT 1,
  etag TEXT, last_modified TEXT, last_success_at TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  latest_item_published_at TEXT, notes TEXT
);
```

其余表:topic、cluster、cluster_member、pick、daily、api_usage——**engine 不依赖**(cluster/pick/daily 为预留空表,ADR-0003)。

engine 依赖字段清单(钉死并在测试中固化):

- `item`:url_hash / url / title / published_utc / content_text / status
- `source`:name / weight / enabled

**判重独立**:topic-digest 的 `url_hash` 与 engine 的 identity_key 归一规则可能不同,engine 用自己的 AIHOT 式归一(spec §5.2)独立判重,不依赖 url_hash 语义。

## 信源清单(服务器在产 15 源)

| 源 | weight | 备注 |
|----|--------|------|
| 机器之心 | 1.5 | **feed 已坏**(连续失败 768 次,XML 解析错误)——engine 预筛排除 |
| 量子位 | 1.5 | |
| 36氪 | 1.0 | **feed 已坏**(同上)——engine 预筛排除 |
| 少数派 | 1.0 | |
| 阮一峰周刊 | 1.5 | |
| 小众软件 | 1.0 | |
| OpenAI Blog | 2.0 | |
| Google DeepMind | 1.5 | SSL 间歇失败 ~32%(被容忍,能出数据) |
| MIT Tech Review AI | 1.5 | |
| The Verge AI | 1.0 | |
| TechCrunch AI | 1.0 | |
| Hacker News Front | 1.0 | 超时 ~12%(被容忍) |
| AIHOT(官方站 feed) | 1.0 | 二手聚合源,月产出 628 条,最多源之一 |
| AI资讯速览 | 1.0 | 每日一篇 |
| AI论文简报 | 1.0 | 每日一篇 |

源 tier 映射(T1/T2/排除)在 [../engine/selection.md](../engine/selection.md),与本文口径一致。

**注意漂移**:本地 dev 库与其 about 页面仍是 12 源旧口径;**服务器 15 源是事实**,以服务器为准。

## 已知坑(engine 设计已考虑)

| 坑 | 对 engine 的影响 |
|----|------------------|
| 两个死源每天空报警 | 预筛排除,不进评分(省调用费) |
| DeepMind SSL / HN 超时间歇失败 | 只是入库波动,读取窗口放宽到 48h 兜底 |
| 二手源(AIHOT/速览/简报)与一手源内容重叠 | engine 的 identity_key URL 归一判重天然去重同 URL;跨源同事件不同 URL 的语义去重 M1 不做(YAGNI,M3 观察) |
| `content_text` 部分为空(trafilatura 抽取率 ~65%) | 摘要写作阶段降级用 title+summary;评分阶段正常(content 为空本身是弱信号) |
| 无通知、备份本地 | 与本项目无关(铁律 4:不动它),记录在 server-environment.md 欠账清单 |

## 只读契约(ADR-0003)

- 打开方式必须只读(SQLite URI `file:...?mode=ro`)
- 永远不写、不改 schema、不加索引
- schema 若变(上游演进):engine 的 schema 依赖测试先红,修复窗口 = 当天日报,站点不受影响
