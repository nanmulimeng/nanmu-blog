# ADR-0002: 博客本体 = Astro 5 静态站,git 即 CMS,零客户端 JS

- 状态:已接受
- 日期:2026-10-02
- 关联:spec §4 / §4.1

## 背景

博客本体要求"简单版本"(用户明确);写作流为 git;同机已有 Astro 构建经验(topic-digest 实测 build 峰值 241MB,1.8G 内存机器无压力)。

## 决策

- Astro 5 Content Layer 双 collection:`posts`(手写,`title/pubDate/tags/draft`)+ `digest`(生成,`date/generated/ai_model/entry_count/cost_cny`),独立目录独立 schema,**schema 即契约**——非法 frontmatter 构建即失败
- 零客户端 JS:明暗主题纯 CSS `prefers-color-scheme`
- 无管理后台,无数据库;git 即 CMS
- 生成内容由 worker 落盘 + git 提交触发构建,绝不在 build 内调 LLM

## 理由

- 静态 = "页面永不调模型"(铁律 6)的物理保证
- Astro 5 glob loader 的 `base` 可指向任意目录,手写/生成内容天然隔离
- 构建即校验:digest 契约违约会在部署前失败,天然闸门
- 与 topic-digest 同技术栈,运维心智统一

## 后果(代价)

- 改内容必须走 git(单人项目可接受)
- 无评论/站内搜索等动态功能(M2 RAG 自用问答部分补足)

## 被否决的替代方案

1. Vue 3 + 管理后台 + 数据库——nanmuli-blog 老路,否决
2. WordPress——运维重,与 AI 管线集成别扭,否决
3. Hugo——可行,但 Astro 与 topic-digest 技术栈统一且组件模型更合适
