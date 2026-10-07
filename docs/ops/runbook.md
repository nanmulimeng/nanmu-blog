# 运维 runbook(目标流程,上线后使用)

> 当前应用已按Task9开通(2026-10-04,线上 `https://nanmu.xyz`),以下是运维基线。[部署手册](deploy.md)已实际执行一轮(开通+韧性实测+计时13s,证据见[sessions/2026-10-04-m0-deploy.md](../sessions/2026-10-04-m0-deploy.md));Task10首篇文章与m0发布待做。环境事实见context/server-environment.md,每次执行先核对现场与目标。

## 巡检

| 频率 | 动作 | 正常标准 |
|------|------|----------|
| 每日 | M0:首页、rss.xml、digest.xml、release.txt;M1:期状态;M2:索引版本/问答健康 | HTTP成功,线上SHA符合预期;日报发布回执与索引状态按已启用阶段核查 |
| 每周 | M0:构建日志;M1:engine journal、失败期/unknown回执、备份 | 无未处理失败/超时,已启用备份连续;不只grep error判断成功 |
| 每月 | M1起:结算/未决费用与供应商账单核对,抽查备份恢复 | ¥40预警已处理,月¥50上限有效;备份确实可读 |

## 回滚

先暂停新push并确认后台构建已结束。列出完整release并核对目标SHA,取得同一`/var/www/nanmu-blog/build.lock`后检查目标`.complete`,用临时软链+`mv -T`切换。具体命令见部署手册§7,不要把占位SHA原样执行。

验证首页、RSS、release.txt与目标版本。恢复最新版本走同样路径。内容错误优先`git revert`后正常push,不要让bare repo main与线上长期分叉;M1还需重新核对digest_issue发布状态。

## 故障处理

| 症状 | 定位 | 处理 |
|------|------|------|
| 站点不可达 | DNS/TLS、Caddy状态/日志、current目标与读权限 | 按证据修复;配置变更先备份+validate再reload,保护现有服务 |
| push成功但未更新 | 对比远端main、release.txt与部署日志 | push只代表接收;按部署手册§8带锁重跑,原样push可能无更新不触发hook |
| 日报未出 | engine journal、digest_issue、receipt_attempt | 区分生成失败/预算停止/提交冲突/已提交未发布;复用产物,不重复付费 |
| 成本异常 | 查看实际+未决预占、请求/价目版本与供应商用量 | budget调0立即禁止新调用,unknown费用不得当零处理 |
| 上游读失败 | 实际路径/WAL shm 权限/schema | 只修本项目读取方式,不改上游数据与服务。现行机制=mode=ro 直读(`connect_readonly`;2026-10-07 审计撤回拷主库+quick_check 方案——复制中途 checkpoint 可得旧新混合行且 quick_check 仍 ok,WAL 内已提交数据也会被漏,不构成一致性保证)。readonly 报错=nanmu 无上游 data/ 的 -shm/-wal 创建写权,E2 中止并在日志报最小权限缺口(须上游授权或暴露一致快照,人工裁决);不得退回文件拷贝或 immutable 直读 |
| 内存不足 | free、journal、构建与RAG实测峰值 | 保持旧站,停止失败增强任务;RAG MemoryMax=200M只是限制,不是性能保证 |

M0部署完成后的带锁手动重跑使用[部署手册](deploy.md)§8,再按§6核对线上SHA与实际页面。此处不另存一份命令,避免路径、日志或超时参数漂移。

## 通知与备份

- M0为hook后台任务,没有build.service/OnFailure自动通知;由日志与发布者的有界SHA确认发现失败。
- M1配本项目engine service的OnFailure与`/etc/nanmu-blog.env`;失败退出非零,通知脚本对连续2期失败去重,配置错误/崩溃立即通知,部署时实发一次测试通知。正常预算预警直接调用通知逻辑。
- 不改topic-digest的env、通知或备份。其历史欠账在环境文档保留。
- engine.db用Online Backup,保留30天并在副本上做完整性/恢复测试。rag.db从已发布Markdown重建,不要把索引当唯一内容来源。
- 服务器bare repo只是代码副本,同机SQLite备份不覆盖整机丢失;异地数据库备份仍未落实,不得在验收记录中称“备份全部完成”。

