# 2026-10-26 首期日报四轮调查收口:engine 全链正确,阻塞在上游抓取停摆

## 四轮失败与根因(每轮一个真问题)

| 轮 | 结果 | 根因 | 处置 |
|---|---|---|---|
| 1(09:01) | zero_qualified,10 次评分调用 | **sources.yaml 漏配**:selection.md tier 表 T1 应四源,实现只配 OpenAI/DeepMind(恰为上游正文稀缺源 123 条仅 1 正文);量子位(424 条/419 正文)缺位 | 已修(80e4558:补量子位/阮一峰/36氪) |
| 2(09:09) | E2.upstream 活库只读 | **服务器 env 是方案 A 定案前旧形态**(NANMU_UPSTREAM_DB 未注释、SNAPSHOT_DIR 缺)——方案 A 落地时漏更新部署 env | 已修(服务器 env:SNAPSHOT_DIR 启用,DB 注释) |
| 3(09:11) | zero_qualified,又 10 次评分 | manifest 106 条 = HN 87+TechCrunch 6+小众 4+Verge 4+AIHOT 3+少数派 2,**T1 四源 0 条** | 见第 4 行根因 |
| 4(根因定案) | — | **上游 td 抓取停摆**:最新备份里量子位/阮一峰/OpenAI Blog 的 max(fetched_utc) 停在 2026-10-23(HN 正常至 10-25 19:00)→ 48h 窗口(锚定 fetched,设计如此)把 T1 整批切出;HN 残余内容评分 5-52 全低于门槛(T2=75)——**编辑门槛如实拦下弱内容,正确行为** | 上游侧问题(td 是用户自管系统),engine「未获授权不修改上游」 |

## engine 侧验证结论(全部正确)

- 快照证据链(resolve→防线→年龄)✓;窗口/判重/预筛排除 ✓;评分链(15→25 笔 receipt)✓;门槛按 tier ✓;预算/速率 ✓(单期 ¥1 内,总成本 **¥0.031**);失败期不影响公开站 ✓;failed 不自动重跑 ✓(人工复位两次均留痕 engine_meta.manual_reset_20261026)。
- 人工复位方式沉淀:digest_issue 有 `CHECK(status='failed' OR markdown_path NOT NULL)`,failed→draft 不可直改,**删期行+freeze 行**让 run 全新处理(entry/评分回执复用,零重复付费)。

## 当前状态与阻塞

- 线上公开站不受影响;engine.db:2026-10-26 期 failed(zero_qualified);receipts 25 笔 ¥0.031。
- **M1「首期→连续 3 天」验收被上游抓取阻塞**:除非 td 恢复抓 T1 源(量子位/阮一峰/OpenAI Blog 自 10-23 停),每日将大概率继续 zero_qualified。
- 处置选项(用户决策):①修 td 抓取(feed 失败类似机器之心先例);②sources.yaml 换入上游仍在抓的高正文源(TechCrunch AI 513/550 正文,T2 提门槛 75 可入);③两者并行。

## Git

80e4558(源配置修复)已推双远端;session 本提交。
