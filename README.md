# nanmu-blog

个人博客:手写文章 + AI 日报 + 自用 RAG。博客先上线,AI 按里程碑叠加,已发布博客不依赖 AI 运行。

## 当前状态(2026-10-04)

M0:Task1-9已完成——site/(Astro5.18.2)、部署工件与服务器链路均已验收,**线上 `https://nanmu.xyz`**(常态发布计时13s,韧性实测5项通过)。Task10(首篇文章+tag m0)未做。**当前阶段(2026-10-05 第五轮核验):M1 详细设计与实施计划评审通过**(五单元+27 任务 plan,待 M0 收尾及用户明确恢复实施,实施类操作仍暂停);tokenizer/费用上界/备份恢复/真实发布属实施验证未运行。skills.nanmu.xyz DNS 记录消失待用户在DNS控制台恢复。engine/ 已建立(digest-design v3 + design/pipeline/budget + units/ 五单元,评审通过版)。

背景审查依据见[审查记录](docs/reviews/2026-10-02-documentation-audit.md);最新执行证据见[最新交接](docs/sessions/2026-10-05-m1-plan-review5-passed.md)(第五轮核验:M1 实施计划通过评审,4 组 P1 关闭+三处引用勘误落盘;后续顺序=获准恢复→M0 Task 10→M1 Task 0 起本地实现)。开发策略统一在[spec §9](docs/superpowers/specs/2026-10-02-nanmu-blog-design.md):M0独立上线验收→M1独立日报与成本治理→M2自用检索问答,M3仅记录候选。

## 开发与部署

本地:`cd site && npm install && npm run dev` 开发;`npm run verify`(build + 冒烟)自 Task 7 起是提交门槛。服务器自动发布链路已在 Task 9 验收(push→线上13s);首篇文章走完整链路在 Task 10(挂起中)。

写作流:Markdown → git push main → 后台构建与冒烟 → 原子静态发布(已验收)。当前文档阶段不执行发布类操作。

## 从哪里读

- [AGENTS.md](AGENTS.md):边界、工作流与阅读顺序。
- [项目背景](docs/context/project-background.md):旧博客教训、topic-digest 数据基础、外部借鉴。
- [文档索引](docs/README.md):设计、计划、证据各自的责任位置。

## 已可用的文档工作流

仓库根运行`python scripts/check_docs.py`检查链接、代码围栏、schema示例一致性和SQL语法;不安装应用依赖、不访问网络。修改计划中的代码片段时再按文档索引运行`--snippets`。

写作方式见[写作指南](docs/writing.md),部署操作见[部署手册](docs/ops/deploy.md)(手册已实际执行一轮,Task10 复测待做)。
