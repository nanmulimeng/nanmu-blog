# 上游数据源:topic-digest 实况

> engine(M1)只读它的 SQLite。本文固化:它是什么、跑得怎么样、schema 契约、信源清单、已知坑。schema 部分逐字来自其仓库 `schema.sql`(2026-10-02 实读核实)。

## 它是什么

多主题 RSS 聚合静态日报站(Python + SQLite + systemd timer + flock + Astro 静态发布),2026-08-31 上线,**无管理后台和后端Web框架,展示站使用Astro**。本地代码已有单条目cluster占位聚类,未见AI评分/摘要主流程;engine独立做AI加工,不写上游表。

仓库:`D:\software\item\topic-digest`;生产运行状态见 [server-environment.md](server-environment.md)。

## 运行节奏与数据量(上一会话转述,本轮未复测)

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

其余表:topic、cluster、cluster_member、pick、daily、api_usage——**engine 不依赖**。本地 `pipeline.py` 每轮调用 `ensure_single_clusters`,向cluster/cluster_member写入,把item从fresh改为clustered;不能称cluster为空表。pick/daily线上行数未复核。

engine 依赖字段清单(钉死并在测试中固化):

- `item`:id / source_id / url_hash / url / title / published_utc / fetched_utc / content_text / status
- `source`:id / name / weight / enabled

**判重独立**:topic-digest 的 `url_hash` 与 engine 的 identity_key 归一规则可能不同,engine 用自己的 AIHOT 式归一(spec §5.2)独立判重,不依赖 url_hash 语义。

## 信源清单(上一会话记录的服务器15源,线上状态待复核)

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

**注意漂移**:本地 dev 库与其 about 页面仍是 12 源旧口径;**以当次服务器核验为准**,不能把本地种子或旧页面当实时状态。

## 已知坑(engine 设计已考虑)

| 坑 | 对 engine 的影响 |
|----|------------------|
| 两个死源每天空报警 | 预筛排除,不进评分(省调用费) |
| DeepMind SSL / HN 超时间歇失败 | 只是入库波动,读取窗口放宽到 48h 兜底 |
| 二手源(AIHOT/速览/简报)与一手源内容重叠 | engine 的 identity_key URL 归一判重天然去重同 URL;跨源同事件不同 URL 的语义去重 M1 不做(YAGNI,M3 观察) |
| `content_text` 可能为空或仅含RSS摘要 | schema没有独立summary列。空文本默认预筛跳过自动事实摘要并记录原因;不声称可凭空回退到summary |
| 无通知、备份本地 | 与本项目无关(铁律 4:不动它),记录在 server-environment.md 欠账清单 |

## 只读契约(ADR-0003)

- 打开方式必须只读(SQLite URI `file:...?mode=ro`)
- 永远不写、不改 schema、不加索引
- schema 若变(上游演进):engine 的 schema 依赖测试先红,修复窗口 = 当天日报,站点不受影响

## 实施读取契约(2026-10-02本地源码核对)

证据:本地上游HEAD `f25d187`,`schema.sql`、`src/topic_digest/pipeline.py`、`cluster.py`、`extract.py`、`config.py`。线上是否一致仍待M1核查。

- JOIN 必须 `item.source_id = source.id`;选 `source.enabled=1`、`item.status IN ('fresh','clustered')`,排除dropped。不能只选fresh,正常采集条目通常已clustered。
- 增量窗口按 `fetched_utc` 近48h纳入新抓取数据,按published_utc展示;空/异常发布时间不能使新抓取条目永久丢失。恢复长时间停机的回补策略在M1 plan确定,不无限追历史。
- `content_text` 不保证全文:`best_content` 可回退RSS摘要。另一个本地路径中,长RSS摘要跳过抓页但没有写回content_text,所以空值不能简单归因于提取失败。这里只记录,不修上游。
- 默认路径来自 `config.DB_PATH`:仓库 `data/topic-digest.db`,可被 `TD_DB_PATH` 覆盖。旧部署目录推导出的 `/opt/topic-digest/data/topic-digest.db` 只是候选路径,必须读线上unit环境并以实际路径验证。
- 以engine实际运行用户验证 `mode=ro`,执行只读schema/状态/空值比例查询;确认DB与WAL/SHM访问权限。不给上游设置journal_mode、不创建索引、不用immutable访问活跃数据库。依据:[SQLite WAL只读条件](https://www.sqlite.org/wal.html#read_only_databases)。
- `source.name` 可为空,展示提供稳定回退;URL规范化不得把路径大小写强制统一,不盲删有业务语义的查询参数。M1测试须涵盖不同URL被误合并的反例。

## M1读取与快照补充

- 首次插入后仍需处理同identity_key的再读取:未发布条目正文由空变非空或内容变更时允许刷新快照,请求hash必须随内容变化,旧付费回执仍保留但不得冒充新内容的结果;已发布条目不自动重新评分/发布。
- 同一identity_key来自多个源时,不能依赖SQL返回顺序选择tier。M1计划须定义确定的来源优先级与平局规则,保留选择依据;判重合并不等于提高可信度。
- 正常窗口按fetched_utc近48h;超窗回补只允许显式指定有上限的时间范围,M1计划给出上限、候选预算与恢复命令,不在服务重启时无限追溯历史。
- 当前死源清单是排除初值,上线前检查实际状态;不修改上游源配置。
