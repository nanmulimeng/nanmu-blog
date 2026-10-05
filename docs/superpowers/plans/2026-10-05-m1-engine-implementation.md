# M1 AI 引擎实施计划(待评审稿)

> **For agentic workers:** 本计划按任务顺序以 TDD 执行;步骤用 checkbox(`- [ ]`)跟踪,只有实际执行后才勾选。
>
> **⚠️ 实施前置门禁(优先于一切任务)**:本文件是 **M1 plan 待评审稿**,评审通过 ≠ 自动开始实施。按 spec §9.1"启动"行:实施开始须**用户明确解除暂停**。在收到该指示前,本计划只能被评审与修订,不得创建 engine/ 代码、不得部署、不得发起任何真实付费调用。

**Goal:** 实现 nanmu-blog 的 M1 AI 引擎——collect→判重→预筛→双次评分→摘要→组装→发布全链,费用治理(账本/预算/重试)与期恢复在任何中断下不丢不重。

**Architecture:** 独立进程 Python 引擎(11 个设计模块 + run/ops/notify/token_count 入口与支撑),engine.db(SQLite WAL,12 表)唯一可写状态源;一切付费调用经 ledger.py 授权闸门(短事务预占后出网);发布走专用 Git 工作副本 + 线上证据链;topic-digest 只读(`mode=ro`)。

**Tech Stack:** Python 3.11 stdlib + httpx + PyYAML(tokenizer 包由 Task 1 选定后追加白名单);pytest + pytest-mock;LLM 一律替身测试。

**Spec:** [docs/superpowers/specs/2026-10-02-nanmu-blog-design.md](../specs/2026-10-02-nanmu-blog-design.md)(总体);[engine/design.md](../../engine/design.md)(模块契约/配置/错误矩阵/判重);五单元详细设计 [engine/units/](../../engine/units/)(本计划的设计真相源,本计划**只编排顺序、依赖、验收与停点,不复制设计**——每个任务的规则细节以所引单元文档章节为准)。

## Global Constraints

以下数值与边界逐字来自真相源文档;任何任务不得偏离,发现文档间冲突以 spec §5/单元文档为准并停下报告:

- **八条铁律**(spec §2):范围生死线/博客零复杂度/引擎独立进程独立库/topic-digest 只读不动(`mode=ro`)/付费先记回执再消费+三级限次+月期金额预占/页面永不调模型/AI 内容必标注/文档随代码走。
- **预算参数**(budget.yaml 真相源 engine/budget.md):monthly=50000000 微元(¥50)/per_issue=1000000(¥1)/warn_monthly=40000000(¥40);rate_limits 10/100/400(分钟/小时/日);max_attempts=2(含首次)/unknown_retry_after_min=30;max_input_tokens=4000/max_output_tokens=200;thinking=disabled、json_output=true(其他值 E1.config)。
- **12 表 DDL 唯一真相源 = spec §5.3**(entry/receipt/receipt_attempt/budget/analysis/override/digest_issue/issue_freeze/api_usage/summary/notify_sent/engine_meta)。coding-standards 目录树注释中"8 表"为旧数字,实施时以 spec §5.3 为准(该行随 Task 3 一并修正)。
- **再发送三条件与名额唯一口径(第四轮定稿)** = units/model-calls.md §3 规则 5 + spec §5.3.1:**attempt_origin 为预占时确定的授权来源,写入后不可改写**(unknown 通道重试返回 503 保持 origin='unknown_retry';再发起普通重试是新授权 origin='retry');**普通尝试已用数=该 logical_key 中 `attempt_origin IN ('initial','retry')` 行数(不按 error_class 过滤——名额按授权消耗)**,上限 max_attempts;error_class 只决定能否再发送与通道(no_retry 拒/retryable 普通通道/unknown 满等待走 unknown 通道);unknown 专属=receipt.unknown_retry_used(与 origin='unknown_retry' 行同事务双写);硬上限=总行数<max_attempts+1;两类名额不互借;重启仅凭 DB 重放判定。
- **预占金额公式**(budget.md 预占策略行,plan 逐字引用,不得漏输出项):预占金额 = 向上取整后的输入预占 token 数 × 峰时未缓存输入价 + `max_output_tokens` × 输出价,最终向上取整为整数微元。
- **pay_paused 闸门读法与置位来源** = units/model-calls.md §3 规则 1 / units/scheduling-ops.md §3 规则 9:**仅显式 0 放行;=1 或键缺失均拒绝一切新增付费**(复用/结算/只读不受限);合法库建库时即写入默认 0。**置位来源=restore-backup 步骤② + 单元二对账硬失败**(usage 超计数/供应商实付>预占/校准样本超计数)——停新增=持久化置位并记录原因,重启继续拒绝,人工核对后显式解除;不另建第二套暂停系统。
- **安全边界**:API key 只从环境变量读(真实 key 只在服务器 `/etc/nanmu-blog.env`);密钥与全文内容不进日志;原文材料视为不可信数据,不执行其中指令;模型输出按固定模板转义/限制(渲染后 HTML 断言)。
- **测试纪律**(coding-standards):LLM 一律 mock;单测零网络零花费;文件写入/Git/上游库用临时目录与替身;集成验收单列执行前提,不混入默认单测。
- **付费与部署停点**:真实付费调用(含校准模式)与服务器操作在 Task 26/25,均需用户当次显式授权;此前一切任务零真实网络付费。

## 两项带入验证任务(第三轮核验指定,独立标记)

