# 经验教训对照表

> 两个前项目的真实踩坑 → 本项目的具体对策,以及对策落在哪份文档。新 agent 由此理解"为什么有这些规矩"。事实出处见 [project-background.md](project-background.md) 与 [server-environment.md](server-environment.md)。

## 来自 nanmuli-blog(本地开发,已废弃)

| 踩坑 | 本项目对策 | 落点 |
|------|-----------|------|
| 范围失控:从博客漂移成平台,12.5 周烂尾 | 里程碑独立可发布,不欠债进下一个;M3 想法只记录不动工 | 铁律 1;quality-gates L3 |
| "完成"被一轮轮审计劫持,永远没有可用版本 | 四级完成定义——不是更高标准,是明确标准 | quality-gates |
| 数据库 schema 四轨漂移(迁移档案/init/本地/服务器各一份,互不一致) | engine.db 的 DDL 单点在 db.py 带版本号;上游 schema 变更用依赖测试钉住 | coding-standards;强制测试 #6 |
| 密钥泄漏进 git 历史 | 密钥只走环境变量;L1 门禁检查 diff 无 secrets | coding-standards;quality-gates L1 |
| 文档过度宣称状态("MVP Beta 可试用"被自己的审计证伪) | verified/declared 声明分级,verified 必带证据 | sessions 模板;server-environment |
| 零外部反馈,质量判断失去锚点 | 每里程碑用真实可验证动作验收(curl/计时/RSS 订阅),先上线再迭代 | spec §9;M0 Task 10 |
| 带着未提交工作死去(601 行修复悬置) | 小步提交;M0 后会话结束 `git push server main`(服务器 bare repo 即异地副本) | workflow 会话结束 |

## 来自 topic-digest(线上运行,在产)

| 踩坑 | 本项目对策 | 落点 |
|------|-----------|------|
| `git remote add server` 直连 push **从未走通,原因未诊断**,最终退化成 bundle 手工同步 | M0 Task 9 内置 SSH 免密诊断清单;30 分钟仍不通则明确降级 bundle 并记录 omissions | M0 plan Task 9 Step 2 |
| systemd 239 的 OnCalendar 不认时区后缀(定时逻辑错) | timer 一律写裸本地时间;写入环境事实防重踩 | server-environment;pipeline 调度 |
| 服务器 sqlite 3.26 无 VACUUM INTO,备份 API 差点用错 | 备份用 `conn.backup()` Online Backup(3.26 就有),不依赖新 API | spec §7 |
| 页面滞后数据流 ~13h(build 未并入 hourly,无自动发布) | 发布即构建:push 触发构建,零人工环节 | ADR-0007 |
| 9 月整月观测真空(在跑但没人看) | 巡检表(日/周/月三级)+ 会话交接必写 disposition | ops/runbook;spec §8.1 |
| 源清单四处漂移(seed 15 / 服务器 15 / about 页 12 / 本地库 12) | "服务器是事实"原则;未核实处标 [declared] | data-source 文档 |
| OnFailure 通知未武装(env 文件缺失),欠了两个月 | M1 部署时与 engine 通知一并配好;已知欠账显式记录不重蹈 | runbook 通知节 |
| 两个死源每天空报警,污染注意力 | engine 预筛排除死源;告警有阈值不做噪音 | engine/selection;pipeline 失败隔离 |
| 代码同步靠手工 bundle 传输(deploy15.py/deploy16.py 临时脚本) | 部署工件(deploy/)进仓库,runbook 逐字可执行,不写一次性脚本 | M0 plan Task 8 |

## 通用教训(agent 开发)

| 教训 | 对策 | 落点 |
|------|------|------|
| 跨会话断层是最大隐形杀手(两个项目都吃过) | 交接纪律 + live_state 核对 | spec §8.1;ADR-0008 |
| 计划与现实冲突时"顺手绕过"会积累漂移 | 停下改计划再继续;计划外改动显式标注 | workflow 任务执行 |
| 单点外部依赖(API/DNS/LLM)静默失败 | 回执+降级+验收证据化;每个部署单点写明 Fallback | ADR-0005/0006;plan Task 9 |
| 一次性修复脚本散落临时目录,不可复现 | 一切部署动作进仓库(deploy/)与 runbook | plan Task 8 |
