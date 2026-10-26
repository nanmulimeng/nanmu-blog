# 2026-10-26 ingest 多源集成与首期全链排障交接

> 承接 [2026-10-26 首期四轮调查](2026-10-26-first-issue-investigation.md)。本日主线:ADR-0012 落地(多 feed 直连)→ 首期全链打通(六轮排障)。origin 间歇断连,截至本文 **4 提交未推 origin**(server 均已部署)。

## 一、多源调研与集成(已完成)

**调研方法**:web_search 双语检索 → 候选逐个实测(先探测脚本后 engine 真实 `_parse_feed`)→ **服务器实测可达性**(本机网络≠服务器网络,TLDR/VentureBeat 本机超时但服务器是 404/429,结论以服务器为准)。

**最终 5 源**(全部服务器实测 [已验证],tier 真相源=sources.yaml):

| 源 | tier | 实测 |
|---|---|---|
| AIHOT | T1 | 50 条/日更 desc 179-295 |
| Techmeme | T2 | 15 条 desc 324-515 |
| MarkTechPost | T2 | 10 条 desc 281-510 |
| Hacker News (≥100分) | T2 | desc 134-571,短条目预筛自然过滤 |
| MIT Tech Review AI | T2 | 10 条 desc 352-405 |

**淘汰**:OpenAI Blog(全量历史 1318 条+正文<200 全灭)、TLDR(404)、VentureBeat(429 反爬)、The Verge(Atom+非 AI 专属)、机器之心(无 RSS)、TechCrunch AI/少数派/小众软件(RSS 摘要 <200 字预筛全灭——td 时代有全文管道故可用,直连不可)。

**实现**(engine 4/4→9/9 测试,全量 338/338):
- `ingest.py` FEEDS 多源清单;单 feed 失败隔离(告警跳过),**全部失败才 E2**;published 滑出 7 天不入库(防全量历史污染);`main()` hourly 入口(只落库不冻结)
- `run.py` NANMU_INGEST=1 双轨开关
- 服务器:nanmu-blog-ingest.{service,timer} 已部署 **enabled**,12:02 首次自动触发成功(判重+HN 超时隔离实弹验证)
- 运行时 config 同步点:`/opt/nanmu-blog/engine/config/`(sources.yaml/budget.yaml 双份维护,改仓库后必须同步)

## 二、首期六轮排障(逐轮真根因)

| 轮 | 现象 | 根因 | 修复 |
|---|---|---|---|
| 1 | KeyError content_hash | ingest manifest 成员缺 entry_id/content_hash(collect 契约) | ab1ad64 补齐 |
| 2 | cannot start transaction | freeze_issue 依赖调用方事务,ingest_once 未包裹→悬挂事务炸 ledger.authorize | 3279677 BEGIN IMMEDIATE/COMMIT 包裹(测试断言须**贴紧单次调用**,r2 的 commit 会吞掉 r1 悬挂——测试盲区教训) |
| 3 | 评分 5 条/轮停+zero_qualified | per_minute=10 打满→摘要阶段全 gate:window 拒→selected 无摘要被剔→落死 | 683086f per_minute 10→120 |
| 4-5 | 仍 10 笔停 | per_hour=100 被多轮重跑累计打满;评分与摘要**共享窗口池** | 等窗口滑开(跨小时) |
| 6 | 18 条 selected 摘要 0 成功 | ①评分挤占窗口 ②卡态 receipt(can_retry unknown_wait 30 分钟)——**其中 12 条是排障诊断脚本污染**(manual authorize 写 pending 未结算/无 key 脚本写 unknown) | 手术清理 12 行污染 receipt;score 卡态 2 条属产品自身 unknown 交 can_retry 自愈 |

**评分最终状态**:49/50 条 completed(¥0.064,远低于 ¥1/期),T1 过线 18 条已 selected+claim。

## 三、已知缺陷(未修,记录在案)

1. **环境性窗口拒落死期**:statuses 含 rejected(window)且 analysis_rows 非空时,understand 全拒→zero_qualified 落 failed——按 L250-252 语义应 return 4 续跑,但该检查仅在 analysis_rows 空分支。修复方向:understand 全 gate 拒时判环境性失败不落 dead-failed。
2. **评分与摘要共享窗口池**:大 to_score 批次会挤占摘要窗口(100/h)。修复方向:摘要窗口预留(类似 max_entries 预留)。
3. **score_loop 诊断日志**(50d4476)上线后可保留(observability)或收敛为 debug 级。

## 四、待办(优先级序)

1. **13:00 窗口滑开后收官轮**:删当日期 failed 行→start→预期:to_score=0(49 复用)+18 摘要+组装+发布。**这是 M1 首期落地时刻**。
2. 首期人工核验(draft 质量)→ 通过后 enable nanmu-blog-engine.timer(每日 08:30,M1 五步之⑤)
3. origin 补推(4 提交:ab1ad64/3279677/683086f/50d4476)
4. td 退役二次确认(用户)后执行:停 td timer/下线(数据未删)
5. workbench 写作验收(用户设口令)

## 五、操作备忘(服务器)

```bash
# 期复位(已验证流程)
sudo -u nanmu sqlite3 /opt/nanmu-blog/engine/engine.db \
  "DELETE FROM digest_issue WHERE issue_date='2026-10-26';"
sudo systemctl start nanmu-blog-engine.service
# 注意:issue_freeze 保留(续跑复用已评分数);删 digest_issue 即触发续跑
# 日志:sudo journalctl -u nanmu-blog-engine.service --since "…" --no-pager
# 关键事件:score_loop / score_loop_done / run_end
# **勿用 grep -v httpx 过滤 understand 调用痕迹**(本轮教训:真实 POST 被
# 过滤隐藏,误导排障两轮)
```
