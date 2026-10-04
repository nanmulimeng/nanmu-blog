# 会话交接:引擎技术设计(2026-10-04)

- **recorded_at**: 2026-10-04 13:18 Asia/Shanghai(同日调研轮扩展本记录)
- **continues**: [文档审查核验与小修](2026-10-04-audit-fixes.md)
- **repository**: 写时 HEAD `8d73e6a`(已推送 origin/main),分支 main,接手时工作区干净。本轮共 11 文件:新增 design.md 与本记录;接线轮改 docs/README、spec、data-source、coding-standards、pipeline、budget、glossary、根 README、AGENTS;调研轮再改 spec(§5.2/§11/变更记录)、budget、data-source、glossary、design.md 本体。2026-10-04 用户确认按推荐方案(R1/R7 反转保留),授权提交推送;本提交即本轮全部变更。
- **objective**: 按 2026-10-04 用户选择的方向,编写 M1 引擎技术设计细化(实施契约层):配置格式、判重规则、错误分类、模块契约、日志字段;不写 M1 plan(铁律 1:计划启动时再写)。同日用户追加要求"着重考虑架构与功能设计的开发细节,线上+线下调研"——完成 AIHOT url.ts / DeepSeek 官方文档线上核实与 topic-digest 本地库实测,并把结论回写各真相源。

- **change_scope**:
  - 本轮修改:新增 `docs/engine/design.md`;接线——docs/README.md(索引行、真相源表行、"开始引擎"路由、最新交接链接)、spec §5.6(指向 design.md)、data-source(多源平局规则改指 design.md)、coding-standards(目录结构后指模块契约)、pipeline.md(头部指针)、budget.md(候选容量指向公式)、glossary(候选上限词条)、README/AGENTS(最新交接入口);新增本记录。
  - 接手时已有修改:无(HEAD 干净)。
  - 外部操作:未执行服务器、发布或付费操作。

