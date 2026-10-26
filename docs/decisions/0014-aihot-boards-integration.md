# ADR-0014: aihot 前四板块集成——精选/全部动态/热点榜/日报

- 状态:已接受(2026-10-26 用户指令「只做前四个就可以,将这些集成到本项目中」)
- 日期:2026-10-26
- 关联:[ADR-0012](0012-upstream-aihot-direct.md)(数据源)/[ADR-0013](0013-digest-card-rendering.md)(卡片流)/上游 KKKKhazix/AIHOT(爬虫模块移植参考)

## 背景

用户对齐产品方向:以 aihot.news 导航的前四板块(精选、全部 AI 动态、热点榜、AI 日报)为目标形态集成进本项目。日报已有;缺三个板块页与持续供给的内容形态。同时按用户最初指令,把 AIHOT 开源仓库(KKKKhazix/AIHOT,MIT)的爬虫模块(sources/)以 Python/SQLite 移植进 engine 作为采集侧基础(用户后续个性化调整)。

## 决策

1. **板块页=每日 run 的衍生产物,零额外 LLM 成本**:`stream.py` 从当日 manifest+analysis+summary 同一数据源构建三份 markdown(精选=过线条目按门槛三组;全部动态=已评分条目全量含未过线;热点榜=跨源聚簇事件),frontmatter `kind/date/generated/count`。
2. **产物与 digest 同构**:`## 板块/### 标题/- 摘要/- 理由 [来源](url)(src·展示分 N)`,渲染层复用 `digest-card.mjs` 解析器与 ADR-0013 的 dg-* 卡片流体系;`DgCard.astro` 抽为通用组件(评分徽标 label 可换——热点榜显示「热度」而非「AI 评分」)。
3. **发布通道复用**:run.py 在 `write_draft` 后写 `site/src/content/stream/<kind>-<date>.md`,`publish._commit_digest` 将其并入同一原子提交;隔离核对白名单从 digest 单文件扩为「期文件集」;digest 已提交而 stream 后到时补一笔 `stream: <date>` 提交。
4. **热点榜=纯规则聚簇**:标题 token(英文词+中文 bigram)Jaccard ≥ 0.35 贪心合并,热度 `min(独立来源数,5)*12 + 代表分//2`(AIHOT「按事件算、独立来源只算一次」的轻量版);≥2 独立来源才上榜。无向量服务依赖。
5. **爬虫模块移植(采集侧基础)**:`crawl.py` 移植 AIHOT sources/ 的三种免费读取器(rss 含 Atom+ETag/304、web_list CSS 选择器+detail 补齐、json_list 字段路径映射)+ filters(前缀/改写/噪声/publishedAfter)+ 配置键白名单(未知键=源失败);调度状态表 `source_state`(db v2:user_version 1→2);sources.yaml 每源可选 `kind/config/interval_minutes/enabled`。x_search/mp_account/external 未落地(付费 key/常驻服务端),留扩展位。**ingest 调度接线(due/退避/首导回填/自适应频率)本轮未做**,FEEDS 五源路径保持,启用调度待个性化时接。
6. **回填**:首期(2026-10-26)用 `python -m nanmu_engine.stream --root ... --date ... --emit-dir ...` 从 DB 重放产出,经 site-work 手动 git 提交(published 期 publish_issue 早退,不走自动链)。

## 后果与边界

- **更新节奏=每日一次**(随日报 run+发布)。静态站无小时级重建;要更快需加构建触发机制(未做)。
- stream 文件**无库内账本身份**(不进 digest_issue 契约),以「可重放覆盖」为一致性手段:重跑 CLI 重写文件,git diff 为准。
- 板块自首个启用日起累积,更早日期无数据(首期已回填)。
- 热点榜为标题相似度聚簇(非向量、无语义判别),中文标题优先参与相似度;误并/漏并随阈值 0.35 调整,标注于代码常量。
- 全部动态含未过线条目(评分徽标可辨);无摘要条目卡片仅标题+原始摘要截断。
- Astro collection 白名单:`content.config.ts` 显式注册 `stream`(strict schema:kind ∈ featured/all/hot)。
- 修复:test_ledger 4 例锚定限值(10/100/400)不再随 budget.yaml 运维值漂移(2026-10-26 budget.yaml 已调 120/200,测试断言存量破损,本轮一并修复)。
