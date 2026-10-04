# 文档索引

**Agent接手路线**:[AGENTS.md](../AGENTS.md)→ 最新session → workflow的Git/文件核对 → 本轮相关spec/plan。初次进入补读背景与教训;环境、引擎与RAG文档按任务加载。

| 文档 | 内容 | 状态 |
|------|------|------|
| [context/project-background.md](context/project-background.md) | 两个自有前项目与外部借鉴:为什么存在、继承什么、拒绝什么 | 定稿 |
| [context/lessons.md](context/lessons.md) | 经验教训对照表:两个前项目的真实踩坑 → 对策 → 落点 | 定稿(踩新坑时追加) |
| [context/server-environment.md](context/server-environment.md) | 服务器/开发机环境事实(部署排障必读,含 [declared] 分级) | 随巡检更新 |
| [context/topic-digest-data-source.md](context/topic-digest-data-source.md) | 上游数据源实况:schema 契约/15 源清单/已知坑 | 定稿(M1 前复核) |
| [context/glossary.md](context/glossary.md) | 术语表(新 agent 对齐词汇) | 定稿 |
| [development/workflow.md](development/workflow.md) | Agent工作流:接手核对、范围/授权、工作区保护、失败处理、交接 | 定稿(约束所有会话) |
| [development/coding-standards.md](development/coding-standards.md) | 编码规范:site/engine/RAG + 依赖白名单 + 测试要求 | 定稿(M1/M2 遵守) |
| [development/quality-gates.md](development/quality-gates.md) | 分阶段验证矩阵、证据口径、四类活动门禁、未来测试清单 | 定稿 |
| [superpowers/specs/2026-10-02-nanmu-blog-design.md](superpowers/specs/2026-10-02-nanmu-blog-design.md) | 设计文档(唯一设计真相源,§2 八条铁律) | 定稿 |
| [superpowers/plans/2026-10-02-m0-blog-launch.md](superpowers/plans/2026-10-02-m0-blog-launch.md) | M0实施计划(10主任务+Task8a边界补验) | Task1-8+8a已实施;9-10待做 |
| [writing.md](writing.md) | 新建文章/草稿/同步/发布/撤回/图片与URL | 本地可用;线上发布待Task9-10验收 |
| [architecture.md](architecture.md) | 三件套架构与数据流 | 定稿 |
| [decisions/](decisions/) | ADR 架构决策记录(0001-0009;模板 `_template.md`) | 持续追加 |
| [engine/design.md](engine/design.md) | 引擎实施契约层:模块I/O、配置格式与校验、判重规则、错误分类与退出码、日志与观测 | 定稿(M1 实施基准) |
| [engine/pipeline.md](engine/pipeline.md) | 日报管线各阶段说明 | 定稿(M1 实施基准) |
| [engine/selection.md](engine/selection.md) | 精选标准/门槛/调整记录(编辑策略) | 定稿(随运营调整) |
| [engine/budget.md](engine/budget.md) | 成本治理与月度成本台账 | 定稿(台账按月追加) |
| [ops/deploy.md](ops/deploy.md) | SSH/目录/权限/Caddy/上线确认/回滚操作 | 工件已落盘;运行验收待9-10 |
| [ops/runbook.md](ops/runbook.md) | 巡检/回滚/故障处理 | 定稿 |
| [reviews/2026-10-02-documentation-audit.md](reviews/2026-10-02-documentation-audit.md) | 文档审查依据、已修订问题与实施前核查 | 本轮审查完成,运行项待对应阶段验证 |
| [sessions/](sessions/) | 开发会话交接记录(模板 `_template.md`;最新一份 = 当前进度) | 每会话一份 |

## 文档纪律

- 设计变更先改 spec/ADR 再改代码
- 当前指南中的过期指令及时修正或移除;只读审查先报告偏差,不改写历史证据
- 当前操作指南只描述有效流程;ADR保留替代方案与被取代的历史结论,历史session保留当时证据

## 真相源与更新责任

