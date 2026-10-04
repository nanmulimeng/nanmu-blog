# ADR-0003: engine 只读直连 topic-digest SQLite

- 状态:已接受;事实/数学依据见文末2026-10-02勘误,当前契约以spec为准
- 日期:2026-10-02
- 关联:spec §5.2 / 铁律 4

> 2026-10-04有效口径:当前有效读取契约见[上游数据源](../context/topic-digest-data-source.md):fresh/clustered、JOIN键与fetched_utc均需读取。下文空表论据/旧字段清单已失效;只读模式仍需验证WAL权限与资源影响,不承诺零风险。

## 背景

聚合数据已在同机 topic-digest 的 SQLite 里(9 月 720/720 小时级新鲜,月入库 3,491 条)。其 `cluster/pick/daily` 三表是预留空表(M1 从未动工)。

## 决策

engine 以**只读**方式直读 topic-digest SQLite 文件(`item JOIN source`,近 24-48h 窗口)。依赖字段清单钉死并在测试中固化:`item.url_hash/url/title/published_utc/content_text/status` + `source.name/weight/enabled`。不启用其空置的 cluster/pick/daily 表。

## 理由

- 同机文件只读 = 零网络、零额外服务、零破坏风险("topic-digest 保持现状不动"铁律 4)
- 集成成本最小:不需要对方做任何改动

## 后果(代价)

- 对 topic-digest schema 演进形成单向耦合:其改表可能破坏 collect。缓解:schema 依赖测试钉住;坏读取只影响当天日报,不波及站点
- 未来若跨服务器部署,两库必须同机(当前同机,可接受)

## 被否决的替代方案

1. topic-digest 暴露 HTTP API——要改"保持现状不动"的在产服务,否决
2. 定期复制数据到 engine 库——引入同步漂移与双份存储,否决

## 2026-10-02事实勘误

只读独立处理的决策不变。本地上游pipeline已使用cluster/cluster_member并将item状态改为clustered,上文“三表为空”的历史依据不成立。字段清单补JOIN键与fetched_utc,当前契约见context/topic-digest-data-source.md;线上表行数仍待核查。
