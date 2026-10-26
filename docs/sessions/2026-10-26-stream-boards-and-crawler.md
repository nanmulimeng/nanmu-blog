# 会话交接:aihot 板块集成 + 爬虫模块移植(2026-10-26)

## 本轮交付

1. **板块集成(ADR-0014)**:精选 /featured/、全部动态 /all/、热点榜 /hot/ 三板块页上线(日报已有,凑齐 aihot 前四板块)。引擎每日 run 产出 `site/src/content/stream/<kind>-<date>.md`,与日报同一 commit 发布。
2. **爬虫模块移植(采集侧基础)**:AIHOT(KKKKhazix/AIHOT,MIT)sources/ 的 Python 移植——`crawl.py` 三种免费读取器 + 过滤器 + 配置白名单;`source_state` 表(db v2);sources.yaml kind/config 字段。**调度未接线**(见待办)。
3. **存量修复**:test_ledger 4 例因 budget.yaml 运维调值(120/200)断言破损,改为锚定固定限值。

## 关键文件

- engine:`src/nanmu_engine/stream.py`(板块产物+聚簇+回填 CLI)、`run.py`(write_draft 后写 stream)、`publish.py`(期文件集提交/隔离白名单/stream-only 补提交)、`crawl.py`(读取器)、`db.py`(v2 source_state)、`config.py`(kind 字段)
- site:`content.config.ts`(stream collection,strict schema)、`components/StreamList.astro`/`DgCard.astro`(通用卡片,评分徽标 label 可换)、`pages/{featured,all,hot}/index.astro`、`Header.astro`(导航+精选/动态/热点)
- docs:`decisions/0014-aihot-boards-integration.md`

## 验证记录(全绿)

- engine:stream 7/7、publish 34/34、ledger 60/60、crawl 11/11、config 24/24、db 8/8;全量终跑见会话记录
- site:build 9 页;npm test 3/3;三板块页卡片数正确(featured 4/all 5/hot 2 夹具);overflowX=0;zai 目检两页通过(时间轴贯穿/卡片要素/热度徽标语义)
- 空集合兜底:无数据时页面显示提示文案;`src/content/stream/.gitkeep` 保 glob base

## 部署清单(服务器)

1. engine pull + `pip install beautifulsoup4`(pyproject 新依赖)
2. 首期回填:`python -m nanmu_engine.stream --root /opt/nanmu-blog --date 2026-10-26 --emit-dir <site-work>/site/src/content/stream`(经 site-work git add/commit/push,published 期不走 publish_issue)
3. 每日起 run 自动产出后续日期(无需人工)

## 待办(下轮)

- **ingest 调度接线**:crawl.py 读取器就绪但 ingest_entries 仍走 FEEDS 五源;due 调度/失败退避/首导回填/自适应频率(collect.ts 语义,source_state 表已建)待接——用户个性化信源清单时一并做
- aihot 六信源中 x_search/mp_account/external 未落地(付费/常驻服务端)
- 已知缺陷 3 项(窗口拒落死期/摘要窗口预留/budget 表同步,见上期交接)仍挂账
- 首页挂三板块入口(当前仅导航);板块 RSS 未做

## 教训

- Git Bash 双引号/heredoc 链吃反斜杠(`\\n`→换行),三次踩坑——写文件一律用 Write/Edit 工具,不走 shell 拼内容
- Astro 5 collection 是白名单制(content.config.ts 显式定义),不是 folder 自动发现——新集合必须注册,glob 空集合有兜底警告无碍
- publish 身份链比对**索引 blob** 而非磁盘字节(autocrlf 下 CRLF/LF 恒不等),stream 待提交判定同法
