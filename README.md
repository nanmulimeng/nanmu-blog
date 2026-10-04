# nanmu-blog

个人博客:手写文章 + AI 日报 + 自用 RAG。博客先上线,AI 按里程碑叠加,已发布博客不依赖 AI 运行。

## 当前状态(2026-10-04)

M0 进行中:site/ 已建(Astro 5.18.2,Task 2-8 完成,`npm run verify` 全绿),deploy/ 工件已落盘;engine/ 留 M1。下一步 M0 [Task 9](docs/superpowers/plans/2026-10-02-m0-blog-launch.md)(服务器开通,需用户配合)与 Task 10(首篇文章上线)。

背景与契约审查依据见[审查记录](docs/reviews/2026-10-02-documentation-audit.md);引擎实施契约(engine/design.md)与 M0 执行进度见[最新交接](docs/sessions/2026-10-04-m0-task2-8.md)。

## 开发与部署

本地:`cd site && npm install && npm run dev` 开发;`npm run verify`(build + 冒烟)自 Task 7 起是提交门槛。部署工件已落盘(Task 8);服务器安装与自动发布在 Task 9 验证,首篇文章走完整链路在 Task 10。

目标写作流为 Markdown → git push main → 后台构建与冒烟 → 原子静态发布。服务器侧链路未验收前,不能把线上发布当作已可用能力。

## 从哪里读

- [AGENTS.md](AGENTS.md):边界、工作流与阅读顺序。
- [项目背景](docs/context/project-background.md):旧博客教训、topic-digest 数据基础、外部借鉴。
- [文档索引](docs/README.md):设计、计划、证据各自的责任位置。

## 已可用的文档工作流

仓库根运行`python scripts/check_docs.py`检查链接、代码围栏、schema示例一致性和SQL语法;不安装应用依赖、不访问网络。修改计划中的代码片段时再按文档索引运行`--snippets`。

写作方式见[写作指南](docs/writing.md),部署准备见[部署手册](docs/ops/deploy.md)。两份指南均标明阶段前提,尚未完成线上验收。