- **[V1] Tokenizer 验证,置于付费链路启用之前** = Task 1 + Task 22 + Task 26 前置检查。计划列明:资源与版本(Task 1 选定并锁定)、消息结构计数方式(完整请求消息含结构开销)、**校准样本来源**(两阶段:零付费离线样本 + 走完整账本的受控校准调用——解"未校准不得调用,却必须先调用才能取得校准数据"的执行循环,不以校准绕过账本与预算;**契约=units/model-calls.md §3 规则 11(第四轮入契约,不再只在 plan 设例外)**:例外唯一/月预算与窗口照常适用/校准记录绑定模型+tokenizer 资源与版本+计数方式+系数,配置任一变化即失效须重校准/**初始系数:官方资源=1.0,无官方资源不预设默认系数,建立不了覆盖依据则停**)、通过条件(零超预占事件,任何 usage.prompt_tokens>预占计数=置 pay_paused 停新增+修正)。
- **[V2] 备份切换验收覆盖实际 SQLite 文件状态** = Task 21 验收内容:连接关闭、WAL checkpoint 处理、重新打开副本后暂停标志校验、切换边界中断测试(真实文件系统,非内存库)。**本轮设计评审只做了顺序审查,未执行文件级恢复实验——顺序审查 ≠ 恢复功能已验收**,该结论只能由 Task 21 的运行证据给出。

## Review Focus(最可能咬人的五类输入/失败模式 → 持有任务)

1. **中断窗口**(Git 与 SQLite 非同事务;授权后出网前;响应落库前;备份切换边界)——恢复只补记不重生成、不存在"已启用旧库但付费未暂停"中间态 → 测试在 Task 5/7/17/21。
2. **重启后仅凭 DB 重放**(名额判定/期状态/内容操作当前可见状态)——判定函数无内存依赖,两次独立连接断言一致 → 测试在 Task 6/17/19。
3. **名额类别混用与计数边界**(HTTP 400 计数未满也不再调用;普通耗尽不借 unknown;耗尽不因重启重获)——反例=max_attempts=2 两次普通失败、总数 2<3 不构成发送许可 → 测试在 Task 6(验收种子 7c/7d)。
4. **不可信输入**(原文材料提示注入、模型输出 Markdown 链接伪装、`javascript:` URL)——页面呈字面文本、DOM 无对应 `<a>`、危险 scheme 拒入产物 → 测试在 Task 13/16(渲染后 HTML 断言)。
5. **裸恢复/备份时点错配**(活动库缺 pay_paused 键;恢复旧库丢回执致同身份重发重复付费)——键缺失同拒+status 提示;恢复后先拒新增待人工核对账单 → 测试在 Task 21。

---

## 任务依赖总览

```
Task 0 工程初始化 → Task 1 [V1]tokenizer核对 → Task 2 config → Task 3 db → Task 4 llm替身 → Task 5 ledger闸门
  → Task 6 重试判定 → Task 7 结算/unknown/快照 → Task 8 复用/N_new
  → Task 9 normalize → Task 10 collect → Task 11 冻结 → Task 12 prescreen
  → Task 13 score → Task 14 summarize → Task 15 入选/claim → Task 16 assemble/安全
  → Task 17 publish四窗口 → Task 18 撤回/重上/纠错
  → Task 19 run运行序 → Task 20 notify → Task 21 [V2]ops/restore-backup → Task 22 [V1]校准执行
  → Task 23 site schema → Task 24 替身端到端 → Task 25 部署对接(需授权) → Task 26 付费链路启用(需授权)
```

串行为主链;Task 9-12(采集侧)与 Task 5-8(账本侧)可并行开发但测试种子独立。**任何任务失败(测试红且两轮修复无效)→ 停在当前任务,报告卡点,不进入后续任务。**

---

### Task 0:engine 本地工程初始化(第四轮新增)

**Files:**
- Create: `engine/requirements.txt`(运行:httpx、PyYAML,+Task 1 选定的 tokenizer 包;测试:pytest、pytest-mock,分 `[dev]` 段)
- Create: `engine/pyproject.toml`(src 布局包元数据,`pip install -e .[dev]` 可装)
- Create: `engine/src/nanmu_engine/__init__.py`、`engine/tests/conftest.py`

**Interfaces:**
- Produces: 可安装的 `nanmu_engine` 包(src 布局,coding-standards 目录树);pytest 可发现 `engine/tests/`;`conftest.py` 提供 `tmp_engine_db`(临时 SQLite:connect_db+migrate)、替身 LLM fixture(后续任务复用)。

**步骤:**

- [ ] Step 1:创建上述骨架文件(pyproject 用 setuptools src-layout;requirements 与 pyproject 依赖一致)。
- [ ] Step 2:`cd engine && pip install -e ".[dev]"`,确认 `python -c "import nanmu_engine"` 成功。
- [ ] Step 3:写冒烟测试 `engine/tests/test_smoke.py`(`def test_package_importable(): import nanmu_engine`),`python -m pytest -v` 通过(此时 conftest 的 db fixture 尚无实现,留空函数占位,Task 3 填充——占位是 fixture 声明,不是设计占位)。
- [ ] Step 4:commit `chore(engine): src 布局工程骨架与测试基建`。

**停点:** 无。

### Task 1 [V1]:tokenizer 资源核对与 token_count.py

**Files:**
- Create: `engine/src/nanmu_engine/token_count.py`
- Create: `engine/tests/test_token_count.py`
- Modify: `docs/development/coding-standards.md`(依赖白名单追加选定 tokenizer 包——先改文档再装依赖)

**Interfaces:**
- Produces: `count_request_tokens(model: str, messages: list[dict]) -> int`(确定性、离线、零网络;计数对象=完整请求消息数组,含 role/结构开销与全部 content;异常时抛 `TokenizerUnavailable`);`load_tokenizer(model: str) -> Tokenizer`(从 config 映射加载,失败即 `TokenizerUnavailable`,**无任何字符比例回退**)。
- Consumes: config 中 `tokenizers` 映射(Task 2 定契约:`model → {resource, version}`)。

**步骤:**

- [ ] **Step 1:核对模型方 tokenizer 发布渠道**(DeepSeek,2026-10-04 已复核官方文档基线)。记录:资源名、版本、发布渠道、离线可用性、确定性依据,写入本任务实施记录(session)。**分支(依据=units/model-calls.md §3 规则 11"初始系数依据",第四轮定稿)**:①官方离线 tokenizer 存在 → 锁定版本进 config,初始校准系数=1.0(依据=资源即服务端分词器);②不存在 → **不预设默认系数**——必须先建立"近似资源+系数能覆盖目标 API 输入计量"的依据(来源、版本、覆盖论证写入实施记录),并下调 max_input_tokens 预算余量;**建立不了覆盖依据则停,不进入付费**;若以近似资源做小额探索,标注为"尚未验证上界的小额实验",不得表述为"已建立保守上界"。两分支都必须使"计数不可得→不出网"可测。
- [ ] **Step 2:写失败测试**(种子:units/content-editing.md §7 场景 3 前半):

```python
def test_count_covers_message_structure_not_just_text():
    # 同一段文本,裸字符串计数 < 完整 messages 结构计数(结构开销必须计入)
    bare = count_text(TEXT)
    full = count_request_tokens("deepseek-flash",
        [{"role": "system", "content": SYS}, {"role": "user", "content": TEXT}])
    assert full > bare

def test_mapping_missing_raises_no_char_fallback(monkeypatch):
    # model→tokenizer 映射缺失 → TokenizerUnavailable,绝不回退字符估算
    with pytest.raises(TokenizerUnavailable):
        count_request_tokens("unknown-model", MSGS)

def test_deterministic():
    assert (count_request_tokens(M, MSGS)
            == count_request_tokens(M, MSGS))  # 同输入两次计数一致,跨进程亦然
```

- [ ] **Step 3:跑测试确认失败**。Run: `cd engine && python -m pytest tests/test_token_count.py -v`。Expected: FAIL(module 不存在)。
- [ ] **Step 4:最小实现** token_count.py(加载选定资源;messages 按消息结构逐项编码求和)。
- [ ] **Step 5:跑测试通过**;同步 coding-standards 白名单;commit `feat(engine): tokenizer 计数模块(资源锁定+无回退)`。

**验收补充:** 离线样本=本地 topic-digest 既有 90 条正文构造真实请求结构,计数分布记入实施记录(校准阶段 A 证据)。
**停点:** 官方渠道无离线资源,且无法建立"近似资源+系数覆盖目标 API 输入计量"的依据 → 停,报告候选与论证缺口,等用户裁决(单元二规则 11:不预设默认系数,不以无依据系数进入付费)。

### Task 2:config.py 四件套加载与校验

**Files:**
- Create: `engine/src/nanmu_engine/config.py`、`engine/config/sources.yaml`、`engine/config/budget.yaml`、`engine/config/selection.yaml`、`engine/config/prompts/score.md`、`engine/config/prompts/understand.md`
- Test: `engine/tests/test_config.py`

**Interfaces:**
- Produces: `load_config(root: Path) -> Config`(类型化对象:Sources/Budget/Selection/Prompts/Tokenizers;含 pricing_version 与各文件 hash);校验规则逐条=design.md"配置包格式与校验"节(字段表+E1.config 拒绝项:bool 冒充 int/缺必填/重复键/NaN/未知 version/`thinking≠disabled`/`json_output≠true`)。
- Prompts 全文=units/content-editing.md 附录 A 逐字落盘;`prompt_version = sha256(文件内容)`。
- Consumes: 无(首任务级)。

**步骤:**

- [ ] Step 1:写失败测试——种子:design.md 配置校验表的非法值逐例(每行一个断言:`rate_limits 任一 ≤0` 是合法停用 E5.limit 而非 E1;`max_attempts=0` 拒绝;`warn_monthly>monthly` 拒绝;`monthly>50000000` 拒绝;pricing 缺 default_model 行拒绝;两文件重复模型价目拒绝)。`prompt_version` 断言:改一字节 → hash 变。
- [ ] Step 2:跑测试确认失败。
- [ ] Step 3:实现 load_config(只读 config/,YAML 逐字段校验,非法输入抛 `ConfigError` 附字段名)。
- [ ] Step 4:跑测试通过。
- [ ] Step 5:commit `feat(engine): 配置加载与校验(四件套+prompts)`。

**停点:** 配置校验表与单元文档出现矛盾 → 停,报告冲突行,先修文档再实现。

### Task 3:db.py 12 表迁移

**Files:**
- Create: `engine/src/nanmu_engine/db.py`
- Test: `engine/tests/test_db.py`

**Interfaces:**
- Produces: `connect_db(path: str) -> sqlite3.Connection`(WAL/busy_timeout=5000/foreign_keys=ON,本项目唯一可写连接入口);`migrate(conn) -> None`(版本化迁移;空库直接建 12 表,**建库同事务写 engine_meta 默认 `pay_paused=0`**);`connect_readonly(path: str)`(topic-digest 用,`file:...?mode=ro`,不执行写 PRAGMA)。
- DDL 逐字=spec §5.3(含 receipt_attempt 三列 attempt_origin/error_class/fail_detail_json、digest_issue ops_json/content_sha256、issue_freeze paused 三列、engine_meta pay_paused)。

**步骤:**

- [ ] Step 1:写失败测试:

```python
def test_fresh_db_writes_pay_paused_default_zero(tmp_path):
    conn = connect_db(tmp_path / "engine.db")
    migrate(conn)
    # 建库即写默认 0 —— 键缺失不可能是正常新库状态(scheduling-ops 规则 9)
    assert conn.execute(
        "SELECT v FROM engine_meta WHERE k='pay_paused'").fetchone()[0] == "0"

def test_table_count_is_12(tmp_path):
    ...  # 12 表齐全,列名与 spec §5.3 一致(抽查三新列存在)
```

另:旧库带旧版本号 → 逐版本迁移成功;遇到未知较新版本 → 拒绝启动写入不重置(coding-standards SQLite 约定)。
- [ ] Step 2-4:红→实现→绿。
- [ ] Step 5:commit `feat(engine): db 单一入口与 12 表迁移`;修正 coding-standards L35"8 表"为"12 表(spec §5.3)"。

**停点:** spec §5.3 DDL 与单元文档字段映射不一致 → 停(理论上已被三轮核验排除,出现即报告)。

### Task 4:llm.py 替身客户端与错误分类

**Files:**
- Create: `engine/src/nanmu_engine/llm.py`
- Test: `engine/tests/test_llm.py`(httpx MockTransport)

**Interfaces:**
- Produces: `call_llm(request: LLMRequest) -> LLMResult`;`LLMRequest{model, messages, max_tokens, purpose, request_hash}`;`LLMResult` 携带 http_status/finish_reason/usage/供应商请求 ID/原始响应文本。**单次调用单次返回,禁用透明重试**;key 只从环境变量。
- Produces: `classify_failure(result_or_exc) -> (error_class, fail_detail)`——映射矩阵:**no_retry={E1.request(HTTP 400/401/422), E4.terminal, E5.balance(402)};retryable={E3.http(429/500/503), E4.parse};unknown={E3.unknown}**(spec §5.3.1;`fail_detail={http_status:int?, matrix_code:str, message:截断摘要}`)。

**步骤:**

- [ ] Step 1:写失败测试——种子:design.md llm.py 调用契约 + model-calls 验收 7d 前置:
  - MockTransport 断言**最终 HTTP JSON 顶层字段**:含 `"thinking":{"type":"disabled"}`、`response_format`、`stream:false`、显式 `max_tokens`,**无 `extra_body` 层**;
  - 请求体 messages 与传入一致(截断后实际输入);
  - `classify_failure` 矩阵逐例:400→no_retry;503→retryable;429→retryable;超时/连接断→unknown(E3.unknown);JSON 解析失败但 HTTP 200→retryable(E4.parse)+**finish_reason=length 且 JSON 恰好可解析→E4.terminal 语义(非正常终止不可消费)**;402→no_retry。
- [ ] Step 2-4:红→实现(httpx 非流式,读环境变量 key)→绿。
- [ ] Step 5:commit `feat(engine): llm 客户端(替身断言最终请求体+错误分类映射)`。

**停点:** 无(纯替身)。

### Task 5:ledger.py 授权闸门与预占

**Files:**
- Create: `engine/src/nanmu_engine/ledger.py`
- Test: `engine/tests/test_ledger.py`

**Interfaces:**
- Produces: `authorize(purpose, model, request_hash, identity_key, token_count, issue_date, origin: Literal['initial','retry','unknown_retry']) -> AttemptRef`(短事务 BEGIN IMMEDIATE→COMMIT **后**才允许出网);`reject_reason -> Literal['pay_paused','key_missing','window','money','token_count_unavailable']`。
- Consumes: Task 3 db、Task 1 token_count(计数不可得→`token_count_unavailable` 拒绝)、Task 4。
- 闸门检查序(model-calls §3 规则 1):`engine_meta.pay_paused` **仅显式 '0' 放行,'1' 或键缺失拒绝** → 窗口次数(receipt_attempt.started_utc 聚合;复用不计)→ 金额(已结算+全部未决预占)→ 通过则写 receipt_attempt(pending+reserved+attempt_origin+issue_date+pricing_version),首 attempt 同事务建 receipt 行。

**步骤:**

- [ ] Step 1:写失败测试——种子:model-calls 验收 6 + 规则 1:

```python
def test_pay_paused_gate(tmp_path):
    conn = connect_db(...)
    # 显式 '1' → 拒;删键模拟裸恢复 → 同拒;显式 '0' → 放行
    set_meta(conn, "pay_paused", "1")
    assert authorize(...) is rejected("pay_paused")
    conn.execute("DELETE FROM engine_meta WHERE k='pay_paused'")
    assert authorize(...) is rejected("key_missing")
    set_meta(conn, "pay_paused", "0")
    assert authorize(...).status == "reserved"

def test_hour_window_full_rejects_without_writing_attempt(...):
    # 小时窗口将满 → 拒且不写预占行(断言表内无新行)
```

金额预占公式(budget.md 预占策略行逐字,**第四轮修正:输出上限必含,不得漏**):预占金额 = 向上取整后的输入预占 token 数 × 峰时未缓存输入价 + `max_output_tokens` × 输出价,最终向上取整为整数微元(budget.md"峰时未缓存输入价与完整输出上限"策略)。
- [ ] Step 2-4:红→实现→绿。
- [ ] Step 5:commit `feat(engine): 授权闸门(pay_paused 读法+窗口/金额+attempt_origin 预占)`。

**停点:** 无。

### Task 6:失败更新与再发送三条件(持久化重放)

**Files:**
- Modify: `engine/src/nanmu_engine/ledger.py`
- Test: `engine/tests/test_ledger.py`(追加)

**Interfaces:**
- Produces: `record_failure(attempt_ref, error_class, fail_detail, usage=None)`(单事务:attempt→failed/unknown + error_class + fail_detail_json 同事务写;有 usage 先结算);`can_retry(logical_key, now_utc) -> RetryVerdict`(再发送三条件判定,**输入全部来自持久化列**)。
- 名额公式逐字=model-calls §3 规则 5 条件 2/3(spec §5.3.1,**第四轮口径**):普通尝试已用数=`attempt_origin IN ('initial','retry')` 行数(**不按 error_class 过滤,名额按授权消耗**)≤max_attempts;unknown=receipt.unknown_retry_used=0 且 ≥30min;硬上限=总行数<max_attempts+1;两类不互借;**origin 预占后不可改写**——record_failure 只写 error_class/fail_detail_json。

**步骤:**

- [ ] Step 1:写失败测试——种子:model-calls 验收 **7/7b/7c/7d 全部**(7d 含第三轮反例与第四轮 origin 授权语义序列表,逐句落实):

```python
def test_7d_replay_from_disk_after_close(tmp_path, fake_http_400):
    # 同一请求首 attempt 注入 HTTP 400 → 落库 → 关闭连接
    run_attempt(tmp_path, inject=HTTP(400))
    # 重新打开 DB,仅凭行数据判定(判定函数无内存依赖)
    verdict = can_retry(logical_key, NOW)
    assert verdict.allowed is False and verdict.reason == "error_class_no_retry"

def test_7d_503_counts_against_normal_quota(...):  # error_class='retryable' 按普通剩余名额
def test_7d_normal_exhausted_unknown_unused_still_rejects(...):  # 不互借
def test_7d_origin_immutable_unknown_channel_returns_503(...):
    # 序列:attempt1 initial/超时未知 → attempt2(≥30min,unknown 通道)返回 503
    # → 断言 attempt2 行保持 origin='unknown_retry'/error_class='retryable'(不因返回类型改写)
    # 若普通名额仍有剩余而再发起 → attempt3 是新授权 origin='retry',计入普通尝试已用数
def test_6_quota_counts_attempts_not_error_classes(...):
    # 普通尝试已用数=origin∈{initial,retry} 行数:initial/unknown 与 initial/retryable
    # 各占一个普通名额(不按 error_class 过滤);失败更新事务断言不改写 attempt_origin
def test_7c_max2_two_normal_failures_no_send_after_restart(...)  # 普通已用 2=max_attempts,总数 2<3 不构成许可
```

- [ ] Step 2-4:红→实现(record_failure 同事务写三列;can_retry 纯 SQL 查询)→绿。
- [ ] Step 5:commit `feat(engine): 失败持久化与再发送三条件(落库重放判定)`。

**停点:** 7d 任一断言两轮修复仍红 → 停(这是第三轮 P1 的直接验证,红=契约未闭合)。

### Task 7:结算、unknown、核清与费用快照

**Files:**
- Modify: `engine/src/nanmu_engine/ledger.py`
- Test: `engine/tests/test_ledger.py`(追加)

**Interfaces:**
- Produces: `record_response(attempt_ref, llm_result)`(先持久化 received+usage_json 再谈解析;actual 按价目快照结算);`reconcile(attempt_ref, evidence) -> bool`(证据四要素齐才 UPDATE actual+reconcile_json,单事务);`issue_cost_snapshot(issue_date) -> (cost_cny, cost_pending)`(**同一只读聚合查询**:Σ(已核清 actual,未核清 reserved);pending=存在任一 actual IS NULL,**不限 status=unknown**)。

**步骤:**

- [ ] Step 1:写失败测试——种子:model-calls 验收 7(unknown 30min 替身时钟)/8(快照算例:3 settled+1 received 未核清→¥0.0289/pending=true;零 attempt 期→0/false;查询计数替身断言单查询)/9(证据缺失拒绝核清,actual 仍 NULL)/10(跨期复用费用归属)。
- [ ] Step 2-4:红→实现→绿。
- [ ] Step 5:commit `feat(engine): 结算/unknown/核清/期费用快照`。

**停点:** 无。

### Task 8:请求身份、复用判定与 N_new

**Files:**
- Modify: `engine/src/nanmu_engine/ledger.py`
- Test: `engine/tests/test_ledger.py`(追加)

**Interfaces:**
- Produces: `request_hash(identity_ctx) -> str`(sha256 确定性序列化:provider/endpoint/purpose/model/prompt_version/模板实例化后完整 system+user 文本(截断后实际输入)/max_tokens/thinking/response_format/identity_key/content_hash/attemptTag——逐字=model-calls §3 规则 2);`reusable_scores(members, identity_ctx) -> ReuseSnapshot`(只读零副作用,含 needs);`compute_n_new(params) -> int`(design.md 候选上限公式本体引用,不复制)。

**步骤:**

- [ ] Step 1:写失败测试——种子:model-calls 验收 1(复用矩阵:同身份 completed 可;prompt 版本变不可;**截断标记差异不可**;received 过完整 E4 验证器可;不可解析不可;**finish_reason=length 而 JSON 可解析→不可**)/2(N_new 作用顺序:4 复用+6 新增、N_new=4→4+4+2 capped;N_new=0→4 recoverable+6 capped 无丢失)/3(部分完成 needs 补缺,attempt_no 顺延不重置)。
- [ ] Step 2-4:红→实现→绿。
- [ ] Step 5:commit `feat(engine): 请求身份/复用判定/N_new`。

**停点:** E4 验证器(完整版)依赖 score/understand 的 JSON 契约 → 本任务先用契约桩,Task 13/14 落地真验证器后回跑本测试(接口断言已在种子中)。

### Task 9:normalize.py 判重归一

**Files:**
- Create: `engine/src/nanmu_engine/normalize.py`
- Test: `engine/tests/test_normalize.py`

**Interfaces:**
- Produces: `identity_key(url: str) -> str`(规则与跟踪参数清单逐字=design.md 判重节)。

**步骤:**

- [ ] Step 1:写失败测试——种子:design.md 五个 URL 期望表逐条断言(与 design.md 共享测试夹具,单元一 §8);data-ingestion 验收 1 前半(多源同 key 选 T1 行属 Task 10)。
- [ ] Step 2-4:红→实现→绿。
- [ ] Step 5:commit `feat(engine): URL 归一与 identity_key`。

**停点:** 无。

### Task 10:collect.py 只读采集与 entry 落库

**Files:**
- Create: `engine/src/nanmu_engine/collect.py`
- Test: `engine/tests/test_collect.py`(夹具:临时 SQLite 模拟 topic-digest 库)

**Interfaces:**
- Consumes: Task 9、`connect_readonly`。
- Produces: `collect_once(issue_date, now_utc) -> Manifest`(窗口=fetched_utc 近 48h、fresh/clustered、排除 dropped;本地写单事务:entry 刷新(used 不刷新)/多源同 key 胜出(tier 优先,平局 item.id 小者)/discovered_utc 寿命锚定)。

**步骤:**

- [ ] Step 1:写失败测试——种子:data-ingestion 验收 1(多源同 key)/5(快照刷新:新期用新 hash、旧期 manifest 不变)/6(used 不刷新)/7(双层窗口与寿命锚定)/12(E2:上游拒绝只读→digest_issue failed 落行由单元五写,本任务断言 collect_failed 日志+异常分类)/13(规模护栏 warning)。
- [ ] Step 2-4:红→实现(mode=ro,查询带超时观察)→绿。
- [ ] Step 5:commit `feat(engine): 只读采集与 entry 落库`。

**停点:** topic-digest 真实库的 WAL/SHM 只读访问条件(ADR-0003)在服务器核查(Task 25);本地用夹具。

### Task 11:冻结 issue_freeze 与 manifest

**Files:**
- Create: `engine/src/nanmu_engine/collect.py`(冻结函数)或独立冻结段;Test: `engine/tests/test_freeze.py`

**Interfaces:**
- Produces: `freeze_issue(conn, issue_date, manifest, now_utc) -> frozen_utc`(幂等:同 issue_date 再调直接返回 frozen)。
- **事务边界(第四轮澄清:任务拆分 ≠ 事务拆分)**:entry upsert 与 issue_freeze INSERT 属于**同一个事务拥有者(collect_once),一次提交**——data-ingestion"collect 本地写单事务"契约;Task 10/11 只是测试关注点拆分,任何把两者拆成两次 COMMIT 的实现即偏离契约,验收 2(冻结原子性:事务内注入 kill→无行无半写)会抓住跨事务半写。

**步骤:**

- [ ] Step 1:写失败测试——种子:data-ingestion 验收 2(步骤 4 事务内注入 kill→无行无半写,重跑一致)/3(幂等:二次 collect_once 上游查询计数=0)/4(空集合:freeze(entry_count=0, manifest='[]') 落地)。
- [ ] Step 2-4:红→实现→绿。
- [ ] Step 5:commit `feat(engine): 期冻结原子性与幂等入口`。

**停点:** 无。

### Task 12:prescreen.py 零成本预筛

**Files:**
- Create: `engine/src/nanmu_engine/prescreen.py`
- Test: `engine/tests/test_prescreen.py`

**Interfaces:**
- Produces: `prescreen(manifest, occupancy, override, reuse_snapshot, n_new) -> PrescreenResult`(纯函数;四去向 to_score/recoverable/excluded/capped 全覆盖不变量;两层排除:内容/编辑适用全体、占用仅他期;确定性排序=平局键 design.md)。
- Consumes: Task 8 reuse_snapshot/n_new(经编排层传入,预筛不查 receipt)。

**步骤:**

- [ ] Step 1:写失败测试——种子:data-ingestion 验收 8(预筛矩阵与占用分层,含"本期 selected 续跑保留 recoverable、他期 selected 排除")/9a-d(N_new=0 四子场景)/10(强制项截断可见性:接口断言消费方可识别"强制项未完成评分")/11(平局收敛:行序颠倒输出不变)。
- [ ] Step 2-4:红→实现→绿。
- [ ] Step 5:commit `feat(engine): 纯函数预筛四去向`。

**停点:** 无。

### Task 13:score.py 双次评分与 E4 验证器

**Files:**
- Create: `engine/src/nanmu_engine/score.py`
- Test: `engine/tests/test_score.py`(LLM mock)

**Interfaces:**
- Consumes: Task 5/6 授权与失败记录、Task 4、Task 1(tokenizer 计数+迭代截断)、Task 2 prompts。
- Produces: `score_entry(member, ctx) -> ScoreOutcome`;完整 E4 业务验证器(正常终止 finish_reason=stop+JSON 契约字段类型/范围全过)在此定稿并回填 Task 8 桩;analysis 行与 receipt completed **同事务**(交界=units/content-editing.md §5)。

**步骤:**

- [ ] Step 1:写失败测试——种子:content-editing 验收 2(权重自检:虚构五轴手算 71;题文不符 ≤30;赞助 ≤20)/3(截断与计量:完整请求计数 ≤4000;改一字节 hash 变;**tokenizer 映射缺失→断言零新增付费 attempt 不出网**;标题超界剔除记日志;system+最小标题空间>4000→E1 拒启动;**替身 usage.prompt_tokens 超预占计数→断言停新增调用非仅日志**)。
- [ ] Step 2-4:红→实现→绿;回跑 Task 8 复用矩阵。
- [ ] Step 5:commit `feat(engine): 双次评分(prompt 附录A+E4 验证器+tokenizer 截断)`。

**停点与停新增机制(第四轮定稿,不留实现者自由选择):** "超预占=停新增"=**置 engine_meta.pay_paused='1' 持久化并记录原因**(复用既有闸门,与备份恢复暂停同一解除协议:人工核对后显式置 0;重启继续拒绝;复用/结算/只读照常)——不是内存态,不引入 `halt_new_charges` 第二套系统。契约已同步至 units/model-calls.md §3 规则 2/8 与 scheduling-ops §3 规则 9(第四轮),实现直接引用,无需再回写设计。

### Task 14:summarize.py 摘要写作

**Files:**
- Create: `engine/src/nanmu_engine/summarize.py`
- Test: `engine/tests/test_summarize.py`

**Interfaces:**
- Produces: `understand_entry(member, digest_ctx) -> SummaryOutcome`(中文标题答案先行/一句话/推荐理由/标签;summary 行与 receipt completed 同事务;JSON 契约含虚构自检约束)。

**步骤:**

- [ ] Step 1:写失败测试——种子:content-editing 附录 A understand prompt 契约(JSON 输出含"json"字样与格式示例→llm.py 断言已覆盖;此处断言业务字段:标题非空、标签集、赞助冲突检查)+ 单条失败→剔除不挂整期(接口级)。
- [ ] Step 2-4:红→实现→绿。
- [ ] Step 5:commit `feat(engine): 摘要写作`。

**停点:** 无。

### Task 15:入选判断与 claim 占用协议

**Files:**
- Create: `engine/src/nanmu_engine/select.py`(或并入 score.py——按 design.md 模块表,入选判断属 score 域;实现时择一并记录)
- Test: `engine/tests/test_selection.py`

**Interfaces:**
- Produces: `decide_selection(analysis_rows, thresholds, override) -> SelectionResult`;claim 协议(content-editing §3 规则 7):selected 同事务写 entry.claim_issue;published 置 used+清 claim;**未进产物的被排除 selected 同事务置 rejected+清 claim**;放弃 failed 期→claim 清、status 回 scored、used 不动;启动校验抓 selected 而 claim 空的脏数据。

**步骤:**

- [ ] Step 1:写失败测试——种子:content-editing 验收 1(入选分离:T1 70 入一瞥、T2 75 落选 rejected;force_include 低分入末尾带标注)/4(claim 协议全事件)/6(失败隔离与就绪:普通缺摘要剔除其余组装;强制缺任一暂停;F=16 暂停;F=1+普通 15→1+14;最终集合空 failed 不产文件;组合场景断言无 rejected 持 claim 残留)/9(零合格:断言不产 draft)。
- [ ] Step 2-4:红→实现→绿。
- [ ] Step 5:commit `feat(engine): 入选判断与占用协议`。

**停点:** 无。

### Task 16:assemble.py 组装与安全输出

**Files:**
- Create: `engine/src/nanmu_engine/assemble.py`
- Test: `engine/tests/test_assemble.py`

**Interfaces:**
- Produces: `assemble_issue(issue_date, selected, summaries, cost_snapshot) -> DigestDraft`(markdown+frontmatter 六字段:date/generated/ai_model/entry_count/cost_cny/**cost_pending 显式布尔**;板块阈值运营参数;示例 model ID 必须替换实际调用模型);`draft 落盘同事务写 digest_issue.content_sha256`;安全转义函数(渲染后断言)。
- Consumes: Task 7 issue_cost_snapshot。

**步骤:**

- [ ] Step 1:写失败测试——种子:content-editing 验收 7(**渲染后 HTML 断言**:模型输出 `[伪装链接](url)`→页面字面文本、DOM 无 `<a>`;`<script>` 字面转义;`javascript:` URL→拒入产物;含括号/空白 URL 正确编码)——测试需起渲染管线(模板转义函数),不是字符串比对;验收 8(draft 期 override exclude→重组装无该条、其余摘要复用零费用查询计数断言);pipeline.md 产物模板结构逐项。
- [ ] Step 2-4:红→实现→绿。
- [ ] Step 5:commit `feat(engine): 组装与安全输出(渲染后 HTML 验证)`。

**停点:** 无。

### Task 17:publish.py 专用副本、四窗口与 ops_json

**Files:**
- Create: `engine/src/nanmu_engine/publish.py`
- Test: `engine/tests/test_publish.py`(临时 git 仓库夹具,禁止真实 push——用本地 bare repo 夹具模拟远端)

**Interfaces:**
- Produces: `publish_issue(draft, ctx) -> PublishResult`(专用工作副本;fast-forward 同步前置检查;commit 回填 git_commit;push→submitted;线上证据链三步→published);`ops_json` append 协议(publish-withdraw §3 规则 5:每项 {seq, op, target_sha256, stages{commit?,pushed?,confirmed_utc?}},**操作开始即 append 未完成项**;当前可见状态=最新 confirmed op;撤回 target=ABSENT);远端接收判定=**分支可达性**(merge-base --is-ancestor,ls-remote 只示尖端)。

**步骤:**

- [ ] Step 1:写失败测试——种子:publish-withdraw 验收 1(推进+used/claim 清空与 published 同事务+未进产物 selected→rejected+claim 清)/2(**四窗口 W1-W4 各注入 kill→恢复只补记不重生成(评分调用计数零);W2:工作副本文件被人为改动→仍以库内 content_sha256 在 git 历史查找;查找失败→转人工;人工确认未提交后重组装零新增;W3:SHA 在尖端可达但非 origin/main 祖先→不判 submitted**)/3(隔离检查:副本存在他期未推送提交→新期不 push+转人工)/8(线上 SHA 含提交但路径 404→不判 published)。
- [ ] Step 2-4:红→实现→绿。
- [ ] Step 5:commit `feat(engine): 发布链四窗口恢复与 ops_json`。

**停点:** 无。

### Task 18:撤回、重新上线与纠错

**Files:**
- Modify: `engine/src/nanmu_engine/publish.py`
- Test: `engine/tests/test_publish.py`(追加)

**Interfaces:**
- Produces: `withdraw(issue_date, reason)`(四步+暂停置位经单元五命令);`relist(issue_date, mode: 'verbatim'|'corrected', corrected_draft=None)`(原样恢复内容身份=撤回父版本;修正后恢复=新提交;**修正稿落盘即 append target=新身份**;均零模型调用);`correct(issue_date, new_draft)`(纠错提交,历史保留)。

**步骤:**

- [ ] Step 1:写失败测试——种子:publish-withdraw 验收 4(撤回全序列:三处消失+withdrawn 落库+暂停;重启无自动重发;**push 成功后 kill→按未完成项 target(ABSENT)+远端删除提交补记;再撤回:当前可见状态=撤回(最新 confirmed op=withdraw),relisted 列保留首次事实不参与判定**)/5(重上两条:零模型调用计数断言;修正后恢复 push 后 kill→按库内 target 找回;状态判定重启后仅凭 DB+站点核验复现;证据不足→转人工)/6(纠错 entry_count 如实变化)/7(核清后提示→纠错提交后三处一致)。
- [ ] Step 2-4:红→实现→绿。
- [ ] Step 5:commit `feat(engine): 撤回/重上/纠错(内容操作记录)`。

**停点:** 无。

### Task 19:run.py 调度运行序

**Files:**
- Create: `engine/src/nanmu_engine/run.py`
- Test: `engine/tests/test_run.py`

**Interfaces:**
- Produces: `main() -> int`(退出码 0/1/2/3/4,优先级 1→2→4→3→0);运行序逐字=scheduling-ops §3 规则 1:flock 单实例→config/预算校验(pay_paused 键缺失=跳过新增付费部分,只读照常)→**先恢复存量未完成期**(issue_date 升序;submitted 只读确认→draft 发布恢复→生成中续跑;paused 跳过;recover_budget_s=600 总预算,耗尽→保存状态**继续新期**)→当天新期全链→汇总记账→收尾写 last_exit/last_run_utc。
- 截止判定(scheduling-ops §3 规则 2):资格锚点=issue_freeze.frozen_utc 唯一;D 与 D+1 两触发窗;D+2 起不自动开始;submitted 只读确认不受限。

**步骤:**

- [ ] Step 1:写失败测试——种子:scheduling-ops 验收 1(恢复顺序:submitted+draft+生成中+paused 各一期→断言顺序)/1b(**恢复预算与新期保底反例:旧期持续失败占满 recover_budget_s→当天新期仍完成 collect+生成**)/2(frozen_utc 锚点:D+1 窗结束仍 draft→D+2 不含该期+通知一次+D+3 去重;晚 push 不延长;D+1 窗内已开始可跑完)/3(暂停:置位→零动作)/4(failed 重跑=续跑:冻结/回执复用计数断言)/5(spec §5.3.1 逐项在各中断窗口后可查)。
- [ ] Step 2-4:红→实现→绿。
- [ ] Step 5:commit `feat(engine): 调度运行序(先恢复后新期+截止锚点)`。

**停点:** 无。

### Task 20:notify.py 与 notify_sent

**Files:**
- Create: `engine/src/nanmu_engine/notify.py`
- Test: `engine/tests/test_notify.py`(发送替身)

**Interfaces:**
- Produces: `notify(event_key, message)`(同 key **UPSERT**:首现 INSERT、重试后 UPDATE result/sent_utc——dedup_key 主键,同 key 二次 INSERT 必冲突,不得另起一行);立即类(E1/402/E8/E9/W1)发生即发但入表按 key 去重;连续 2 期类(E2/E6/无合格)按子类+期判二期;`warn-monthly:`+YYYY-M 月度去重;发送失败有界重试不改账本;**崩溃边界:发送成功未落库→重启可能重复通知,不承诺 exactly-once/至多一次**。

**步骤:**

- [ ] Step 1:写失败测试——种子:scheduling-ops 验收 6 全部(同 key 重试成功 UPDATE 原行断言无第二次 INSERT 无主键冲突;正常持久化后同 key 零重发;**不设次数上限断言**——收窄后的承诺)。
- [ ] Step 2-4:红→实现→绿。
- [ ] Step 5:commit `feat(engine): 通知去重(UPSERT+收窄承诺)`。

**停点:** 无。

### Task 21 [V2]:ops.py status 与 restore-backup(文件级验收)

**Files:**
- Create: `engine/src/nanmu_engine/ops.py`
- Test: `engine/tests/test_ops_restore.py`(**真实文件系统+SQLite 文件,非内存库**)

**Interfaces:**
- Produces: `restore_backup(backup_path, live_path)` 五步逐字=scheduling-ops §3 规则 9 表(①恢复到待启用副本不动活动库→②副本置 pay_paused=1→③**读回校验**(关闭连接后重开副本:key 存在且='1';失败中止不切换)→④原子切换 rename→⑤核对清单);全程持有与常规运行相同互斥锁;`pause_issue/unpause_issue`;`status(issue_date=None)`(scheduling-ops §3 规则 8 五组事实;活动库无 pay_paused 键→提示核对)。
- **不变量:活动库完成切换 ⇔ 其内 pay_paused=1 已先持久化**。

**步骤:**

- [ ] Step 1:写失败测试——种子:scheduling-ops 验收 8 全部 + 本任务 [V2] 文件级强化:

```python
def test_v2_checkpoint_close_reopen_before_switch(tmp_path, kill_at):
    # ②后崩溃:副本已置位——断言前先 conn.execute("PRAGMA wal_checkpoint(FULL)")
    # 并 close();以全新连接重开副本读 pay_paused=='1'(WAL 未合并/读旧快照均会漏)
    ...
def test_v2_switch_boundary_crash_states(tmp_path):
    # ①③后崩溃 → 活动库未动可重试;④后崩溃 → 新活动库已含标志;
    # 任何中断点重启后:不存在"活动库已启用且 pay_paused≠'1'"(除活动库从未被替换)
def test_v2_bare_restore_key_missing(tmp_path):
    # 活动库删 pay_paused 键(模拟绕过命令的裸恢复)→ 闸门拒绝新增+status 提示核对
def test_v2_backup_older_than_published_state(...):
    # 备份时点 draft、实际已 published → 线上证据链补记 published(幂等)
```

- [ ] Step 2-4:红→实现(shutil+os.rename;WAL checkpoint 在读回校验前强制)→绿。
- [ ] Step 5:commit `feat(engine): status/restore-backup(文件级切换验收)`。

**验收口径声明:** 本任务运行通过前,设计文档中的 restore-backup 五步**仅为顺序审查结论,不得表述为"恢复功能已验收"**;通过后以本任务测试证据为准。
**停点:** 文件级测试暴露顺序审查未发现的窗口 → 停,先回 scheduling-ops/spec 修订序列再改实现(文档先行)。

### Task 22 [V1]:校准模式执行体 calibrate 命令

**Files:**
- Modify: `engine/src/nanmu_engine/ops.py`、`engine/config/budget.yaml`(calibration 段,字段已入 design.md 配置契约)
- Test: `engine/tests/test_calibrate.py`(替身)

**Interfaces:**
- Produces: `calibrate()`——**契约=units/model-calls.md §3 规则 11(第四轮入契约,本任务只实现不另行设计)**:
  - **阶段 A(零付费,Task 1 已完成)**:离线样本(本地 topic-digest 90 条正文构造请求结构)→ 计数函数自身验证;
  - **阶段 B(受控付费)**:固定样本(3 条最小合成材料+1 条真实短文)**走完整账本流程**(purpose='calibration',经授权闸门预占/attempt/结算,**月预算与窗口限额照常适用**,不设免检额度;`calibration.budget_micro_cny` 预占合计上限,耗尽即中止不追加),产出 usage.prompt_tokens vs 预占计数比值;
  - **例外范围唯一**:正式管线(purpose∈{score,understand})的授权前置=校准状态对**当前配置**生效;calibration purpose 是该检查的唯一例外(解"未校准不得调用,却必须先调用才能校准"执行循环);
  - **校准记录绑定配置**:engine_meta 记录 {model, tokenizer 资源与版本, 消息计数方式, 校准系数, 样本对账结果, 判定时刻}——**任一项变化即失效须重校准**,不是可跨配置沿用的 passed 标志;
  - 通过条件:全部样本 ratio≤1 → 校准状态对当前配置生效;任一 ratio>1 → **置 pay_paused 停新增(同规则 2)+上调系数(人工确认后重新校准)**。
- Config 契约(design.md budget.yaml 已同步):`tokenizers` 映射(Task 1)+`calibration.budget_micro_cny`;**初始系数不进 config 默认值**——官方资源=1.0(依据=资源即服务端分词器),无官方资源依 Task 1 建立的覆盖论证,建立不了则停。

**步骤:**

- [ ] Step 1:写失败测试(替身模拟 usage 返回;种子=model-calls 验收 11 全部):ratio≤1 全过→校准状态生效+绑定记录落 engine_meta;ratio>1→停新增置 pay_paused 断言(持久化,重启仍拒);校准预算耗尽→中止不追加;calibration attempt 在账本中可查且**计入窗口与月预算**(不绕闸门断言);**换模型/tokenizer 资源或版本/计数方式/系数任一项→状态失效,正式管线重新拒绝新增**。
- [ ] Step 2-4:红→实现→绿(校准状态读写与配置指纹比对;单元二规则 11 为行为规范)。
- [ ] Step 5:commit `feat(engine): 校准模式(走账本的受控校准通道)`。

**停点:** 真实校准调用(非替身)属 Task 26 授权范围;本任务只交付替身验证过的执行体。

### Task 23:site schema 消费与 AI 标注

**Files:**
- Modify: `site/src/content.config.ts`(digest collection schema 加 cost_pending 字段;注意实际路径是 `src/content.config.ts`,不是 `src/content/config.ts`)
- Modify: `site/src/pages/digest/[...page].astro`(列表页成本行,当前 L24 附近"成本 ¥{cost_cny}")
- Modify: `site/src/pages/digest/[id].astro`(详情页成本行,当前 L16 附近"成本 ¥{cost_cny}")
- Test: site 既有 `npm run verify` + schema 负例;engine 侧断言在 Task 16(见步骤)

**步骤:**

- [ ] Step 1:写失败测试——schema:digest collection 加 `cost_pending: z.boolean().default(false)`(**default 仅旧文件兼容**——site 侧验证"旧文件缺字段可过"是兼容行为,**"新生成文件必须显式写布尔值"由 engine 组装测试断言(Task 16:assemble 产物总含显式 cost_pending),两职责不混在 schema 一处**);负例=类型错(字符串 `"false"`/整数)→构建拒绝。页面:cost_pending=true 时列表页与详情页成本行同步显示"(含未决预占,为保守上界)"(digest-design §3.4 文案);ai_model 为示例 ID 的拒绝属 engine 断言(assemble 用实际调用模型,铁律 7),schema 保持 min(1) 不重复实现。
- [ ] Step 2-4:红→实现→绿(`npm run verify`,含两个页面渲染断言)。
- [ ] Step 5:commit `feat(site): digest cost_pending schema 与两页成本标志显示`。

**停点:** 无(纯本地构建)。

### Task 24:替身端到端集成

**Files:**
- Test: `engine/tests/test_e2e.py`(整链 mock LLM+本地 bare repo 夹具+临时库)

**步骤:**

- [ ] Step 1:写集成测试:小样本(≤5 条)全链贯通——collect(夹具上游)→冻结→预筛→评分→摘要→组装→发布(夹具远端+线上证据桩)→published;三失败路径各一(E2 上游拒/LLM 全挂→failed+退出非零+通知;单条失败剔除不挂整期)。**重启重放分窗口断言(第四轮修正:"任意阶段 kill 后零新增付费"不成立,已删)**:①评分响应已有效→不重发(复用,零新增);②评分缺失/身份失效→**可按授权补发(允许新增付费,逐过闸门与名额)**;③unknown→预占保留,遵循等待条件与名额;④发布恢复(commit/push/确认窗口)→**零模型调用**。各窗口分别 kill 后重跑断言对应行为。
- [ ] Step 2:跑通;修复跨界缝隙(接口失配在本任务暴露,修接口定义处)。
- [ ] Step 3:commit `test(engine): 替身端到端全链`。

**停点:** 跨任务接口失配两轮修不平 → 停,报告失配点与两侧契约。

### Task 25:部署对接(⚠️ 需用户当次授权:服务器操作)

**Files:**
- Create: `deploy/nanmu-blog-engine.service`+`nanmu-blog-engine.timer`(每日 08:30 + RandomizedDelaySec=300 + Persistent=true)、engine systemd EnvironmentFile 引用说明
- Modify: `docs/ops/runbook.md`(restore-backup/status/暂停命令;备份纳管复用 topic-digest `conn.backup()` Online Backup 模式,保留 30 天)

**授权方式(第四轮修正):** 一次授权覆盖本任务列明的操作范围,范围内直接执行;**范围变化或遇未列操作再确认**(不再逐步机械请示)。

**步骤:**

- [ ] Step 1:核查清单执行(spec §11/单元一 §9):服务器侧 topic-digest DB 路径、只读 WAL 权限以 engine 运行用户验证(`mode=ro`);fetched_utc 分布实测回填 data-source(48h 窗口候选量级证实或修订);systemd timer 时区核对。
- [ ] Step 2:部署 timer 与 `/etc/nanmu-blog.env`(key 只进 env)——**timer 安装但保持 disabled(不 enable/start)直至 Task 26 步骤 3 完成付费启用**;期间引擎侧校准状态检查是第二道闸门(校准状态对当前配置未生效=正式管线拒绝新增付费);测试告警一次(OnFailure 链路,经手动触发 service 验证,不启动定时付费)。
- [ ] Step 3:commit+部署记录 session。

**停点:** 任一服务器前置核查不通过 → 停,报告;**不修改 topic-digest 任何配置(铁律 4)**。

### Task 26:真实付费链路启用(⚠️ 分两次授权:真实校准 / 正常付费运行)

**前置检查(全部通过才请求第一次授权):** Task 0-24 全绿;校准方案与预算已按 units/model-calls.md §3 规则 11 定稿(初始系数有依据或已停);闸门/重试/备份文件级验收有运行证据;用户明确解除实施暂停的指示在案。

**授权顺序(第四轮解循环,五步不得倒置):**

- [ ] Step 1:**本地与替身验证全部通过,校准方案及预算明确**(含初始系数依据)→ 请求并获**真实校准授权**(范围=calibration.budget_micro_cny 内的校准调用)。
- [ ] Step 2:`calibrate` 真实执行(受控预算内)→ 检查结果:全部样本 ratio≤1 → 校准状态对当前配置生效;任一超出 → 置 pay_paused 停新增,报告并等人工处置(**不得进入后续步骤**)。
- [ ] Step 3:校准通过后,请求并获**正常付费运行授权**(范围=首期小样本+后续自动调度)。
- [ ] Step 4:首期真实运行(小样本)→ 人工核验产物。
- [ ] Step 5:启用 timer(Task 25 保持 disabled 的对应动作)→ 连续 3 天自动产出+每天最多 5 条人工核验(spec §9.1 M1 交付);M1 验收:连续 3 天日报、单期 ≤¥1、熔断注入测试通过(timer 环境下验证 pay_paused/E5.limit 停新增)、AI 标注可见;证据写 session。

**停点:** Step 2 校准失败 → 停在付费暂停态等人工处置;真实运行中任何超预占/重复付费迹象 → 立即置 pay_paused=1(显式命令,同 restore 语义)→ 停,报告账本证据。

---

## Self-Review 结论(plan 写作自查;第四轮核验修正后复检)

1. **覆盖核对**:spec §9.1 M1 范围(collect→评分→摘要→日报发布全链+成本治理)→ Task 9-19/24;五单元 §7 验收场景全部映射到任务(data-ingestion 1-13→Task 9-12;model-calls 1-11→Task 5-8/22;content-editing 1-9→Task 13-16;publish-withdraw 1-8→Task 17-18;scheduling-ops 1-8→Task 19-21);两项带入验证任务→[V1]Task 0/1/22/26、[V2]Task 21。
2. **无占位符**:每任务有 Files/Interfaces/种子编号与代表性测试;数值逐字引自真相源;第四轮清除项:Task 13 停新增机制不再留实现者选择(=置 pay_paused)、Task 22 初始系数不再有默认 1.2。
3. **类型一致**:AttemptRef/ReuseSnapshot/PrescreenResult/DigestDraft/PublishResult 跨任务引用同名。
4. **Review Focus 五类均有持有任务测试**(见各条目)。
5. **第四轮修正落位自查**:①origin 授权语义(授权时消耗名额)→Task 6 测试+Global Constraints+model-calls v5+spec §5.3.1+pipeline;②校准通道入契约→model-calls 规则 11+design.md calibration 字段+Task 1/22/26;③预占公式含输出上限→Task 5+Global Constraints;④Task 26 五步授权顺序+Task 25 timer 保持 disabled;校正表四项→Task 0/Task 10-11/Task 23/Task 24。

## 文档边界声明

- 本计划不复制五单元设计;规则细节以所引文档为准,冲突时先修文档再改实现(文档随代码走铁律 8 的反向约束)。
- Task 13 若发现需持久化"停新增"标志、Task 22 的 config 契约追加,均属契约层增量:实现前回写对应单元文档与 spec,不以计划代替设计。
- 计划评审通过 ≠ 自动开始实施;实施开始须用户明确解除暂停。
