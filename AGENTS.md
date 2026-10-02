# AGENTS.md — nanmu-blog

**一句话**:极简静态博客(手写文章)+ AI 引擎自动日报(读 topic-digest 数据)+ 自用 RAG。博客先上线,AI 是渐进叠加层,**任何一层挂掉博客都在线**。

## 项目状态快照(2026-10-02)

- 设计阶段完成:spec + M0 计划 + 文档系统全部落盘
- 里程碑:M0(博客上线)待执行,Task 1 已完成;M1(引擎)/M2(RAG)计划各自启动时再写
- 执行方式:Native(executing-plans),按 [docs/superpowers/plans/2026-10-02-m0-blog-launch.md](docs/superpowers/plans/2026-10-02-m0-blog-launch.md) 逐任务
- 最新进度:看 [docs/sessions/](docs/sessions/) 最新一份交接记录

## 新进入项目?按这个顺序读

1. **本文**——铁律与导览(5 分钟)
2. [docs/context/project-background.md](docs/context/project-background.md)——三个前项目的完整故事:为什么这个项目长这样;[docs/context/lessons.md](docs/context/lessons.md)——踩坑→对策对照表(规矩的由来)
3. [docs/superpowers/specs/2026-10-02-nanmu-blog-design.md](docs/superpowers/specs/2026-10-02-nanmu-blog-design.md)——设计真相源
4. 当前里程碑的 plan(上述 M0 计划)
5. [docs/sessions/](docs/sessions/) 最新记录——现在做到哪
6. **动工前必读**:[docs/development/workflow.md](docs/development/workflow.md)(会话怎么干活)、[docs/development/coding-standards.md](docs/development/coding-standards.md)(代码怎么写,含 engine 目录结构与依赖白名单)、[docs/development/quality-gates.md](docs/development/quality-gates.md)(做到什么程度算完成)
7. 需要时:[docs/context/server-environment.md](docs/context/server-environment.md)(部署/排障)、[docs/context/topic-digest-data-source.md](docs/context/topic-digest-data-source.md)(M1 数据上游)、[docs/context/glossary.md](docs/context/glossary.md)(术语表)、[docs/README.md](docs/README.md)(全部文档索引)

## 八条铁律(全文;真相源 spec §2,修改先改 spec)

1. **范围是生死线**:每个里程碑必须独立可发布,不欠债进下一个(nanmuli-blog 12.5 周烂尾的头号教训)
2. **博客本体永远不为 AI 功能加复杂度**:AI 挂了博客照常在线
3. **AI 引擎独立进程独立数据库**:engine 崩溃不影响博客,反之亦然
4. **topic-digest 保持现状不动**:本项目只读它的 SQLite(同机文件只读,`mode=ro`)
5. **付费请求先记回执再消费 + 三级预算熔断**,LLM 月预算红线 **¥50**
6. **页面永不调模型**:读者打开页面只读预生成内容
7. **AI 生成内容必须标注**:digest 栏目注明 AI 生成、模型与成本,与个人文章视觉区分
8. **文档随代码走**:设计变更先改文档;会话结束写交接记录

## 项目结构

```
site/      Astro 5 静态站(posts 手写 + digest 生成)
engine/    AI 引擎(M1,Python + SQLite + systemd timer)
docs/      specs/plans/decisions/engine/ops/sessions/context
deploy/    服务器部署工件(随 M0 Task 8 落盘)
```

## 常用命令(site/ 下)

- `npm run dev` 本地开发
- `npm run build` 构建
- `npm run verify` build + 冒烟检查——**commit 前必须绿**

## 开发流程

详见 [docs/development/workflow.md](docs/development/workflow.md)(会话开始 live_state 核对 / 任务执行 / 提交规范 / 会话结束交接)。要点:

- 会话开始:读最新 session → `git log` 核对 → 跑验证,不符先纠偏
- commit 前自动验证必须绿(site:`npm run verify`;engine:`pytest`)——四级门禁见 [docs/development/quality-gates.md](docs/development/quality-gates.md)
- 会话结束写 `docs/sessions/` 交接记录——**硬性步骤,被中断也要写 continuable**
- 编码规范:[docs/development/coding-standards.md](docs/development/coding-standards.md)(零客户端 JS / 依赖白名单 / engine 目录结构 / 密钥只走环境变量)
- 设计/决策变更:先改 spec 或新增 ADR(模板 `docs/decisions/_template.md`),再改代码

## 禁止事项

- ❌ 不改 topic-digest 的任何东西(铁律 4)
- ❌ 密码/密钥不落盘:服务器密码只在交互输入,API key 只进服务器 env(铁律与凭据政策)
- ❌ 不在页面/构建里调 LLM(铁律 6)
- ❌ 不给博客本体加数据库、后台、客户端 JS(ADR-0002)
- ❌ 不跳过 `npm run verify` 提交
- ❌ 不引用过期文档——发现过期,当场修正或删除(nanmuli-blog 教训)
- ❌ M3 想法(周报/热度/事件聚簇等)只记录不动工,见 spec §9

## 环境速查(详见 server-environment.md)

- 服务器 123.56.223.97(Alinux 3,systemd **239**——timer 无时区后缀,1.8G 内存)
- 80/443 归 Caddy;服务器上有 topic-digest(8080)与 nanmu-skill-mcp(3456,**勿动**)
- 开发机 Windows 11 + Git Bash;shell 脚本必须 LF(.gitattributes 已强制)
