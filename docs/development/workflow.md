# Claude Code 开发工作流

> 本仓库的主要开发者是 Claude Code(agent)。本文规定会话的固定动作,让任何会话产出可预期、可接续。纪律的来源:nanmuli-blog 死因之一就是跨会话断层(ADR-0008)。

## 会话开始(live_state 核对,必做)

按顺序执行,前一步不符就先处理再动工:

1. 读 `AGENTS.md`(铁律与导览)
2. 读 `docs/sessions/` **最新一份**交接记录(当前进度与 omissions)
3. `git log --oneline -10`(核对 session 记录声称的提交真实存在)
4. 跑验证:仓库当前有 site 则 `cd site && npm run verify`;有 engine 则 `cd engine && python -m pytest -q`
5. 对照:测试/构建结果与 session 记录一致 → 动工;不一致 → **先纠偏(修到绿或修正记录),把偏差写进今天的 session**

## 任务执行

### 有 plan 时(默认情况)

- 按 plan 的任务顺序逐个执行,**勾选 checkbox**,不跳步
- 每步按计划走 TDD 循环:写失败测试 → 确认失败 → 最小实现 → 确认通过 → commit
- **发现 plan 与现实冲突**:停下 → 改 plan(或记入 session 待用户决定)→ 再继续。禁止"顺手偏离"
- plan 外的改动(即使很小):单独 commit 并在 session 里注明"计划外"

### 无 plan 时

- 小事(bug 修复、文档更新、一两行改动):直接做,TDD 适用则 TDD
- 大事(新功能、新子系统):先停下,走 brainstorming → spec/plan 流程,不直接写代码

### 各层的"测试"形态

| 层 | 自动验证 | 人工验证(结果记入 session) |
|----|----------|------------------------------|
| site(Astro) | `npm run verify`(build + 冒烟) | `npm run dev` 看视觉效果、明暗主题 |
| engine(Python) | `python -m pytest -q`(LLM 一律 mock) | 真跑一轮日报(仅在部署/里程碑验收时,花钱前查预算) |
| 服务器/部署 | curl 输出、日志 tail 输出(粘贴进 session) | 浏览器确认 |

### 提交规范

- 格式:`type(scope): 中文描述`,type ∈ feat/fix/docs/chore/test/refactor/ops
- 一个逻辑变更一个 commit;TDD 的红/绿可以合为一个 commit
- **commit 前:对应层的自动验证必须绿**(这是硬门禁,见 [quality-gates.md](quality-gates.md))
- 直接在 main 上提交,不建长期分支

### 依赖与密钥

- 新增运行时依赖:先问"stdlib/现有依赖能不能做"→ 不能则加,并在 commit message 或 ADR 写明理由
- **密钥(API key/密码)只进环境变量**:本地 `.env`(已 gitignore)或服务器 systemd `EnvironmentFile`;config 文件与代码里永远只有变量名引用

## 服务器任务

- 严格按 `docs/ops/deploy.md` 与 `docs/ops/runbook.md` 逐字执行,不即兴发明命令
- 每条命令的关键输出(curl 状态码、日志 tail)粘贴进 session 作为证据
- 不可逆操作(删除、覆盖)必须先列目标让用户确认

## 会话结束(硬性步骤,不可省略)

1. 对应层自动验证跑最后一遍,确认绿
2. 写 `docs/sessions/YYYY-MM-DD-<主题>.md`(用 `_template.md`):state 带证据、omissions 显式列出
3. 提交 session 记录
4. disposition 如实写:continuable / blocked / complete
5. (M0 Task 9 配好 server remote 后)`git push server main`——服务器 bare repo 是代码的异地副本;未推送的提交只存在于开发机(nanmuli-blog 带着 601 行未提交工作死掉的教训)

被中断(上下文耗尽/用户打断)时同样适用——**宁可提前写 continuable 记录,不留断层**。

## 不确定时的顺序

查文档(spec/ADR/context)→ 查代码实读 → 问用户。禁止凭猜测改代码或配置;禁止编造"文档里应该有"的内容。