恢复旧engine.db前先停止新付费和发布,保留现库用于核对。恢复副本通过完整性检查后,对照备份之后的供应商用量、远端Git和线上SHA补齐账本/期状态,再恢复调度;未知费用继续预占。不能把旧库里缺失的调用当作没有发生,否则可能重复扣费。具体命令及备份时间点演练在M1计划落盘,M0不提前操作数据库。

## M1 engine 运维命令(Task 25 安装;root=/opt/nanmu-blog/engine)

以下命令经 engine venv 执行(`/opt/nanmu-blog/engine/.venv/bin/python`);所有改变状态的操作(恢复/暂停解除)是人工决策,先核对再执行。

| 操作 | 命令 |
|------|------|
| 期状态总览 | `cd /opt/nanmu-blog/engine && .venv/bin/python -c "from nanmu_engine.db import connect_db; from nanmu_engine.ops import status; from pprint import pprint; pprint(status(connect_db('engine.db')))"` |
| 单期事实 | 同上,`status(connect_db('engine.db'), '2026-10-07')` |
| 暂停一期 | `… -c "from nanmu_engine.db import connect_db; from nanmu_engine.ops import pause_issue; pause_issue(connect_db('engine.db'), '2026-10-07', reason='人工核对')"` |
| 解除暂停 | 同上换 `unpause_issue(connect_db('engine.db'), '2026-10-07')` |
| 每日备份 | `NANMU_ENGINE_ROOT=/opt/nanmu-blog/engine /opt/nanmu-blog/engine-src/deploy/engine-backup.sh`(Online Backup,保留 30 天,产物 `/opt/nanmu-blog/backups/engine.db.<时间戳>`) |
| 恢复备份 | 先停 engine(无 timer 运行时即无并发)再执行:`flock /opt/nanmu-blog/engine/run.lock … -c "from nanmu_engine.ops import restore_backup; restore_backup('/opt/nanmu-blog/backups/engine.db.<时间戳>', '/opt/nanmu-blog/engine/engine.db')"`——五步序列(副本置 pay_paused→读回校验→原子切换),调用方须持与常规运行相同的单实例锁;**恢复后闸门拒新增付费,人工核对备份点之后的供应商用量与账单再显式解除** |
| 解除付费暂停 | `… -c "import sqlite3; c=sqlite3.connect('/opt/nanmu-blog/engine/engine.db'); c.execute(\"INSERT INTO engine_meta (key,value,updated_utc) VALUES ('pay_paused','0',datetime('now')) ON CONFLICT(key) DO UPDATE SET value='0'\"); c.commit()"`——仅在完成上述核对后 |
| 校准状态 | `… -c "from nanmu_engine.db import connect_db; from nanmu_engine.config import load_config; from nanmu_engine.ledger import calibration_effective; from nanmu_engine.ops import status; c=connect_db('engine.db'); print(calibration_effective(c, load_config('/opt/nanmu-blog/engine')))"` |

- 手动触发一次运行(替代 timer;需在 `/etc/nanmu-blog.env` 有真实 key 才会付费,当前空 key=闸门拒绝新增):`sudo systemctl start nanmu-blog-engine.service`——**timer 保持 disabled 直到 Task 26 Step 5**。
- 失败告警:service `OnFailure=nanmu-blog-engine-fail.service`(journal tag `nanmu-blog-engine`;webhook 配置见 `/etc/nanmu-blog.env` 的 `NANMU_NOTIFY_WEBHOOK`,空=仅 journal)。
- 日志:`journalctl -u nanmu-blog-engine.service`;结构化行 `stage=… event=…` 与 design.md 日志观测节对应。
