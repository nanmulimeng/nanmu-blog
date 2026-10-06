# 会话交接:M1 首批实施 Task 0–12(2026-10-06)

- **recorded_at**: 2026-10-06 Asia/Shanghai
- **continues**: [M1 开发交接](2026-10-06-m1-development-handoff.md)
- **repository**: 本批末 HEAD=c16fc2e、分支 main、未推送;本批 15 个提交 2e42c63..c16fc2e(末两位=整分支评审修复轮 39322eb + 审计 P1 修复轮 c16fc2e)。接手时已有的未提交文档修改(AGENTS.md、README.md、docs/README.md、plan、spec、handoff session)本批**未触碰、未 stage、未提交**,保持原样。
- **objective**: 按[已通过计划](../superpowers/plans/2026-10-05-m1-engine-implementation.md)从 Task 0 起实施 M1 首批(Task 0–12),inline 执行,TDD 全程,整批完成后交付审计。
- **change_scope**:
  - 本轮修改:新增 engine/(src 布局工程、12 表 db、config 四件套、tokenizer 计数、llm 客户端、ledger 账本、normalize、collect、prescreen、config 四件套与 prompts 资源)及对应测试;`docs/development/coding-standards.md` 依赖白名单加 tokenizers。未动 M0 应用代码、不动 topic-digest、不部署。
  - 接手时已有修改/暂存:见 repository 行,未触及。
  - 外部操作:仅经 hf-mirror.com 只读下载 tokenizer.json 公开资源(内容寻址哈希验真);无其它网络写操作、无部署、无付费。

- **state**:
  - Task 0–12 全部完成,提交与测试基线 [verified: 提交链 2e42c63→def2b8d→150ed3a→c4b58b9→28e91e8→5fd608c→4de73b6→7af1aab→c8bc8cf→16a4bfd→c84da2d→daf4a85→0ea31d0;`cd engine && python -m pytest -q` → 130 passed;ledger=.superpowers/sdd/2026-10-05-m1-engine-implementation/progress.md]
  - 整分支评审后修复轮(ONE pass)完成 [verified: 评审 2C+5I+8Minor+10Declined;7 项修复(停用语义/预占红线/跨月未决/回执状态/月投影幂等/对账共用/建库单事务)各带 RED→GREEN 新测试,commit 39322eb;全套装 138/138;8 Minor 全部 deferred、10 Declined 逐条裁定见 ledger Final 行]
  - 审计 P1 修复轮完成 [verified: 审计复核确认 138 passed 但独立探针复现 4 个 P1;修复=计费证据判定(三键齐才结算,缺项不核清)/金额上界对账(actual>reserved 同停)/结算与暂停同事务(三路径原子)/上海自然月口径(月窗口+月投影统一 +8 换算,原 M7 deferred 项销账);commit c16fc2e,11 个新测试全 RED→GREEN,全套装 149/149;同时撤销"tokenizer 哈希不匹配会拒载"裁定(审计实证 load_tokenizer 不验证声明哈希,一致性验证纳入 Task 22)]
  - 零真实付费证据边界 [verified: 全部模型调用为替身——test_llm 用替身 HTTP 断言最终请求体,不设 DEEPSEEK_API_KEY、不读真实 key;engine 代码无任何真实出网调用路径被执行;全套装仅 pytest,退出码 0]
  - 上游只读 [verified: collect 测试用临时夹具库经 connect_readonly(mode=ro);无任何写上游语句]
  - tokenizer 资源核对(Task 1 Step 1)[verified: HF API blobs=true blobId=628e3364caad11bdf9e67cea06eae7878122811d 与 size=6367146 逐字一致;hf-mirror 下载后 git hash-object 与该 blobId 相等入库;官方 encoding_dsv4.py 原文确认 chat 模板 `<｜Assistant｜></think>`]
  - 90 条真实样本 token 分布(Task 1)[verified: min 36 / p50 533 / p90 3006 / max 12438 / 超 4000 共 4 条——初始校准系数 1.0 依据;记录于当轮会话,脚本未留存]
  - E4 完整验证器为契约桩 [declared: Task 8 按 brief 停点条款先落桩(finish_reason=stop+JSON 契约),Task 13/14 落地真验证器后回跑 reusable_scores 测试——ledger 有记录]

- **verification**:

  | 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
  |--------------|----------------|----------------|
  | engine/(Windows 本机,Python 3.13.2;早前记 3.11 有误,更正) | `python -m pytest -q` | 通过;退出码 0,审计修复轮后 149/149(db 7、ledger 58;含评审轮 +9 与审计轮 +11 个修复测试、删 1 个锁定旧行为的跨月测试);含 token_count 3、config 22、llm 17、normalize 16、collect 12、freeze 5、prescreen 8;未覆盖:真实 API、真实上游库、并发、systemd 部署(Task 22–25);3.11 兼容性未验证(Task 25) |
  | engine/ | 各任务 RED→GREEN 逐轮执行 | 每任务先看失败再实现;失败形态经人工核对(ImportError/断言红),非跳过 |
  | 仓库根 | 文档运行 check_docs | 未运行(本批未改被其覆盖的文档结构;coding-standards.md 仅加白名单行,由审计裁量) |

- **pending_runtime**: 无。
- **decisions_needed**: 审计 AI 裁定 Task 8 两项 Ruling(response_json 三要素形态/E4 契约桩回跑点;原第三项"跨月未决预占归属"已被评审推翻并撤销,见 ledger Final 行)与 Task 12 两项(apply_n_new recoverable 单义修正/occupancy 快照形态)是否需要回补设计文档;另 8 条 deferred Minor 与修复轮附带裁定(2 个既有测试按 C2 新语义改构造)见 ledger `Final:` 行。

- **disposition**: continuable

- **next_action**: 下一批从 **Task 13**(score JSON 契约验证器)开始:brief=.superpowers/sdd/2026-10-05-m1-engine-implementation/task-13-brief.md;落真验证器后回跑 test_ledger 的 reusable_scores 用例(Task 8 停点条款);账本侧与采集侧接口已稳定,可按 plan 并行安排。本批不主张任何 M1 里程碑通过。

- **omissions**:
  - E4 验证器是契约桩,真验证器(Task 13/14)落地前 reusable_scores 的"过完整 E4 业务验证器"仅覆盖桩契约。
  - 上游 fetched_utc 真实格式未核实(夹具按 ISO-8601 Z 假定;ledger Task 10 Ruling),Task 25 服务器核查时校正。
  - 真实 WAL/SHM 只读条件(ADR-0003)未在本机验证,属 Task 25。
  - token 校准系数仍为 1.0 初始值,真实对账在 Task 22 校准通道;**load_tokenizer 当前不验证 config 声明的版本哈希**(审计实证),资源配置/加载版本/校准指纹一致性验证纳入 Task 22。
  - 90 条分布的统计脚本未入库(数据为本地 data/topic-digest.db 只读计算,一次性证据);离线样本计数不能单独证明服务端计量与系数 1.0 的对应关系。
  - 账本**不构成正式付费启用条件**:校准通道与真实对账未建立(Task 22),正式启用前须经该通道验证。
