# nanmu-blog

个人博客:手写文章 + AI 日报 + 自用 RAG。博客先上线,AI 按里程碑叠加,已发布博客不依赖 AI 运行。

## 当前状态(2026-10-06)

**M0 全部完成并验收通过(2026-10-06,tag `m0`)**——首篇文章《你好,nanmu-blog》已在 **`https://nanmu.xyz`** 真实发布(发布计时12s;RSS 解析+CommaFeed 真实订阅、明暗主题、文章页/404、持锁回滚演练全部通过)。**当前阶段:M1 部署对接完成,待真实校准授权(2026-10-07,315 测试)**——Task 25 已执行:引擎已部署服务器(timer 保持 disabled)、上游快照只读、零付费验证全通过;真实模型调用与 timer 启用归 Task 26,须当次授权。skills.nanmu.xyz DNS 记录消失待用户在DNS控制台恢复。engine/ 设计文档(digest-design v3 + design/pipeline/budget + units/ 五单元)评审通过,为实施基线。

接手从 [M1 审计修复轮交接](docs/sessions/2026-10-06-m1-audit-fix-round.md)开始(审计 8 项修复全记录与待办);前序实施记录见 [M1 批次实施](docs/sessions/2026-10-06-m1-batch1-implementation.md)与 [M1 开发交接](docs/sessions/2026-10-06-m1-development-handoff.md)。M0 执行证据见 [M0 验收交接](docs/sessions/2026-10-06-m0-acceptance.md)。阶段策略以 [spec §9](docs/superpowers/specs/2026-10-02-nanmu-blog-design.md)为准。

## 开发与部署

本地:`cd site && npm install && npm run dev` 开发;`npm run verify`(build + 冒烟)自 Task 7 起是提交门槛。服务器自动发布链路已在 Task 9 验收;首篇文章走完整链路发布+回滚演练已在 Task 10 验收(tag `m0`)。

写作流:Markdown → git push main → 后台构建与冒烟 → 原子静态发布(已验收,首篇文章已真实走通)。发布类操作(push/tag)仍需授权。

## 从哪里读

- 前端设计专项：[全站页面/动效/3D 任务书](docs/design/2026-10-07-visual-redesign/FULL-SITE-BRIEF.md)与[最新交接](docs/sessions/2026-10-08-frontend-creative-research.md)(2026-10-08，创意参考已补充，允许科技感与大胆美术探索；原型扩展待执行，不代表正式站改版完成)。**R4「纸筑」全站原型已交付（2026-10-08）**：入口 [r4/index.html](docs/design/2026-10-07-visual-redesign/prototypes/r4/index.html)，R3→R4 对照图与四项定点修复验证见 [batch4 交接](docs/sessions/2026-10-08-visual-redesign-batch4.md)；仍为原型，未接入正式站。**R5「字场 · 碑页」首页深化原型已交付（2026-10-08）**：入口 [r5/index.html](docs/design/2026-10-07-visual-redesign/prototypes/r5/index.html)，两案取舍与验证见 [R5 会话报告](docs/sessions/2026-10-08-r5-homepage-creative.md)；评审后完成集中修正（五组交界问题+夜间纸质感+落线衔接），见 [R5 修正轮报告](docs/sessions/2026-10-08-r5-fix-round.md)；仅首页，内页沿用 R4。

- [AGENTS.md](AGENTS.md):边界、工作流与阅读顺序。
- [项目背景](docs/context/project-background.md):旧博客教训、topic-digest 数据基础、外部借鉴。
- [文档索引](docs/README.md):设计、计划、证据各自的责任位置。

## 已可用的文档工作流

仓库根运行`python scripts/check_docs.py`检查链接、代码围栏、schema示例一致性和SQL语法;不安装应用依赖、不访问网络。修改计划中的代码片段时再按文档索引运行`--snippets`。

写作方式见[写作指南](docs/writing.md),部署操作见[部署手册](docs/ops/deploy.md)(Task9 部署与Task10 发布/回滚验收均已执行)。