- **state**:
  - design.md 定位为 spec §5 与 M1 plan 之间的实施契约层,含七节:模块契约(11 模块 I/O/副作用/硬边界表)、配置四件套格式与校验(YAML 示例+字段表+fail-fast 加载契约)、identity_key 归一规则(R0-R7 序表+多源平局)、错误分类与退出码(E1-E10/W1 矩阵,退出码 0/1/2/3/4)、候选上限与额度预留公式(双币种截断)、日志与观测(行格式+最小事件集+禁入项+status 命令契约)、M1 计划对接(节→强制测试映射)[verified: 文件已落盘,check_docs 全绿]
  - 关键设计决定:identity_key 不哈希(`url:`+归一全文,依据 spec §5.3 DDL 注释);budget.yaml 为预算真相源、启动同步次数进 budget 表而金额不建表(避免双真相);未知源默认 T2;trailing slash 不归一(保守);追踪参数清单标注"按 spec §11 M1 前逐项核实";退出码 4 专门标记需人工的发布窗口/撤回暂停 [declared: 依据现有真相源推导,未经实现验证]
  - 接线后真相源边界:spec §5 产品契约 / engine 三文档运营口径 / design.md 实现契约 / M1 plan 步骤,四层互指不复制 [verified: docs/README.md 真相源表已加行]
  - 上轮遗留的 3 处审查发现已闭合(2 修复 1 保留),本轮未引入新的已知矛盾
  - 调研轮(线下):上游 HEAD 复核仍为 `f25d187`(未见漂移);本地库 `mode=ro` 实测 90 items/0.6MB/12 源(聚合 3 源未入本地库)、`content_text` 空值 27/90(约30%)、item 无 `fetched_utc` 索引(48h 窗口全表扫描)、90 条 URL 追踪参数 0 命中 [verified: sqlite3 探测 + git HEAD 核对,2026-10-04]
  - 调研轮(线上):AIHOT url.ts 全套归一规则(https 统一/去 www/黑名单 24 项/参数排序/去 trailing slash/微信四参固定顺序);DeepSeek 定价与 10-02 快照一致,新增事实:V4 系思考模式默认开且 effort=high(`extra_body={"thinking":{"type":"disabled"}}` 关闭)、JSON Output 两模型均支持、错误码 400/401/402/422/429/500/503、并发 Flash 2500/Pro 500、高峰=工作日 9-12/14-18 [verified: 官方文档与 GitHub raw 读取,2026-10-04]
  - 调研驱动的两处设计反转(初版保守、调研后改从生产验证行为):R1 http/https 统一按 https 归一(判重键;原 URL 保留展示);R7 trailing slash 去除(原样保留→去除,反例进测试 #1 观察清单)。llm.py 契约明确"单次调用单次返回,重试=新 attempt 由业务+ledger 编排"与思考模式显式关闭
  - spec §11 M1 启动前核查清单前两项闭合(黑名单定稿、DeepSeek 复核),剩服务器三项(topic-digest 现场/node 版本/API key)留 M1 部署期

- **verification**:

  | 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
  |--------------|----------------|----------------|
  | 仓库根 | `python scripts/check_docs.py` | 通过;退出码 0(调研轮复跑同过),41 份 Markdown、118 条本地链接全过、DDL 8 表、errors/warnings 为空。仅文档结构,design.md 的 YAML 示例不被语法校验(检查器只校验 plan 的 bash/js/json) |
  | 仓库根 | `git -c core.safecrlf=false diff --check` | 通过;退出码 0(调研轮复跑同过) |
  | 线上 | WebFetch:github.com/KKKKhazix/AIHOT `packages/backend/src/lib/url.ts`(main)、`industry/` 目录与 prompts 清单 | url.ts 归一规则全量核实(黑名单逐项、微信四参固定顺序、trailing slash 去除、https 统一);prompts/ 28 件粒度作参考;fetch 时点 2026-10-04 |
  | 线上 | WebFetch:api-docs.deepseek.com 定价/思考模式/错误码三页 | 定价与 10-02 快照一致;思考模式默认开/关闭参数/JSON Output/错误码/并发/高峰时段;fetch 时点 2026-10-04;上下文与最大输出长度页未给数,未采信未经核实数值 |
  | 线下 | `sqlite3 "file:...?mode=ro"` 计数/空值/索引/URL 模式探测;上游 `git rev-parse HEAD` | 见 state 调研轮(线下)各数字;铁律 4 只读未触碰上游写路径 |

- **disposition**: complete(技术设计、接线、调研与回写完成;变更经授权提交推送)
- **next_action**: 进入 M0 Task 2(Astro 脚手架,按 M0 plan Native 执行);M1 plan 留 M1 启动时编写(铁律 1);spec §11 剩服务器三项留 M1 部署期。
- **omissions**:
  - design.md 的公式/规则/字段未经任何实现或测试验证,是纸面契约;M1 实施中若发现缺陷须先改本文再改代码。
  - reasoning token 计费:官方定价页未单独说明思考模式计价,本项目按"输出侧单价、最坏按输出价预留"保守处理;若 M1 发现官方另有思考计价口径,先改 budget.md/design.md 再实现。
  - 本地库实测样本 90 条且早于聚合 3 源入库:追踪参数 0 命中、源分布、空值比例均不能外推到服务器库;黑名单有效性留 M1 服务器抽样。
  - AIHOT 回执/预算实现未定位到具体文件(lib/ 9 件与 backend/src 15 目录中未见 receipts 命名);本项目该域设计已由 ADR-0009 覆盖,深挖价值低,停止。
  - spec §11 剩服务器三项(topic-digest 现场/node/API key)未闭合,需用户配合 SSH。
  - title_blacklist 初值、prompts 文案本体留 M1 定稿。
  - 本轮 11 文件变更已随本提交入库;未运行 --snippets(未触碰 M0 计划代码片段)。
