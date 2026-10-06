# AGENTS.md — nanmu-blog

**一句话**:极简静态博客(手写文章)+ AI 引擎自动日报(读 topic-digest 数据)+ 自用 RAG。博客先上线,AI 是渐进叠加层,**任何一层挂掉博客都在线**。

## 项目状态快照(2026-10-06)

- M0:**全部完成并验收通过(2026-10-06,tag `m0`)**——首篇文章《你好,nanmu-blog》真实发布上线(发布计时12s),线上验收全通过(RSS XML 解析+CommaFeed 真实订阅、明暗主题、文章页/404),持锁回滚演练实操通过(切旧版 c8a4567 确认后切回)。证据见 [M0 验收交接](docs/sessions/2026-10-06-m0-acceptance.md)与 [部署交接](docs/sessions/2026-10-04-m0-deploy.md)
- **当前阶段:M1 本地实施推进中(Task 0-24 已实现,审计修复轮+跨模块核验与交界缝修复完成)**——engine/ 已创建并替身端到端绿(全套件 301 passed);用户审计 8 项(8d24fbe..9e4d8e0)与跨模块核验 8 处交界缝(9075620..a68cae2)均已按模块修复完毕,修复证据见交接文档。模型全部替身、上游只读、不部署不付费;Task 25 部署与 Task 26 真实付费须用户当次显式授权。
- 顺序:M1 Task 0-12→Task 13-24(本地替身端到端)→Task 25 部署/Task 26 分两段授权启用付费;进入条件以spec §9为准(M0 验收已满足)
- 执行方式:Native,按任务顺序执行;计划中提及的 skill 若环境没有,以本仓库 workflow 为准,按 [docs/superpowers/plans/2026-10-05-m1-engine-implementation.md](docs/superpowers/plans/2026-10-05-m1-engine-implementation.md) 逐任务
- 最新接手入口:[2026-10-06 M1 审计修复轮+跨模块核验](docs/sessions/2026-10-06-m1-audit-fix-round.md)(审计 8 项+交界缝 8 处修复全记录:账本校准/内容身份运行序/发布恢复/站点产物四组,测试与验收证据);前序:[M1 批次实施](docs/sessions/2026-10-06-m1-batch1-implementation.md)、[M1 开发交接](docs/sessions/2026-10-06-m1-development-handoff.md)。本轮修改/提交/推送状态接手时以 Git 实况核对。

## Agent接手入口

1. 读本文与上方最新交接,先明确**本轮用户目标**。交接中的下一步不是自动执行授权。
2. 按 [workflow](docs/development/workflow.md) 核对工作区、暂存区、分支与提交;保留已有修改,不要先清理工作区。
3. 初次进入补读 [项目背景](docs/context/project-background.md)(两个自有前项目与外部借鉴)、[经验教训](docs/context/lessons.md)及 [spec](docs/superpowers/specs/2026-10-02-nanmu-blog-design.md) 总体边界。继续会话只读本次影响的章节。
4. 读取当前任务的 plan 与实际文件;写代码前读 [coding-standards](docs/development/coding-standards.md),选择验证看 [quality-gates](docs/development/quality-gates.md)。未创建的应用不能当作现成功能。
5. 部署补读 [环境](docs/context/server-environment.md)与 [部署手册](docs/ops/deploy.md);M1补读 [上游契约](docs/context/topic-digest-data-source.md)。其余按需从 [文档索引](docs/README.md)查找。

本文保留入口与关键边界;会话动作由workflow维护,编码约束由coding-standards维护,验收条件由quality-gates维护。发现冲突先核对真相源与实际证据,不要复制另一套规则。

## 八条铁律摘要(完整定义以spec §2为准,修改先改spec)

1. **范围是生死线**:每个里程碑必须独立可发布,不欠债进下一个(nanmuli-blog 12.5 周烂尾的头号教训)
2. **博客本体永远不为 AI 功能加复杂度**:AI 挂了博客照常在线
3. **AI 引擎独立进程独立数据库**:engine 崩溃不影响博客,反之亦然
4. **topic-digest 保持现状不动**:本项目只读它的 SQLite(同机文件只读,`mode=ro`)
5. **付费请求先记回执再消费 + 三级次数限制与月/期金额预占**,全部付费LLM/embedding月预算红线 **¥50**
6. **页面永不调模型**:读者打开页面只读预生成内容
7. **AI 生成内容必须标注**:digest 栏目注明 AI 生成、模型与成本,与个人文章视觉区分
8. **文档随代码走**:设计变更先改文档;修改型会话结束写交接记录,只读讨论不强制写盘

## 项目结构

```
scripts/   已有文档检查工具
site/      Astro 5 静态站已建(M0 Task 2-8+8a;posts 手写 + digest 生成)
engine/    AI 引擎已建(M1 Task 0-24,Python + SQLite + systemd timer;src/nanmu_engine + tests,301 测试)
docs/      specs/plans/decisions/engine/ops/sessions/context
deploy/    服务器部署工件(已安装并在 Task 9 验收;线上 https://nanmu.xyz)
```

## 常用命令

仓库根:`python scripts/check_docs.py`检查文档;修改计划中的代码片段时加`--snippets`(需要Node与Git Bash)。

site/下(已创建,verify自Task7起可用):

- `npm run dev` 本地开发
- `npm run build` 构建
- `npm run verify` build + 冒烟检查 + 夹具临时构建验证;从Task7起用于site验证,此前用build。工作目录与各类任务要求见quality-gates

engine/下(M1 已建):

- `python -m pytest tests -q` 全套件(engine 目录内执行;替身模型+本地 bare repo,零真实网络)

## 开发流程

详见 [docs/development/workflow.md](docs/development/workflow.md)(会话开始 live_state 核对 / 任务执行 / 提交规范 / 会话结束交接)。要点:

- 会话开始:当前目标 → 最新session → Git/文件核对 → 适用基线验证。已有失败先区分原因,不顺手修无关问题
- commit前通过当前阶段适用验证;暂存/提交/推送分别核对范围与授权,不混入已有改动
- 修改型会话结束写 `docs/sessions/` 交接记录;只读审查不强制写盘——**硬性步骤,被中断也要写 continuable**
- 编码规范:[docs/development/coding-standards.md](docs/development/coding-standards.md)(零客户端 JS / 依赖白名单 / engine 目录结构 / 密钥只走环境变量)
- 设计/决策变更:先改 spec 或新增 ADR(模板 `docs/decisions/_template.md`),再改代码

## 禁止事项

- ❌ 不改 topic-digest 的任何东西(铁律 4)
- ❌ 密码/密钥不落盘:服务器密码只在交互输入,API key 只进服务器 env(铁律与凭据政策)
- ❌ 不在页面/构建里调 LLM(铁律 6)
- ❌ 不给博客本体加数据库、后台、客户端 JS(ADR-0002)
- ❌ 不跳过当前阶段适用验证提交;禁止故意将坏内容提交到生产 main
- ❌ 不把过期文档当执行依据——修改任务内修正相关指南;只读审查报告偏差。历史session保留,不为“更新”改写旧证据
- ❌ M3 想法(周报/热度/事件聚簇等)只记录不动工,见 spec §9

## 环境速查(详见 server-environment.md)

- 服务器 123.56.223.97(Alinux 3,systemd **239**历史记录;timer暂沿用本机裸时间策略,版本/时区/解析在部署时复核,1.8G内存)
- 80/443 归 Caddy;服务器上有 topic-digest(8080)与 nanmu-skill-mcp(3456,**勿动**)
- 开发机 Windows 11 + Git Bash;shell 脚本必须 LF(.gitattributes 已强制)
