# AGENTS.md — nanmu-blog

极简静态博客(Astro 5)+ AI 引擎(Python,读 topic-digest 数据产日报)+ RAG(自用问答)。
当前阶段:M0 博客上线。完整设计与八条铁律见 `docs/superpowers/specs/2026-10-02-nanmu-blog-design.md`(§2 必读)。

## 结构
- `site/` — Astro 5 站点(手写文章 posts + AI 日报 digest)
- `engine/` — AI 引擎(M1,未创建)
- `docs/` — specs/plans/decisions/engine/ops/sessions 文档系统(索引见 `docs/README.md`)
- `deploy/` — 服务器部署工件(hook 与构建脚本,随 M0 Task 8 落盘)

## 常用命令(在 site/ 下)
- `npm run dev` 本地开发
- `npm run build` 构建
- `npm run verify` build + 冒烟检查(commit 前必须绿)

## 部署
push 到 main → 服务器 post-receive 后台构建原子发布。Runbook:`docs/ops/deploy.md`。
回滚 = 切 `/var/www/nanmu-blog/current` symlink 到旧 release(详见 `docs/ops/runbook.md`)。

## 会话交接
每个开发会话结束在 `docs/sessions/` 写交接记录,格式见 spec §8.1
(objective/state/disposition/next_action/omissions,声明分级 verified|declared)。

## 纪律
- 设计变更先改 spec/ADR 再改代码
- 服务器凭据不落盘(密码只在交互输入)
- 文档过期宁可删除,不留误导
