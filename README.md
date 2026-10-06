# nanmu-blog

个人博客:手写文章 + AI 日报 + 自用 RAG。博客先上线,AI 按里程碑叠加,已发布博客不依赖 AI 运行。

## 当前状态(2026-10-06)

**M0 全部完成并验收通过(2026-10-06,tag `m0`)**——首篇文章《你好,nanmu-blog》已在 **`https://nanmu.xyz`** 真实发布(发布计时12s;RSS 解析+CommaFeed 真实订阅、明暗主题、文章页/404、持锁回滚演练全部通过)。**当前阶段:M1 本地实施(Task 0-12 批量,已授权)**——替身模型、真实上游只读、不部署不付费;之后 Task 13-24 本地替身端到端,Task 25/26 部署与付费另行授权。skills.nanmu.xyz DNS 记录消失待用户在DNS控制台恢复。engine/ 设计文档(digest-design v3 + design/pipeline/budget + units/ 五单元)评审通过,为实施基线。

最新执行证据见[最新交接](docs/sessions/2026-10-06-m0-acceptance.md)(M0 验收全记录);M1 批次规范与给执行 AI 的指令原文见 [resume-implementation](docs/sessions/2026-10-06-resume-implementation.md)。开发策略统一在[spec §9](docs/superpowers/specs/2026-10-02-nanmu-blog-design.md):M0独立上线验收(已达成)→M1独立日报与成本治理→M2自用检索问答,M3仅记录候选。

## 开发与部署

本地:`cd site && npm install && npm run dev` 开发;`npm run verify`(build + 冒烟)自 Task 7 起是提交门槛。服务器自动发布链路已在 Task 9 验收;首篇文章走完整链路发布+回滚演练已在 Task 10 验收(tag `m0`)。

写作流:Markdown → git push main → 后台构建与冒烟 → 原子静态发布(已验收,首篇文章已真实走通)。发布类操作(push/tag)仍需授权。

## 从哪里读

- [AGENTS.md](AGENTS.md):边界、工作流与阅读顺序。
- [项目背景](docs/context/project-background.md):旧博客教训、topic-digest 数据基础、外部借鉴。
- [文档索引](docs/README.md):设计、计划、证据各自的责任位置。

## 已可用的文档工作流

仓库根运行`python scripts/check_docs.py`检查链接、代码围栏、schema示例一致性和SQL语法;不安装应用依赖、不访问网络。修改计划中的代码片段时再按文档索引运行`--snippets`。

写作方式见[写作指南](docs/writing.md),部署操作见[部署手册](docs/ops/deploy.md)(手册已实际执行一轮,Task10 复测待做)。