| 信息 | 唯一责任位置 | 其他文档的职责 |
|------|--------------|----------------|
| 产品范围/跨组件契约/阶段推进策略 | spec(阶段策略§9) | ADR解释决策,计划落实步骤;冲突先修设计再实施,不另建重复路线图 |
| 当前实际进度 | 最新 session + Git/文件/运行证据 | README/AGENTS只是入口快照,不能代替验证 |
| Agent会话执行/编码/验证 | development/workflow、coding-standards、quality-gates各司其职 | AGENTS只保留入口与关键边界;session模板承载交接,不另立规则 |
| 任务执行与验收 | 当前里程碑 plan + quality-gates | 测试通过才勾选,文档示例不是运行结果 |
| 服务器现状/上游依赖 | context/server-environment 与 data-source | 历史验收与当次实测分开,未验证明确标注 |
| 运营策略/成本 | engine/selection、budget、pipeline | 与 spec契约同步;计价只在budget维护,实现读取配置 |
| 引擎实现契约(模块边界/配置格式/判重/错误分类/日志) | engine/design.md | spec §5 保持产品契约,engine 三文档保持运营口径;M1 plan 引用而不复制 |
| 写作与内容维护 | writing.md | 字段以spec为准,不复制部署命令 |
| 部署操作/日常巡检 | ops/deploy.md / ops/runbook.md | plan保留实施与验收步骤,工件落盘后实现以deploy/为准 |
| 调研证据与缺口 | reviews/ | 保存出处与待核查事项,不复制完整设计 |

未来工件用行内代码标“尚未创建”,不要生成死链接。旧 session 是历史快照不改写,新 session 明确接续。引用外部可变事实必须带来源与核查时点;未复测的性能只能称估值。

## 按目标选择文档

- 接手当前工作:先看[最新交接](sessions/2026-10-04-m0-task8a.md),再按[工作流](development/workflow.md)核对目标、Git与工作区。交接格式见[模板](sessions/_template.md),初次进入才补读背景链。
- 写文章:writing.md本地预览 → M0已验收后的发布流程。开发博客:spec §4 → Task9-10上线。
- 上服务器:server-environment.md → ops/deploy.md → ops/runbook.md。准备手册存在不代表部署已完成。
- 开始引擎:先核对spec §9的M0验收前提 → spec §5 → data-source → engine三文档与design.md → quality-gates测试清单 → 编写M1计划。
- 开始RAG:先核对spec §9的M1验收前提 → spec §6 → quality-gates的M2项 → 目标环境探针与固定问题集 → 编写M2计划。

## 文档验证命令

在仓库根运行(仅Python标准库):

```bash
python scripts/check_docs.py
git diff --check
```

变更M0脚本/JavaScript示例时追加:

```bash
python scripts/check_docs.py --snippets
```

Windows若PATH中的bash指向WSL启动器,显式选择Git Bash,例如本机当前路径:

```powershell
python scripts/check_docs.py --snippets --bash 'D:/software/Git/Git/bin/bash.exe'
```

脚本见[check_docs.py](../scripts/check_docs.py)。默认检查本地内联链接路径(不验证网页/锚点/引用式链接)、代码围栏、spec与M0的两个schema示例、SQLite DDL。--snippets在临时目录检查Bash/JS/JSON并运行冒烟正反例,不执行部署、不替代Astro构建。退出码0为检查通过,非0必须查看errors;缺Node/Bash不能记作通过。

## 状态与变更边界

“定稿”表示可作为设计基线,不表示代码已存在;“准备版”表示已有操作步骤但先决工件/现场验证未完成;“已验收”必须有运行证据。未来任务中的checkbox只有实际执行后才勾选。

变更产品或跨组件契约:先spec/ADR,再同步消费它的plan/engine文档。纯事实勘误可修改正文或给历史ADR附勘误;旧session不重写。完成的计划任务只保留简要结果与证据,删除失效模板;不要让同一操作流程在多份文档中复制。

一次文档会话做到已发现的矛盾闭合、检查通过、omissions能定位下一阶段即可收尾。服务器和付费运行证据在对应阶段取得,不以持续补文档代替实现。

同日多份session以记录中的Asia/Shanghai时间与“接续”关系排序,不按主题字母排序;入口链接指向最近一次修改型会话。只读审查不制造空交接。

检查器的`syntax_and_links`只证明围栏/路径可解析,`contracts`只证明两份schema文本一致及DDL可执行,`snippets`只覆盖计划中提取的Bash/JS/JSON和冒烟夹具。重复的完整二级章节以`warnings`提示人工确认;不把Astro/TypeScript编译、一般操作命令或真实服务验收包含在“文档检查通过”里。
