# nanmu-blog

个人博客:手写文章 + AI 日报 + 自用 RAG。博客先上线,AI 按里程碑叠加,已发布博客不依赖 AI 运行。

## 当前状态(2026-10-04)

设计基线与文档系统已建立,M0 Task 1 完成。当前仓库包含文档、基础配置与文档检查脚本,尚无 `site/`、`engine/`、`deploy/`。下一步按 [M0 计划](docs/superpowers/plans/2026-10-02-m0-blog-launch.md)执行 Task 2。

背景与契约审查依据见[审查记录](docs/reviews/2026-10-02-documentation-audit.md);4 轮文档修订的审查核验结论与小修见[最新交接](docs/sessions/2026-10-04-audit-fixes.md)。

## 开发与部署(待 M0 实现)

Task 2 创建 site 后才可运行 `cd site && npm install && npm run dev`。Task 7 建立 `npm run verify`。部署手册准备版已建立;Task8创建部署工件并核对手册,Task9验证server remote与自动发布。

目标写作流为 Markdown → git push main → 后台构建与冒烟 → 原子静态发布。现在不能把这些命令当作已可用能力。

## 从哪里读

- [AGENTS.md](AGENTS.md):边界、工作流与阅读顺序。
- [项目背景](docs/context/project-background.md):旧博客教训、topic-digest 数据基础、外部借鉴。
- [文档索引](docs/README.md):设计、计划、证据各自的责任位置。

## 已可用的文档工作流

仓库根运行`python scripts/check_docs.py`检查链接、代码围栏、schema示例一致性和SQL语法;不安装应用依赖、不访问网络。修改计划中的代码片段时再按文档索引运行`--snippets`。

写作方式见[写作指南](docs/writing.md),部署准备见[部署手册](docs/ops/deploy.md)。两份指南均标明阶段前提,尚未完成线上验收。
