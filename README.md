# nanmu-blog

个人博客:手写文章 + AI 日报 + 自用 RAG。博客先上线,AI 按里程碑叠加,已发布博客不依赖 AI 运行。

## 当前状态(2026-10-04)

M0进行中:site/(Astro5.18.2)与deploy/工件已落盘,Task1-8原范围已完成。下一步先做[M0 Task8a](docs/superpowers/plans/2026-10-02-m0-blog-launch.md)的原始内容路径/slug与缓存边界修复,再做Task9服务器开通与Task10首篇上线。已有build/verify通过记录不覆盖这两项新增边界;engine/尚未创建。

背景审查依据见[审查记录](docs/reviews/2026-10-02-documentation-audit.md);本轮技术契约修订、待实现项和验证见[最新交接](docs/sessions/2026-10-04-technical-direction.md)。开发策略统一在[spec §9](docs/superpowers/specs/2026-10-02-nanmu-blog-design.md):M0独立上线验收→M1独立日报与成本治理→M2自用检索问答,M3仅记录候选。

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
