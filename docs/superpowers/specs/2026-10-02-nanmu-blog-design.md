# nanmu-blog 设计文档

> 状态(2026-10-07):M0 全部验收通过,tag `m0`→cb6898a;M1 详细设计与27任务实施计划已通过评审。M1 Task 0–24 已实现(330 测试),审计/核验/复核轮修复完成;Task 25 部署对接完成且经同日审计修正(快照方案撤回→mode=ro 直读+E2 权限缺口报告;tokenizer 官方件锚定;校准 CLI 补齐;详见 Task 25 交接顶部审计更正块),引擎已部署 timer 未启用、零付费验证通过;上游只读存权限缺口待用户裁决。M2/M3尚未实现,Task 26 真实校准须当次授权。接手见 [Task 25 交接](../../sessions/2026-10-07-task25-deploy.md)。
> 日期:2026-10-02
> 路径:Architectural(brainstorming → spec → writing-plans → 实施)

---

## 1. 背景与定位

### 1.1 两个前项目与外部参考的结论

| 项目 | 结局 | 对本项目的输入 |
|------|------|----------------|
| nanmuli-blog(2026-04~06,已废弃) | 12.5 周烂尾,死因"开始设计太多导致后期无法进行" | 反面教材:范围铁律、伪需求清单(标签系统/自动优化闭环/质量评分趋势不做);正面资产:日报/AI 整理的产品想法、AesEncryptor/请求层等可参考实现 |
| topic-digest(2026-08-31 上线,生产运行中) | 9月720/720来自历史记录,本轮未复测 | 已验证的极简运维模式(SQLite + systemd timer + flock + 原子 symlink 发布);**继续在产,本项目的 AI 引擎直接读它的数据** |
| AIHOT(外部参考,热度不作为选型证据) | 生产级 AI 聚合框架 | 六大可搬模式:URL 判重、双次独立评分、单一公开投影、回执+预算熔断、industry 配置包、append-only 判断+人工覆盖;不整体引入(重装备+成本) |

### 1.2 定位(2026-10-02 与用户确认)

- **博客本体做简单版本**——git 写作流,静态站,无后台无数据库
- **项目重心是 AI 与博客的连接层**,两个方向:
  1. **AI 内容自动发布**:topic-digest 聚合数据 → AI 精选/评分/摘要 → 自动发布为博客"日报"栏目(借鉴 AIHOT 模式 + 旧博客日报想法)
  2. **博客内容 → AI 知识库**:个人文章 + AI 精选内容向量化 → RAG 问答/搜索(先自用)
- 部署:同服务器(123.56.223.97,环境见 server-environment.md)+ apex 域名 `nanmu.xyz` 走 Caddy(2026-10-04 已接管上线)
- 设计参考:AIHOT 的设计模式 + 旧博客(nanmuli-blog)的产品想法,轻量实现

### 1.3 默认决策(用户未反对即生效,均可推翻)

| 决策点 | 默认值 |
|--------|--------|
| 子域名 | 直接用 apex `nanmu.xyz`(2026-10-04 用户拍板,替代原默认 `blog.nanmu.xyz`;apex A 记录已指向服务器,原 Caddy 块为指向 127.0.0.1:3000 的死转发) |
| AI 内容形态 | 每日一期日报(延续旧博客想法) |
| RAG 使用者 | 仅自己(basicauth 保护) |
| LLM 提供商 | DeepSeek 为主(兼容端点),Qwen 备选;具体 model ID/计价在 M1 启动核查,budget.md 保存快照 |

## 2. 设计原则(铁律)

1. **范围是生死线**(nanmuli-blog 头号教训):每个里程碑必须独立可发布,不欠债进下一个
2. **博客本体永远不为 AI 功能加复杂度**:AI 挂了博客照常在线
3. **AI 引擎独立进程独立数据库**:engine 崩溃不影响博客,反之亦然
4. **topic-digest 保持现状不动**:本项目只读它的 SQLite(同机文件只读),不改它
5. **付费请求先记回执再消费 + 三级次数限制与月/期金额预占**,全部付费LLM/embedding月预算红线 **¥50**
6. **页面永不调模型**:读者打开页面只读预生成内容
7. **AI 生成内容必须标注**:digest 栏目页脚/文件头注明 AI 生成,与个人文章视觉区分
8. **文档随代码走**:设计变更先改文档,长期决策写ADR;修改型会话结束写交接,只读讨论不强制写盘

## 3. 总体架构

架构图与故障边界见 [architecture.md](../../architecture.md)。设计采用静态发布、引擎写入和受保护问答三个运行边界,通过版本化内容与可重建索引衔接。

数据流三句话:
1. **写作流**:人写 markdown → git push → hook 构建 → 静态发布
2. **AI 流**:engine 定时读 topic-digest 数据 → 评分精选 → 摘要 → 产出 digest markdown + git commit/push → 同一构建链 → 线上版本确认
3. **RAG 流**:engine 对已发布内容建向量索引 → RAG API 供问答

## 4. 博客本体(site,M0)

- **Astro 5**,零客户端 JS,明暗主题跟随系统(topic-digest 同款审美)
- 内容模型(content collections):
  - `posts/`——个人文章,手写,frontmatter: title/pubDate/tags/draft
  - `digest/`——AI 日报,程序生成,frontmatter 额外带 `generated: true`、`ai_model`、`cost_cny`、`cost_pending` 等溯源字段
  - `about`——关于页,`src/pages/about.astro` 普通页面,不进 collection
- 页面:首页(文章+日报双栏或单列)、`/posts/*`、`/digest/*`、`/about`、RSS(个人文章一条、日报一条)
- 无管理后台:git 即 CMS

### 4.1 混合内容组织(Astro 5 Content Layer,基础构建已验证;路径边界待Task8a补验)

- 配置文件为 `src/content.config.ts`(Astro 5 起不再用 `src/content/config.ts`);两个独立 collection = 独立目录 + 独立 schema,手写与生成天然隔离:
  ```ts
  import { defineCollection, z } from 'astro:content';
  import { glob } from 'astro/loaders';

  const posts = defineCollection({
    loader: glob({ pattern: '**/*.md', base: './src/content/posts' }),
    schema: z.object({
      title: z.string().trim().min(1), pubDate: z.coerce.date(),
      tags: z.array(z.string()).default([]), draft: z.boolean().default(false),
    }),
  });

  const digest = defineCollection({
    loader: glob({ pattern: '**/*.md', base: './src/content/digest' }),
    schema: z.object({
      date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine((value) => Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value, '日期必须是有效的YYYY-MM-DD'), generated: z.literal(true),
      ai_model: z.string().trim().min(1), entry_count: z.number().int().nonnegative(), cost_cny: z.number().finite().nonnegative(), cost_pending: z.boolean().default(false),
    }),
  });

  export const collections = { posts, digest };
  ```
- **cost_pending 字段契约(2026-10-05 M1 设计同步;区分两层)**:**待实施契约**=如上 schema——该期存在未决预占时为 `true`;新生成日报显式写出布尔值,`default(false)` 仅为旧文件兼容;核清时数字、标志与正文标注一起经正常内容提交更新(三约束见 [digest-design.md](../../engine/digest-design.md) §2)。**当前 site 实现**尚未包含此键与消费代码(列表/详情现仅显示 `cost_cny`),M1 实施许可后随 engine 写入一起落码;本文与 M0 plan 的 schema 示例保持一致(check_docs contracts),不代表 M0 已实施该字段。
- 生成内容由 engine落盘 + commit/push触发构建(build 开始时文件已存在)——构建确定性、可回滚、离线可复现;**绝不在 build 内调 LLM**(铁律 6);`.astro/` 数据存储目录 gitignore;M0 临时工作目录构建不承诺跨构建持久化
- 分页分开:`/posts/[...page]` 与 `/digest/[...page]` 各自 `paginate(getCollection(...))`;RSS 分开:`/rss.xml`(个人文章)与 `/digest.xml`(日报)两个 endpoint
- 路径与展示约定:posts单层英文短横线文件名,不能纯数字;digest文件名必须与date一致。日期显示固定Asia/Shanghai,同日期按id稳定排序。详细写作操作见 [写作指南](../../writing.md)。
- 两个collection均禁止frontmatter自定义`slug`(即使与文件名相同)。校验原始文件相对路径与最终id,不能只检查glob处理后的id;posts文件主名须匹配`[a-z0-9]+(-[a-z0-9]+)*`且非纯数字,digest须为单层`YYYY-MM-DD.md`。原始路径不得先小写/slugify后再检查,重复id须在写入内容store前拒绝。已由M0 Task8a实施:schema `.strict()`入库前拒绝slug等未知键,源目录扫描按原始文件名校验并以文件数/条目数一致性拦截重复id;负例矩阵见[Task8a交接](../../sessions/2026-10-04-m0-task8a.md)。
- 本地持久缓存不能充当内容真相源。Astro5.18.2删除最后一篇digest后可能保留旧store;正式build/dev入口已接入可再生缓存自动清理(M0 Task8a,`prebuild`/`predev`),自动清理不替代产物核对——删除/改名/撤回/测试fixture清理后,仍按[质量门禁](../../development/quality-gates.md)重新验证不存在的详情、列表和RSS。生产每次archive新建工作目录;M1的持久工作副本也须遵守该验证契约。
- **schema 即契约**:digest frontmatter 不合法 → 构建失败 → 部署不发生——天然闸门;engine 的测试必须覆盖此 frontmatter 契约

## 5. AI 引擎(engine,M1)——项目重心

> 细节设计基于 AIHOT 操作级深挖结论(2026-10-02),轻量化适配单机 SQLite 场景。AIHOT 25 张表 → 本设计 8张表;M1单实例flock,账本短事务授权;M2并发需同一账本事务保护。

### 5.1 形态
- Python 3.11 venv + SQLite(WAL)+ systemd timer + flock(整套 topic-digest 已验证运维模式)
- 目录:`engine/`(与 site/ 同 repo,monorepo 但边界清晰:engine负责产出markdown并在提交前调用既有verify做校验;构建发布仍由独立hook执行)

### 5.2 管线(每日一期,总流程)
```
collect   读 topic-digest SQLite 只读(item JOIN source,fetched_utc近48h;字段已实读源码核实:
          item.id/source_id/url_hash/url/title/published_utc/fetched_utc/content_text/status,
          source.id/name/weight/enabled;cluster/cluster_member 已用于单条目聚类,
          item 正常状态含 fresh/clustered;排除 dropped,不依赖上游聚类表或 pick/daily)
   ↓
判重      identity_key归一(借鉴AIHOT,本项目边界和固定样例见engine/design.md):
          记住原始scheme后统一https、host小写、去www/原始默认端口/fragment、剩余参数排序、去非根pathname尾斜杠,
          路径大小写与非黑名单业务参数保留;追踪参数黑名单定稿+微信四参特判(固定顺序) → entry表INSERT OR IGNORE
   ↓
预筛      本地规则零成本:标题关键词黑名单、死源/空文本排除、已用identity_key排除;按调用与金额额度限制候选
   ↓
双次评分   同一 prompt 独立调用 2 次(0-100),回执 attemptTag=score-1/score-2
          入选判据:score_1 + score_2 ≥ 2 × threshold(tier 分级门槛)
          展示分数:floor((score_1+score_2)/2)  ← "和判均显"(AIHOT 模式)
   ↓
摘要写作   仅对入选条目:中文标题(答案先行)/一句话摘要/推荐理由/标签
          防幻觉规则:不写来源没提的公司/数字;题文不符条目评分 ≤30 自然拦截
   ↓
组装      每日一期 digest markdown(按分数排序,分板块)
          frontmatter: date/generated: true/ai_model/entry_count/cost_cny 溯源
   ↓
发布      专用工作副本 git add + commit + push → bare repo hook;确认线上版本与日报后才 published
   ↓
记账      每次调用立即落回执/尝试/费用;即使整期失败也入账,期末只做汇总
```

### 5.3 数据模型(engine SQLite,12 表 DDL 要点;2026-10-05 单元设计定稿+联合核验修正轮:issue_freeze/summary/notify_sent/engine_meta 与各表扩展列)

```sql
-- 候选条目(topic-digest 条目的快照,判重后)
CREATE TABLE entry (
  id INTEGER PRIMARY KEY,
  identity_key TEXT NOT NULL UNIQUE,      -- url:{归一URL} 判重键
  url TEXT NOT NULL, title TEXT NOT NULL,
  source_name TEXT NOT NULL, source_tier TEXT NOT NULL DEFAULT 'T2',  -- T1/T2
  published_utc TEXT, discovered_utc TEXT NOT NULL, -- discovered来自上游fetched_utc
  content_text TEXT,                       -- 提取正文(来自 topic-digest)
  status TEXT NOT NULL DEFAULT 'pending'   -- pending/scored/selected/rejected/used
    CHECK(status IN ('pending','scored','selected','rejected','used')),
  claim_issue TEXT                         -- 占用归属:选中该条的未完成期issue_date;置selected同事务写,
                                           -- 确认published置used时清空,放弃失败期人工释放时清空(单元三定稿)
);
CREATE INDEX idx_entry_discovered ON entry(discovered_utc DESC);

-- 逻辑回执(每个请求身份一条;每次网络尝试另写receipt_attempt)
CREATE TABLE receipt (
  id INTEGER PRIMARY KEY,
  logical_key TEXT NOT NULL UNIQUE,        -- provider/endpoint/purpose/model/request_hash/attemptTag
  provider TEXT NOT NULL, endpoint TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  service TEXT NOT NULL,                   -- llm
  purpose TEXT NOT NULL,                   -- score/understand/summarize
  model TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'   -- pending/received/completed/failed/unknown
    CHECK(status IN ('pending','received','completed','failed','unknown')),
  request_digest TEXT,                     -- prompt版本/内容hash/模型参数的请求身份,不含 key
  unknown_retry_used INTEGER NOT NULL DEFAULT 0, -- 持久化一次自动放行标志
  response_json TEXT, usage_json TEXT,     -- tokens 等供业务复用;逐次费用在 receipt_attempt
  cost_cny REAL,                           -- 逻辑回执费用展示投影;逐次结算/未决以receipt_attempt为准
  attempts INTEGER NOT NULL DEFAULT 0,     -- 派生计数;窗口与金额以 receipt_attempt 为准
  created_utc TEXT NOT NULL, completed_utc TEXT
);
CREATE INDEX idx_receipt_open ON receipt(status) WHERE status IN ('pending','unknown');

-- 每次网络尝试单独记录,用于滑动窗口与金额预占(原设计实为7表,本表补成8表)
CREATE TABLE receipt_attempt (
  id INTEGER PRIMARY KEY,
  receipt_id INTEGER NOT NULL REFERENCES receipt(id),
  attempt_no INTEGER NOT NULL,
  issue_date TEXT,                         -- 日报归属;M2问答可空
  started_utc TEXT NOT NULL,               -- 此次尝试时间,不是逻辑回执创建时间
  status TEXT NOT NULL CHECK(status IN ('pending','received','unknown','failed')),
  attempt_origin TEXT NOT NULL
    CHECK(attempt_origin IN ('initial','retry','unknown_retry')),
                                           -- 授权来源,预占事务写入(第三轮核验定稿):
                                           -- initial=该logical_key首个attempt;retry=普通重试通道;
                                           -- unknown_retry=unknown专属额外名额通道(与receipt.unknown_retry_used
                                           -- 同事务双写,判定读标志、审计按行重算)
  error_class TEXT CHECK(error_class IN ('no_retry','retryable','unknown') OR error_class IS NULL),
                                           -- 规范化错误类别,失败/unknown状态更新同事务写入(成功路径留NULL)。
                                           -- 映射(design.md错误矩阵):no_retry={E1.request,E4.terminal,E5.balance};
                                           -- retryable={E3.http,E4.parse};unknown={E3.unknown}。
                                           -- 重启后再发送判定读取本列——400(no_retry)与503(retryable)
                                           -- 同为failed+未核清时靠它区分,仅status与计数不够(第三轮反例)
  fail_detail_json TEXT,                   -- 受约束失败明细:{http_status:int?,matrix_code:"E3.http",
                                           -- message:截断摘要};与error_class同事务写入,诊断与审计用
  reserved_micro_cny INTEGER NOT NULL CHECK(reserved_micro_cny >= 0),
  actual_micro_cny INTEGER CHECK(actual_micro_cny >= 0),
  usage_json TEXT, pricing_version TEXT NOT NULL,
  reconcile_json TEXT,                     -- 核清证据:证据类型/账单关联标识/核查时间/依据说明;
                                           -- 与actual_micro_cny同一UPDATE事务写入(单元二定稿,不留给plan)
  UNIQUE(receipt_id, attempt_no)
);
CREATE INDEX idx_attempt_started ON receipt_attempt(started_utc);

-- 三级预算(次数限制;行缺失=配置错误,拒绝付费;任一档 ≤0 = 立即停用)
CREATE TABLE budget (
  service TEXT PRIMARY KEY,
  per_minute INTEGER NOT NULL, per_hour INTEGER NOT NULL, per_day INTEGER NOT NULL
);

-- 评分记录(append-only:换模型/换 prompt 版本只增不改,历史可追溯)
CREATE TABLE analysis (
  id INTEGER PRIMARY KEY,
  entry_id INTEGER NOT NULL REFERENCES entry(id),
  prompt_version TEXT NOT NULL,            -- prompt 内容哈希
  model TEXT NOT NULL,
  score_1 INTEGER, score_2 INTEGER,        -- 两次独立分数
  selected INTEGER NOT NULL DEFAULT 0,     -- 和 ≥ 2×threshold
  receipt_ids TEXT NOT NULL,               -- JSON [id,...] 成本溯源
  created_utc TEXT NOT NULL
);
CREATE INDEX idx_analysis_entry ON analysis(entry_id, id DESC);

-- 人工覆盖(优先于评分判断,不绕过来源/输入安全/预算限制)
CREATE TABLE override (
  identity_key TEXT PRIMARY KEY,
  action TEXT NOT NULL CHECK(action IN ('force_include','exclude')),
  reason TEXT, created_utc TEXT NOT NULL
);

-- 每期日报
CREATE TABLE digest_issue (
  issue_date TEXT NOT NULL UNIQUE,         -- YYYY-MM-DD
  entry_ids TEXT NOT NULL DEFAULT '[]',    -- JSON数组;读取失败时尚无入选条目
  markdown_path TEXT,                      -- 未产出即失败时可空;draft/submitted/published必须有路径
  git_commit TEXT,                         -- commit成功即回填(仍处draft),push后置submitted
  content_sha256 TEXT,                     -- 内容身份=文件字节sha256,draft落盘同事务写入首值;
                                           -- 语义=当前已确认线上版本:线上确认类操作(纠错/重新上线)确认时
                                           -- UPDATE为该操作target_sha256,原始与历史经ops_json追溯(单元四)
  ops_json TEXT,                           -- 内容操作记录(单元四第二轮核验定稿):受约束JSON数组append-only,
                                           -- 每项{seq,op:withdraw|relist|relist_corrected|correct,target_sha256,
                                           -- stages:{commit?,pushed?,confirmed_utc?}};操作开始(写/删文件前)即
                                           -- append未完成项=待执行目标版本持久化;各阶段补记;线上确认置
                                           -- confirmed_utc。当前可见状态=最新confirmed项的op类型(非列组合)
  cost_cny REAL NOT NULL DEFAULT 0,        -- 仅展示/汇总;授权用receipt_attempt整数微元
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','submitted','published','failed')),
  created_utc TEXT NOT NULL,
  fail_reason TEXT,                        -- 生成路径失败原因(E2/E6子类/no_candidates/zero_qualified;单元五)
  updated_utc TEXT,                        -- 状态最近变更时间(恢复窗口判定)
  last_exit INTEGER,                       -- 最近一次运行退出码(status命令/通知判定)
  last_run_utc TEXT,                       -- 最近一次运行结束时间
  withdrawn_utc TEXT,                      -- 最近一次撤回确认事实:撤回提交线上确认后写入(单元四);再撤回时覆盖
  withdraw_commit TEXT,                    -- 最近一次撤回删除提交SHA
  relisted_utc TEXT,                       -- 最近一次重新上线确认事实(单元四);不参与状态判定
                                           -- (判定=ops_json最新confirmed op,withdrawn/relisted组合在
                                           -- "撤回→重上→再撤回"下会误判,2026-10-05第二轮核验用户实测)
  relist_commit TEXT,                      -- 最近一次重新上线提交SHA
  CHECK(status = 'failed' OR markdown_path IS NOT NULL)
);

-- 期候选冻结确认(2026-10-05 数据接入单元设计定稿,见 engine/units/data-ingestion.md)
-- collect 结束单事务写入;行存在且完整=冻结确认事件;半途中断=行不存在=未冻结
-- paused 三列由单元五定稿:冻结后全生命周期的期级暂停标志(生成中/draft/submitted/published均可叠加;
-- 冻结前无期概念无暂停需求;failed不自动重跑无需暂停)。置位/解除=独立UPDATE,留痕于paused_reason/paused_utc
CREATE TABLE issue_freeze (
  issue_date TEXT PRIMARY KEY,            -- YYYY-MM-DD;一期恰好一条,已存在则续跑不覆盖
  frozen_utc TEXT NOT NULL,               -- 确认写入时间(=事件发生时间)
  entry_count INTEGER NOT NULL CHECK(entry_count >= 0),  -- 允许 0(空集合是合法冻结结果)
  manifest_json TEXT NOT NULL,            -- 成员清单 JSON:identity_key/entry_id/url/title/source_name/
                                          -- source_tier/published_utc/discovered_utc/content_text/content_hash
  paused INTEGER NOT NULL DEFAULT 0 CHECK(paused IN (0,1)),
  paused_reason TEXT,
  paused_utc TEXT
);

-- 月度成本聚合(报表投影,从 receipt_attempt 聚合;不作调用授权依据)
CREATE TABLE api_usage (
  month TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
  tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,
  cost_cny REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (month, provider, model)
);

-- 摘要记录(2026-10-05 单元三定稿;与analysis对称的append-only,换prompt/模型只增不改)
-- 组装取该entry当前请求身份的最新行;同身份跨期复用,身份变化(正文/prompt/模型)后需新调用
CREATE TABLE summary (
  id INTEGER PRIMARY KEY,
  entry_id INTEGER NOT NULL REFERENCES entry(id),
  prompt_version TEXT NOT NULL,            -- understand prompt 内容哈希
  model TEXT NOT NULL,
  title_zh TEXT NOT NULL, summary TEXT NOT NULL, reason TEXT NOT NULL,
  tags_json TEXT,                          -- ≤3;M1 系统内部不展示(digest-design §2)
  receipt_ids TEXT NOT NULL,               -- JSON [id,...] 成本溯源
  created_utc TEXT NOT NULL
);
CREATE INDEX idx_summary_entry ON summary(entry_id, id DESC);

-- 通知发送记录(2026-10-05 单元五定稿+核验修正:同key UPSERT,不另起行——主键去重)
-- dedup_key=错误子类+issue_date / 月预警"warn-monthly:"+YYYY-MM / 配置错误类含配置hash
-- 重试成功=UPDATE本行result/sent_utc;主键防同期重复。崩溃承诺(2026-10-05第二轮收窄):发送成功
-- 但结果未持久化即崩溃→重启可能重复通知——不承诺外部精确一次,也不承诺任意重复崩溃下最多重复一次
CREATE TABLE notify_sent (
  dedup_key TEXT PRIMARY KEY,
  channel TEXT NOT NULL,
  sent_utc TEXT NOT NULL,
  result TEXT NOT NULL                     -- ok | fail:原因(重试后UPDATE本行)
);

-- 全局运行标志与校准记录(2026-10-05 核验修正轮定稿+第二轮修正恢复序列,第12表;单元五)
-- 键内容两类(第五轮引用对齐):①pay_paused——建库/初始化即写入默认0(键缺失不可能是正常新库
-- 状态)。闸门读法=仅显式0放行;=1或键缺失(违规裸恢复/库损坏异常态)均拒绝一切新增付费attempt
-- (防止恢复旧库后按丢失的receipt重复授权重发),复用/结算/只读不受限。置位来源两方=单元五
-- restore-backup 步骤②与单元二对账硬失败(其规则2/8/11;同一闸门同一解除协议:人工核对后显式
-- 置0)。恢复必须经restore-backup命令,序列=恢复到待启用副本→副本内置1→读回校验→原子切换为
-- 活动库(不变量:切换完成⇔标志已先持久化,消除恢复操作自身中断窗口;先恢复后置位的顺序禁止)。
-- 裸文件恢复属runbook违规(status检测:活动库无该键即提示核对)。②校准记录——绑定 {model,
-- tokenizer资源与版本,消息计数方式,校准系数,样本对账结果,判定时刻},任一变化即失效须重校准,
-- 契约全文=units/model-calls.md §3 规则11,不在本注释展开。
CREATE TABLE engine_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_utc TEXT NOT NULL
);

-- (M2 追加)向量数据不入本库:独立 rag.db(vec0 虚拟表 float[1024] + 溯源列),
-- 与 engine.db 解耦,可从已发布 Markdown 重建(见 §6)
```

### 5.3.1 恢复数据的实施约束

上述DDL为核心模型,不是M1最终迁移工件。无Markdown可记failed,其他期状态必须有路径。期状态以生成/远端接收/线上确认分层;entry仅在确认published后标used。人工撤回需要可持久化的暂停重试标志,不能靠一次性口头操作防重发。**期冻结存储已定位**(2026-10-05,数据接入与候选管理单元):issue_freeze 行存在=冻结确认,manifest 含每成员输入版本快照,旧期续跑读 manifest 而不读 entry 现值;"生成中(已冻结)"由该行承载,digest_issue 行仅在产出产物或记失败时创建——详见 [units/data-ingestion.md](../../engine/units/data-ingestion.md)。

M1计划必须给出失败阶段/原因、状态更新时间、产物内容身份、重试暂停、普通/unknown重试计数、通知去重、对账证据的字段或本项目状态文件映射,并同步DDL后才写代码。可复用现有表/JSON字段,不预设新增服务。参照[管线恢复](../../engine/pipeline.md)与[账本恢复](../../engine/budget.md),覆盖Git成功与DB落状态之间的中断窗口。**上述映射已于 2026-10-05 五单元详细设计定稿(同日两轮核验修正补齐)**:失败原因/更新时间/退出码/撤回事实/重新上线事实→digest_issue 扩列;**产物内容身份→digest_issue.content_sha256(draft 落盘同事务写入;第二轮起语义=当前已确认线上版本,随确认类操作 UPDATE,历史经 ops_json 追溯)+内容操作记录→digest_issue.ops_json(操作开始即持久化目标版本与阶段;当前可见状态=最新 confirmed op)**;重试暂停→issue_freeze.paused;**重试判定持久化(第三轮核验定稿;第四轮修正授权语义)=receipt_attempt 三列**:`attempt_origin`(授权来源,预占事务写,**写入后不可改写**——unknown 通道重试返回 503 的行保持 origin='unknown_retry',不因返回类型变成 'retry')、`error_class`(规范化错误类别 no_retry/retryable/unknown,失败或 unknown 状态更新同事务写,映射自错误矩阵 E1.request/E4.terminal/E5.balance→no_retry,E3.http/E4.parse→retryable,E3.unknown→unknown)、`fail_detail_json`(HTTP 状态+矩阵子类+摘要,同事务写)。**名额统计唯一口径(第四轮定稿:名额按授权消耗,不随响应结果改写)**:普通尝试已用数=该 logical_key 中 `attempt_origin IN ('initial','retry')` 的行数(**不按 error_class 过滤**——每次授权即消耗一个名额,无论返回什么;上限 max_attempts,即首次+max_attempts−1 次重试);unknown 专属=receipt.unknown_retry_used 标志(与 `attempt_origin='unknown_retry'` 行存在同事务双写,判定读标志、审计按行重算);硬上限=该 logical_key 总行数<max_attempts+1;**error_class 的职责是决定能否再发送与走哪个通道**(最近失败类别 no_retry→拒绝、计数未满也不调用;retryable→普通通道;unknown→满足等待条件走 unknown 通道),不参与名额计数(score-1/score-2/understand 各自序列,同身份耗尽后重启不重置、不重获额度;能否再发送=再发送三条件,普通与 unknown 名额不互借);通知去重/发送结果→notify_sent 表(同 key UPSERT);对账证据→receipt_attempt.reconcile_json(与 actual 同事务);摘要业务结果→summary 表;占用归属→entry.claim_issue;**付费暂停→engine_meta.pay_paused(第 12 表;仅显式 0 放行、键缺失同拒;置位来源=restore-backup 步骤②与单元二对账硬失败——usage 超计数/供应商实付>预占,**停新增=持久化置位并记录原因,重启继续拒绝,人工核对后显式解除**,复用/结算/只读照常;恢复=先在副本置位校验后切换活动库;校准通道契约=单元二规则 11:purpose='calibration' 是"校准未完成不出网"的唯一例外,走完整闸门,月预算与窗口照常适用,校准记录绑定模型/tokenizer 资源与版本/计数方式/系数,配置变化即失效)**。详见 engine/units/ 各单元文档。

公开cost_cny聚合该期全部attempt(含失败候选/重试),每次取实付或未决预占;含未决时页面/正文明确标保守上界。**cost_pending 布尔与 cost_cny 出自同一时点、同一期费用快照;未决判定覆盖所有 actual 未核清 attempt(不限于 status=unknown);新生成日报显式写出布尔值;核清时数字、标志与正文标注一起更新**(三约束全文见 [digest-design.md](../../engine/digest-design.md) §2,site 消费代码待 M1 实施许可)。跨期复用与跨月预占计算以budget.md为准。

### 5.4 回执状态机与预算熔断(借鉴AIHOT,按本项目契约实现)

**状态机**:
```
pending → received → completed   (正常成功:响应先落库再做业务写,崩溃可复用已付费结果)
pending → unknown                (超时/崩溃等结果不明,预占费用保留)
unknown → failed                 (≥30min 可重试一次,持久化标志;旧尝试费用不释放)
received → failed                (响应不可解析)
failed → pending                 (重试:attempts+1,先复查预算)
status ∈ {received, completed}   (同请求身份复用,零网络调用;不可解析响应不能无限循环)
```

**幂等键**:`provider:endpoint:purpose:model:request_hash:attemptTag`。request_hash 覆盖 identity_key、输入内容 hash、prompt 内容 hash、模型参数与输出上限;score-1/score-2 分开。它防本地重复调度,不保证供应商端 exactly-once。未知结果重试仍可能再次收费。

上图是逻辑回执的恢复路径,旧attempt仍保留其unknown状态和费用,不能因新attempt重试而改写成免费失败。普通HTTP/解析失败与unknown的独立限次、累计上限和HTTP请求体以[engine/design.md](../../engine/design.md)为实施契约;收到错误HTTP响应不等于结果未知。

**三级预算**(单进程下用 flock + 计数查询替代 advisory lock):
- 统计口径:按 `receipt_attempt.started_utc` 计近 1min / 1h / 24h 尝试行数;每次重试另计,复用响应不计。检查与写预占在同一短事务,提交后再访问网络。
- 分钟额度用于节流,按最早尝试到期时间有界等待,整期设超时;小时/日额度或金额不足则停止新增增强。预筛时留出摘要与重试额度,已有合格条目可发布,没有合格条目记failed。**任一档 ≤0 = 立即停用**。
- 初始次数值:per_minute=10 / per_hour=100 / per_day=400。日均 116 条全量双评分会超过小时额度,候选规模须在 M1 实测后配置。
- 次数配置接受整数,≤0是合法停用值,只禁止新增付费attempt;仍可复用响应、结算和发布已有合格产物。缺字段/错误类型属于配置错误,不能与停用混为一谈。已发出的请求仍记账,配置在下一次预算授权前生效,不等到下一期才停用。
- **月金额 ¥50、单期 ¥1 是独立限制**:调用前以输入上界、输出 token 上限、已核实的保守单价预占,已结算+未决预占+新请求不得超限。金额用整数微元(1元=1,000,000微元),显示才转元;月按 Asia/Shanghai 自然月,所有未决预占跨月保留直至核清。¥40 去重预警。详见 budget.md 与 ADR-0009。

### 5.5 评分标准(prompt 设计,AIHOT selection-score.md 结构移植)

- **输入安全边界**:输入材料是不可信数据非指令,拒绝注入
- **不给模型的信息**:tier、信源名、历史分数、门槛(防锚定)
- **五轴内步**(不输出):信息价值/新颖度/可信度/实用度/兴趣相关,各 0-10,按条目类型加权(类型:模型发布/产品发布/工具教程/研究论文/行业事件/观点分析)
- **两清单**:"必须正常评价"(重大发布/开放性变化/可复用方法/意外事实)与"必须压住"(无细节的 PR/小版本/营销课程/纯预告/轶事/跑分帖)
- **题文不符封顶 ≤30**;不可核实主张按"有人声称 X"弱化评价
- **输出**:仅 `{"attentionScore": 0-100}`,无解释
- prompt 放配置包,版本=内容哈希,写进 analysis.prompt_version

### 5.6 配置包(编辑策略与代码解耦,AIHOT industry/ 模式)

```
engine/config/
  ├── sources.yaml        # tier映射见selection.md;机器之心/36氪按历史记录暂排除,上线前核查
  ├── budget.yaml         # 调用/金额限额、输入输出上限、价目版本;不含密钥
  ├── selection.yaml      # 门槛 {T1: 60, T2: 75}、每期条目数上限、板块划分
  └── prompts/            # score.md / understand.md(摘要写作)/ rules-anti-hallucination.md
```

字段格式、校验与加载契约见 [engine/design.md](../../engine/design.md);配置校验失败=拒绝任何付费调用。

### 5.7 调度与运维

- `nanmu-blog-engine.timer`:每日 08:30(Asia/Shanghai,暂沿用本机裸时间策略,先验系统时区及next elapse;不归因为上游239不支持)+ RandomizedDelaySec=300 + Persistent=true(missed 补跑一次)
- flock 使用本项目用户可写锁目录;若用 `/run/lock` 须预建文件并验证属主/权限,不能假定普通用户可写
- 失败隔离:单条目失败不挂整期;LLM 全挂 → 该期不生成(digest_issue 记 failed),博客照常在线
- OnFailure 接入本项目 `/etc/nanmu-blog.env`;不修改 topic-digest 的 env/units。无日报或读取失败记非成功并退出非零,通知脚本按连续2期/预算预警去重;崩溃与配置错误立即告警。

## 6. RAG 知识库(M2)

选型方向已定,版本/价格/目标机能力在 M2 启动时实测,不把调研估值当验收:

- **向量存储:sqlite-vec**(具体版本在 M2 核实可安装包及兼容性后锁定;官方 pre-v1,不沿用未经复核的 0.1.9 断言)
  - 当前按万级向量评估 brute-force KNN;响应和内存是待测指标,不承诺毫秒级/50MB
  - 暂不引入额外向量数据库服务;LanceDB/Chroma 的具体资源开销未在本机复测,规模变化后再评估
  - SQLite写入用短事务串行授权:**engine timer 写索引,常驻 RAG API 对 rag.db 只读**;API 的付费调用仍经统一账本写 engine.db,用短事务做并发预算预占
  - 向量以紧凑二进制存储(float32 `struct.pack`);**embedding 身份 = model+dimension+distance+normalization 钉成整体**(PowerContext EmbeddingProfile 模式),每条向量绑定被嵌入内容的 hash——换模型/内容变更可机器检测陈旧向量;**Markdown 是语料真相源,chunk 是规范化语料投影,向量/FTS 是 chunk 的可重建索引**,提供一键 rebuild
  - 其他向量扩展不在当前范围,不维护未经核实的版本/生态断言
- **embedding**:优先验证 SiliconFlow `BAAI/bge-m3`(预期1024维),阿里百炼 embedding 为备选。免费额度、model ID、维数、限速与计价均须在 M2 实测;切换维数时重建 schema/索引,不宣称无成本平滑切换。付费 embedding 同样计入月预算。
- **架构**:
  ```
  engine(timer)→ 增量索引(已发布且 draft=false 的 posts + 已发布 digest 精选条目)→ rag.db(vec0 虚拟表 float[1024])
  FastAPI /ask(仅自用,basicauth)→ 向量检索 top-k=8 → DeepSeek 生成答案(必须附来源链接)
  Caddy(rag 子域名或 apex 站块 /api/* 反代)→ localhost:8787
  ```
- **检索设计(双通道混合,PowerContext 模式)**:
  - FTS5(bm25)+ 向量两条通道独立检索,融合去重后取 top-k=8;每个命中标注 `matched_by: fts|vector|both`——检索质量可观测
  - **embedding 端点失败自动降级纯 FTS**;检索无充分证据则明确无法回答,LLM 不可用只返回来源片段
  - chunk 带 `corpus` 列(posts/digest)按语料分区;注入 prompt 的检索结果设字节预算上限
- 自用`/ask`允许明确发起模型请求,它不嵌入公开静态博客浏览流程;“页面永不调模型”约束公开内容访问,不否定独立受保护的M2 API。
- 曾评估 OceanBase PowerContext 整体采用,结论**不采用**:它解决 agent 跨会话交接而非知识库问答,部署与版本维护负担超出当前需要(原调研内存/版本节奏未在目标机复测);且其检索底座恰是 FTS5+sqlite-vec 同款积木,反向验证本选型
- 验收(M2):固定个人问题集抽查,中文短词/中英混合/无答案问题都覆盖;记录样本规模、缓存条件和端到端 p95 <5s。答案必须引用实际检索来源,无证据拒答。补文章删除、改稿、draft变化后的索引同步和可重建验证;中文 FTS tokenizer 先在目标 Python SQLite 探针中验证。

### 6.1 M2计划需要确定的索引一致性

语料读取线上release.txt所指SHA的Git Markdown,不读未上线工作区。索引记录corpus SHA与EmbeddingProfile;同一批次的chunk/FTS/vector成功后才对外生效,失败保留上个可用版本。构建期间又有新发布时,下次按新SHA追赶,不能把混合版本标为最新。删除、转draft和整站回滚都按目标SHA重建/失效处理。

M2计划确定事务更新或临时库切换的具体方案,验证API读者重开连接与失败恢复,不在M0新增实现。p95从请求进入到完整答案/降级结果返回测量,固定问题集、并发度和冷/热缓存条件分别记录,不能只测向量检索耗时。

## 7. 部署与运维

- 服务器:123.56.223.97(Alinux 3,systemd 239,Caddy 80/443 已有,1.8G 内存 + 2G swap)
- **域名与备案前置核查**:此前设计期的概括性转述不作为上线许可证明;按[环境文档](../../context/server-environment.md)分别核对域名归属、ICP/接入与公安备案适用要求,记录官方出处和账户适用结论
- **Caddy**(注意 v2.8+ 指令名是 `basic_auth`,不是旧名 `basicauth`):
  ```caddyfile
  nanmu.xyz {
      root * /var/www/nanmu-blog/current/dist
      encode gzip
      file_server
      handle_errors {
          rewrite * /404.html
          file_server
      }
  }
  rag.nanmu.xyz {            # M2;或并入 blog 站块用 handle_path /api/* 反代,二选一
      basic_auth {
          admin <bcrypt-hash>   # `caddy hash-password` 预生成;凭据不落盘
      }
      reverse_proxy localhost:8787
  }
  ```
  404 用 `handle_errors`(返回真 404 状态码;`try_files` 回退是软 404,不采用)。
  **reload 前必须 `caddy validate`**——坏配置会连累同机的 skills.nanmu.xyz。
  `basic_auth` 默认在 `reverse_proxy` 之前执行,自动覆盖被代理上游;依赖 Caddy 为公网域名自动签 TLS
- **git push 自动构建**(bare repo + post-receive;topic-digest 已验证模式 + 调研补强两个坑):
  - 只部署 `refs/heads/main`;忽略删分支(null SHA)
  - post-receive 用 nohup 后台启动并重定向 stdin/stdout/stderr;锁等待最长900秒,构建最长900秒;后到请求等待锁后读取最新 main,超时/失败留日志,不静默跳过(ADR-0009)
  - deploy:锁内解析 main SHA → `git archive <sha>` 到独立临时目录 → `npm ci --cache` → `npm run verify` → 带 `.complete` 的完整 release → 切 current。部分 dist 不能当成功缓存;输出 `/release.txt` 用于核对线上 SHA
  - **原子切换必须 `mv -T`**(先建 `current.tmp` 软链再 rename);`ln -f` 存在 unlink 窗口,不可用;保留最近 N 版目录供回滚
  - 权限:安装时由sudo准备本项目路径,日常构建由nanmu写releases;mktemp的700目录在发布前显式改为755,静态产物a+rX,Caddy只读。以实际Caddy用户验证父目录遍历与文件读取。
  - 内存:topic-digest 同机实测 astro build 峰值 241MB,该值仅为上游2026-08-31历史测量;本项目build峰值与并发内存需另测
- 新增 systemd units:
  - M0 构建使用上述 hook+nohup,不额外承诺尚未提供工件的 build.service
  - `nanmu-blog-engine.timer`:每日 08:30 + RandomizedDelaySec=300 + Persistent=true(missed 补跑一次)
  - `nanmu-blog-rag.service`(M2,常驻,MemoryMax=200M)
- 备份:engine SQLite 纳入每日备份(复用 topic-digest 的 `conn.backup()` Online Backup 模式,保留 30 天);本项目异地数据库备份仍待落实;不得借此修改topic-digest备份配置
- 监控:M0 构建文件日志+线上SHA核对;M1 systemd journal+本项目 OnFailure 通知,接入时做一次测试告警

## 8. 文档系统

```
nanmu-blog/
├── AGENTS.md                        # AI agent 项目说明书(第一天就有,AIHOT 模式)
├── README.md                        # 定位 + 快速上手 + 三个前项目结论链接
├── CLAUDE.md                        # 项目记忆(与 AGENTS.md 同口径)
├── scripts/check_docs.py            # 文档检查入口,不替代应用验证
├── docs/
│   ├── README.md                    # 文档索引
│   ├── context/                     # 项目背景与环境事实(新 agent 必读:三前项目故事/教训对照表/服务器事实/上游数据源/术语表)
│   ├── development/                 # agent 开发约束:工作流/编码规范/按活动门禁
│   ├── superpowers/specs/           # 设计文档(本文档)
│   ├── superpowers/plans/           # 实施计划(writing-plans 产物)
│   ├── writing.md                   # 写作、草稿、发布与撤回
│   ├── reviews/                     # 带日期的审查证据
│   ├── architecture.md              # 三件套架构与数据流(2026-10-02 已落盘)
│   ├── engine/pipeline.md           # 管线各阶段说明(已落盘,M1 实施基准)
│   ├── engine/design.md             # 模块/配置/请求/判重/错误与成本计算契约
│   ├── engine/selection.md          # 精选标准/门槛/调整记录(编辑策略文档)
│   ├── engine/budget.md             # 成本治理与月度成本记录
│   ├── engine/digest-design.md      # M1 日报功能详细设计(v3 已收口,第 3 步输入基线)
│   ├── engine/units/               # M1 五设计单元详细设计(第 3 步逐单元产出与评审)
│   ├── ops/deploy.md                # 部署准备手册已建立,Task8核对工件/Task9实测
│   ├── ops/runbook.md               # 巡检/回滚/故障处理
│   ├── sessions/                    # 开发会话交接记录(§8.1)
│   └── decisions/                   # ADR 架构决策记录(0001-0009 已落盘)
```

文档纪律:设计变更先改文档再改代码;每个里程碑的验收清单写入 plan;过期文档宁可删除不留误导(nanmuli-blog 教训)。

### 8.1 会话交接纪律(PowerContext 模式,针对 nanmuli-blog 头号死因)

nanmuli-blog 复盘的死因之一是跨会话上下文断层(9 月观测真空即此类)。本项目从第一天执行轻量交接纪律(纯 markdown,不引入工具):

- **交接记录** `docs/sessions/`:每次开发会话结束写一份(agent 生成),字段——
  - `objective` 本次目标;`state[]` 已完成事项,**每条附证据**(commit/测试/文件路径)
  - `disposition` continuable | blocked | complete;`next_action` 下一步
  - `omissions` 已知未验证/缺失项——**显式声明"我不知道什么"**(跨会话断层的主要来源)
- **声明分级**:陈述标注 [verified: 证据] 或 [declared];declared 不得伪装成有证据
- **接手检查**:先明确本轮目标并核对已有修改/暂存、分支与Git记录,再执行当前阶段适用验证,不运行尚不存在的应用命令。不符在新记录纠偏,不改写旧session;具体动作与失败分类由 [workflow](../../development/workflow.md)维护
- **范围与完成**:disposition以本轮objective为单位,next_action仅为接续建议,不自动授予外部操作权限。记录写作时HEAD、本轮与已有改动范围、验证结果及未验证边界;格式见 [交接模板](../../sessions/_template.md)
- **终态原则**:当前操作指南只写有效流程;ADR保留被否决方案和历史理由,新结论明确取代范围

## 9. 里程碑与验收标准

| 里程碑 | 内容 | 验收标准 | 量级 |
|--------|------|----------|------|
| **M0 博客上线** | Astro 站 + git 写作流 + 构建发布 + apex 域名(2026-10-04 由子域名改) | 手写一篇文章 push 后 3 分钟内线上可见;RSS 可订阅;明暗主题正常 | 1-2 天 |
| **M1 AI 引擎** | collect→评分→摘要→日报发布全链 + 成本治理 | 连续 3 天自动产出日报且入选质量可接受;单期成本 ≤¥1;熔断器注入测试通过;AI 内容有明确标注 | 3-5 天 |
| **M2 RAG** | 向量索引 + /ask API | 个人文章+日报可问答,检索相关性抽查合格;响应 < 5s | 2-3 天 |
| **M3 可选** | 周报/热度/更多 AIHOT 模式 | 按需定义 | — |

### 9.1 当前推进顺序与进入条件

用户价值优先:先能持续写作与订阅,再每天读到值得点开的日报,最后能找回已发布内容。上表量级是早期估算,不替代任务证据或形成交付期限。推进顺序如下,本节只定义阶段策略,M1/M2计划仍在各自启动时编写。

| 顺序 | 本阶段交付与开发策略 | 完成/进入下一步的条件 |
|------|----------------------|------------------------|
| M0 Task8a(已完成2026-10-04) | 修复原始路径/slug校验,构建/dev入口自动清可再生缓存;保留现有Astro/静态写作方案 | 正反例矩阵与verify已通过,证据见[sessions/2026-10-04-m0-task8a.md](../../sessions/2026-10-04-m0-task8a.md);当前进入Task9-10 |
| M0 Task9(已完成2026-10-04) | 按现有工件开通服务器、独立故障验收、Caddy接管apex域名 | 服务器开通/韧性实测5项/公网验证/常态发布计时13s(≤180s)通过,线上=`https://nanmu.xyz`,证据见[sessions/2026-10-04-m0-deploy.md](../../sessions/2026-10-04-m0-deploy.md);skills.nanmu.xyz 当日DNS记录意外消失待用户恢复;当前进入Task10 |
| M0 Task10 | 首篇真实文章和订阅、主题与回滚演练 | 正式域名上180秒发布指标复测与Task10逐项通过;获授权后发布m0,不以M1计划是否写好阻塞M0 |
| M1启动 | 先按[设计评审规范](../../development/design-review.md)完成五设计单元的详细设计与评审(以完整日报样例为起点),再核对线上上游只读访问、真实模型/价目/输入上界;然后实现config/db/ledger和mock客户端 | M0已验收;**五设计单元评审通过(阻塞问题解决)**;M1 plan经评审;费用单位、请求体、停用和重试边界有可执行测试,首次真实付费前预算闸门已验证。本文档与engine四文档是总体设计基线,单独不构成M1编码许可;设计评审与M1 plan评审通过是必要条件而非自动恢复实施的许可,实施开始须用户明确解除暂停 |
| M1交付 | collect/归一/预筛→双评分→摘要→安全模板→验证→提交/线上确认,先用小样本端到端贯通再扩大候选 | 连续3天自动产出、每天最多5条人工核验、单期≤¥1/月≤¥50;已收结果复用不再付费,unknown重试保留原费用并限次,撤回不自动重发;通知和备份恢复有证据 |
| M2启动与交付 | 读取已发布SHA的Markdown;先验证中文FTS与来源返回,再加向量、融合和受保护ask;复用统一预算闸门 | M1已验收并无阻塞缺口;M2 plan经评审;固定问题集的拒答/降级/删改/回滚/并发预算与端到端p95<5s验证 |
| M3 | 只保留有实际使用反馈支撑的候选想法 | 用户另行选择范围与验收前不实现 |

### 9.2 范围与调整策略

- 不新增管理后台、博客数据库、客户端脚本、队列服务或质量趋势平台;文章tags保持简单元数据。M1不做跨URL事件聚类、复杂排行和来源配额,先观察现有筛选样本。
- M1优先使用一期同一模型,先守住来源、费用、恢复与发布契约,再调prompt和门槛。正文不足则跳过,零合格项如实记失败,不为凑满15条放宽事实要求;失败期不影响旧站。
- M2先满足个人问答,不嵌入公开博客浏览链路。embedding不可用时FTS降级、证据不足时拒答;模型/索引选择由目标机探针和问题集决定,不提前增加服务。
- 调整依据来自首篇真实写作、日报人工抽样和固定问题集;只记录问题与对应修复,不建立新管理系统。阶段验收通过后推进,只回补影响当前交付的缺陷,不循环扩张文档审查范围。
- 文档、编码、部署与付费分别保持证据和授权边界。服务器/DNS前提缺失时继续独立本地工作,不能将未验收的M0写为已完成或用M1开发绕过阻塞。

## 10. 风险清单

| 风险 | 对策 |
|------|------|
| 范围蔓延(头号历史死因) | 里程碑铁律;M3 功能一律"记录想法不动工" |
| LLM 成本失控 | 回执+三级次数限制+月/期金额预占;日报 frontmatter 记成本可见 |
| 域名/DNS 异常 | 备案/解析/TLS均需部署时验证;DNS未通可本地/SSH隧道验收构建,不得占用上游8080或把临时入口算正式M0验收。2026-10-04实录:skills.nanmu.xyz 记录当日从可解析变 NXDOMAIN(非本项目变更所致),DNS层单点风险真实发生过,恢复需域名控制台操作 |
| 服务器内存(1.8G) | topic-digest 同机实测 astro build 峰值 241MB;RAG 常驻 MemoryMax=200M;swap 2G 已配 |
| AI 日报质量不可接受 | 双次评分+人工覆盖表;M1 验收含人工抽查;门槛可配置随时调 |
| topic-digest 变更破坏读取 | 只读 + 明确 schema 依赖清单;坏读取只影响当天日报 |
| SSH 免密部署路径不通(topic-digest 历史:remote 直连失败未诊断,退化 bundle) | Task 9 内置诊断清单;30 分钟不通降级 git bundle 同步并记录 omissions |
| Caddy 配置错误连累同机 skills.nanmu.xyz | reload 前强制 `caddy validate`;候选validate失败不覆盖运行配置;加载失败按deploy.md恢复备份并返回失败 |
| 开发机故障丢未推送提交(nanmuli-blog 601 行悬置教训) | M0后在有效发布授权与验证覆盖内push server main;否则交接明确未推送。bare repo是开发机代码副本,不替代数据库/凭据灾难恢复备份 |

## 11. 调研方向与实施前核查(方向确定不代表运行项已验证)

- [x] §4.1 Astro 混合内容:双 collection + glob loader + 分页/RSS 分开(Astro 5 官方文档验证)
- [x] §5 引擎详设:DDL 8 表 / 回执状态机 / 三级预算 / 评分 prompt 结构(AIHOT 操作级深挖移植)
- [x] §5.2 collect契约:2026-10-02复读上游schema与pipeline,确认JOIN键/fetched_utc/clustered状态;线上版本待M1验证
- [x] §6 选型方向 sqlite-vec + embedding + FTS;版本/免费额度/目标机性能待 M2 验证
- [x] §7 Caddy `basic_auth` + 子域名免单独备案(阿里云官方口径)+ post-receive 后台 flock 构建 + `mv -T` 原子切换(勘误 2026-10-04:域名改用apex后"子域名免备案"依据不再适用;apex备案状态未核实,见 server-environment.md 网络节)
- 参考项目补充:Horizon的先过滤后增强与环境变量引用用于设计;分类配额仅是可调运营方向,未经样本验证不能称已实现;open-aggregator 的"LLM 不可达→降级输出、站点保持在线"已吸收进 §5.7 失败隔离。他项目成本不可作为本项目预算依据;按本期候选、token上限与当前计价测算
- PowerContext(oceanbase):评估后**不采用**(问题域是 agent 会话交接而非知识库问答),搬走其最值钱的模式——§6 双通道混合检索 + matched_by 观测 + EmbeddingProfile + FTS 降级,§8.1 会话交接纪律(omissions/声明分级/接手检查,直击 nanmuli-blog 跨会话断层死因)

### M1 启动前核查清单(写 M1 plan 时先做,消除 [declared])

- [x] 对照 AIHOT `packages/backend/src/lib/url.ts` 定稿追踪参数黑名单与微信特判规则(2026-10-04 线上核实其生产实现;黑名单=utm_* 前缀+22 精确项,落 engine/design.md 判重规则节,§5.2 已同步)
- [x] 复核 DeepSeek 当期定价(2026-10-04:与 10-02 快照一致;新增思考模式默认开/关闭参数/JSON Output/错误码事实,落 budget.md 价目节与 design.md llm.py 调用契约)
- [ ] 确认服务器 topic-digest commit、DB路径、运行用户、只读WAL访问、fresh/clustered分布与正文覆盖率,回填 server-environment.md
- [ ] 确认服务器 node 版本与安装方式(M0 Task 9前置核查时记录,M1启动再核对是否变化)
- [ ] 用户申请/确认 LLM API key 与 SiliconFlow key(M2 前)可用,密钥只进服务器 env

---

## 附:变更记录

- 2026-10-05 第五轮核验:**4 组 P1 关闭,M1 实施计划通过评审**——阶段登记为"M1 详细设计与实施计划评审通过;待 M0 收尾及用户明确恢复实施"。通过结论的边界:tokenizer/费用上界/备份恢复/真实发布均未运行验收(实施验证任务在 plan [V1]/[V2]/Task 21/22/26),不解除实施暂停;"官方资源初始系数 1.0"须 Task 1 核实其与目标 API 模型及完整消息计数方式的对应关系,不能仅凭模型方发布过 tokenizer 即成立。同批三处**引用对齐**(非阻塞,不新增设计主题):①plan Task 25 Step 2——timer 保持 disabled **直到 Task 26 Step 5**(此前已取得正常运行授权并完成首期人工核验;步骤 3 是获得授权,不与实际启用动作混谈);②scheduling-ops §0 接口表——engine_meta(pay_paused) 写入职责对齐第四轮定稿(单元二对账硬失败亦置位,单元五恢复备份置位与人工解除,双方消费同一持久化闸门),不再是"单元五唯一写入者";③本文件 §5.3 engine_meta DDL 注释——"当前唯一键 pay_paused"更新为两类键内容(pay_paused+校准记录,校准记录契约引用单元二规则 11 不在本注释展开)。
- 2026-10-05 第四轮核验修正(M1 plan 评审轮:4 组 P1+计划校正表;不重开五单元):①**attempt_origin 授权语义定稿**——预占时确定、响应后不改写(unknown 通道重试返回 503 保持 origin='unknown_retry';再发起普通重试是**新授权** origin='retry');**名额公式简化**:普通尝试已用数=`origin IN ('initial','retry')` 行数(**不按 error_class 过滤**,名额按授权消耗,不因响应结果保留或改写);error_class 只决定能否再发送与通道(no_retry 拒/retryable 普通通道/unknown 满等待走 unknown 通道);unknown 名额与硬上限不变;②**校准通道入契约**(单元二规则 11,不再只在 plan 中设例外)——purpose='calibration' 是"校准未完成不出网"的**唯一显式例外**(解执行循环);走完整闸门,**月预算与窗口次数照常适用**,单列 `calibration.budget_micro_cny`(design.md budget.yaml 已同步,默认 ¥0.05 预占合计上限,耗尽中止);校准记录**绑定**模型/tokenizer 资源与版本/消息计数方式/系数(配置任一变化即失效须重校准),不是可跨配置沿用的 passed 标志;**删除无依据的默认系数 1.2**——官方 tokenizer 资源初始系数=1.0(依据=资源即服务端分词器);无官方资源时不预设系数,必须先建立"近似资源+系数能覆盖目标 API 输入计量"的依据,建立不了则停;近似小额探索(如进行)表述为"尚未验证上界的小额实验",不得称"已建立保守上界";③**预占公式补输出上限**(plan Task 5 引 budget.md 原文:输入预占 token 数×峰时未缓存输入价+max_output_tokens×输出价,向上取整微元)+**停新增持久化**——对账硬失败(usage 超计数/供应商实付>预占)置 pay_paused=1 并记录原因(复用既有闸门不另建暂停系统,重启继续拒绝、人工解除,复用/结算/只读照常);④**Task 26 授权顺序解循环**——本地替身验证→获真实校准授权→执行校准→校准通过+获正常付费运行授权→首期→自动调度验收(五步不得倒置);Task 25 部署期间 timer 安装但保持 disabled 直至付费启用完成(引擎侧校准状态检查为第二道闸门);服务器授权=一次授权覆盖列明范围,范围内直接执行,范围变化再确认。**计划校正表(同批落实)**:新增 Task 0 工程初始化;Task 10/11 明确 entry upsert 与 freeze INSERT 由**同一事务拥有者一次提交**(任务拆分≠事务拆分);Task 23 路径修正 site/src/content.config.ts+补两消费页面([...page].astro/[id].astro 成本标志同步显示;schema default(false) 仅旧文件兼容,**engine 断言新产物显式写布尔值**,两职责不混);Task 24 分窗口断言(有效响应不重发/缺失评分可按授权补发/unknown 保留预占遵循等待名额/发布恢复零模型调用——"任意阶段 kill 后零新增付费"不成立,已删)。model-calls v5/scheduling-ops(置位来源)/pipeline(口径行)/design.md(calibration 字段)同步。
- 2026-10-05 第三轮联合核验(②补齐+M1 plan 同批交付):①③④⑤ 关闭;②判定规则通过但持久化未闭合——补 **receipt_attempt 三列**:`attempt_origin`(授权来源 initial/retry/unknown_retry,预占事务写)、`error_class`(规范化 no_retry/retryable/unknown,失败或 unknown 状态更新同事务写;映射 no_retry={E1.request,E4.terminal,E5.balance}、retryable={E3.http,E4.parse}、unknown={E3.unknown})、`fail_detail_json`(http_status+矩阵子类+摘要,同事务写);**名额统计唯一口径**(§5.3.1)=普通名额消耗为 `origin∈{initial,retry} AND error_class='retryable'` 行数(≤max_attempts,即首+max_attempts−1 重),unknown 专属=unknown_retry_used 标志(与 origin='unknown_retry' 行同事务双写);"可重试类失败计数"一词统一指该公式,不再与"行数"混用;重启仅凭 DB 重放判定(400 与 503 同为 failed 未核清靠 error_class 区分)。验收 7d=落库关闭连接重读判定(替身)。model-calls v4/pipeline 计数行同步。**同批交付 M1 实施计划待评审稿**(docs/superpowers/plans/2026-10-05-m1-engine-implementation.md;含 tokenizer 校准数据来源与备份文件级验收两项验证任务)。

- 2026-10-05 第二轮联合核验修正(4 组 P1 阻塞+通知承诺收窄;一次修正统一交付):①**输入计量改 tokenizer 计数**——字符比例(含 1:1)退出授权链(官方换算仅"大致比例",推不出上界);预占=发送前最终请求 token 计数×校准系数;**计数不可得→不出网**;对账 usage.prompt_tokens 超计数=停新增+修正(删除"孤立个位可忽略"通过条件,处置同"供应商实付>预占");tokenizer 资源/版本/模型映射入 config,M1 实施第一步选型核对。②**再发送三条件**(错误类别允许自动重试/对应类别名额剩余——普通 max_attempts 与 unknown 专属名额**不互借**/累计硬上限 max_attempts+1+当次授权),同一判定用于补缺失与重跑;反例封堵:max_attempts=2 两次普通失败不因总数 2<3 续发。③**内容操作记录 ops_json**(digest_issue 扩列,12 表数不变):每次改变公开内容的操作**开始即 append 未完成项=待执行目标版本持久化**,提交/远端接收/线上确认分别补记 stages;**当前可见状态=最新 confirmed op**(withdrawn/relisted 专用列降为最近一次事实,修复"撤回→重上→再撤回"误判,用户内存 SQLite 实测);content_sha256 语义=当前确认版本(随确认类操作 UPDATE,历史经 ops_json);修正后恢复的目标身份出网前落库;**查找失败=证据不足→转人工**(不把未知当重新生成许可);**远端接收判定=分支可达性**(merge-base --is-ancestor,ls-remote 只示尖端)。④**restore-backup 序列=先在待启用副本置 pay_paused 并读回校验、后原子切换活动库**(不变量:切换完成⇔标志已先持久化,消除恢复操作自身中断窗口);**闸门读法=仅显式 0 放行,键缺失(裸恢复/库异常)同拒**,合法库建库即写默认 0。⑤通知崩溃承诺收窄:重启可能重复通知,不承诺外部精确一次也不承诺最多一次。单元文档 v3:model-calls/content-editing(①②)、publish-withdraw(③)、scheduling-ops(④⑤)。逐反例核验记录见 sessions/2026-10-05-m1-units-review3-fix.md。

- 2026-10-05 五单元联合核验修正轮(用户指出七组问题+prompt 缺口,一次修正统一交付):§5.3 扩为**12 表**——digest_issue 再扩 3 列(**content_sha256**=draft 落盘同事务持久化的不可变内容预期值,恢复比对基准;git_commit 语义改"commit 成功即回填,仍 draft";**relisted_utc/relist_commit**=重新上线留痕,与 withdrawn 两列构成三态判定)、notify_sent 改同 key **UPSERT**(主键即防重,重试成功 UPDATE 原行)、新增 **engine_meta 表**(key/value;pay_paused=备份恢复后全局付费暂停,restore-backup 命令置位,闸门拒新增付费防"丢回执重发重复扣费")。五单元文档同步 v2:费用上界闭合(1 字符=1 token 保守上界,截断保证完整请求≤max_input_tokens,实付≤预占)、attempt 计数粒度=logical_key 独立(score-1/score-2/understand 各自序列,重启不重置,耗尽不重获额度)、复用有效性纳入完整 E4 验证器(finish_reason=length 不可消费)、按上下文安全转义(Markdown 文本/链接目标分治,验收查渲染后 HTML)、发布四窗口 W1-W4+内容身份确定查找+线上证据链三步、恢复预算 recover_budget_s=600s+新期保底、截止锚点唯一化 frozen_utc(D/D+1 两窗)、普通项失败隔离(最终产物集合+终态统一清算)、prompt 初版全文定稿(units/content-editing.md 附录 A;类型/赞助规则与 selection.md 统一)。批量轮 session 末尾附 erratum(两处推演数字更正)。逐反例核验记录见 sessions/2026-10-05-m1-units-review2-fix.md。

- 2026-10-05 五单元批量闭环轮(用户指令:一次完成整批设计与自审):§5.3 扩为**11 表**——entry.`claim_issue`(占用归属,置 selected 同事务写/published 清/放弃失败期人工清)、receipt_attempt.`reconcile_json`(核清证据四要素与 actual 同一 UPDATE 事务)、digest_issue 扩 6 列(fail_reason/updated_utc/last_exit/last_run_utc/withdrawn_utc/withdraw_commit)、issue_freeze.paused 三列(冻结后全生命周期暂停)、**summary 表**(第 10,摘要结果与 analysis 对称 append-only)、**notify_sent 表**(第 11,通知去重 dedup_key 主键);§5.3.1 恢复字段映射全部定稿(不留 M1 plan)。新增单元三 engine/units/content-editing.md(占用协议/事务交界/prompt 权重初版/截断策略/组装就绪五判据/安全输出)、单元四 engine/units/publish-withdraw.md(三窗口恢复/隔离检查/撤回四步/重新上线两条/核清后提示)、单元五 engine/units/scheduling-ops.md(运行序/"1 个后续调度日"精确截止=运行时计算不加列/通知去重/status 事实清单/备份边界);model-calls.md v2 落实用户三组修正(请求身份覆盖实际输入/双次评分三分/N 三分);data-ingestion.md 回填微调;design.md(score.py/summarize.py 契约行)、pipeline.md(11 表)、digest-design.md §7(未决项批量闭环)同步。交付物含 8 组跨单元端到端场景推演(见 sessions/2026-10-05-m1-units-batch.md,文档推演非运行测试)。待用户跨单元联合核验。

- 2026-10-05 单元一复核+单元二联合定稿:单元一采集/冻结/窗口/去重/预筛排除规则通过用户复核(②③④组关闭,占用区分通过);复用识别与新增付费容量(N_new)的交接由 engine/units/model-calls.md 定稿——`reusable_scores` 只读接口传入预筛(预筛保持纯函数、不查 receipt)、N_new 仅限确需新增付费评分、先复用后截断、recoverable 单义化为"评分网络零新增"——并回填 data-ingestion.md(规则 7.6/8、输出③、验收 9 四子场景)与 engine/design.md 候选上限节;占用写入与释放协议仍留单元三联合定稿。

- 2026-10-05 M1 第 3 步启动(用户确认 digest-design v3 收口为功能输入基线):§4.1/§5.3.1 同步 cost_pending 字段契约(显式布尔/default 仅旧文件兼容/三处一致更新;"待实施契约"与"当前 site 实现"分层标注,site 代码待实施许可);§5.3 增 issue_freeze 表(9 表)承载期冻结确认事件——manifest 含每成员输入版本快照,"生成中已冻结"由该行承载、digest_issue 枚举不动;§8 文档树补 engine/digest-design.md 与 engine/units/。单元一设计见 engine/units/data-ingestion.md(设计稿待评审)。

- 2026-10-04 用户拍板博客直接用apex域名`nanmu.xyz`(替代`blog.nanmu.xyz`):§1.3决策表、§7 Caddy示例、astro.config `site`、部署手册与计划同步;apex A记录实测已指向服务器,接管既有指向127.0.0.1:3000的死转发Caddy块。

- 2026-10-04 M0 Task8a实施:§4.1的slug/原始路径/重复id/缓存校验落地(schema `.strict()`+源目录扫描+文件数一致性+`prebuild`/`predev`自动清缓存),状态行与§9.1顺序更新;负例与连续构建证据见sessions/2026-10-04-m0-task8a.md。

- 2026-10-04 技术契约复审修订:§4.1明确原始路径/禁slug/缓存验证,代码补验列M0 Task8a;§5对齐HTTP请求体、字段级配置停用、错误重试与整数预算单位、URL归一的本项目边界;§9.1-9.2明确M0→M1→M2进入条件与功能范围,更新当前状态。本轮为文档调整,不代表实现/部署/付费验收完成。

- 2026-10-02 初稿(骨架 + 已确认决策;细节章节随调研补充)
- 2026-10-02 细节补全:§4.1(Astro 双 collection)、§5 全章详设(AIHOT 模式移植 + topic-digest schema 核实)、§6(sqlite-vec + bge-m3)、§7(部署细节),待定项清零
- 2026-10-02 增补 PowerContext 调研:§6 检索设计(双通道混合/FTS 降级/EmbeddingProfile/可重建投影)、§8.1 会话交接纪律;结论"借鉴不采用"
- 2026-10-02 文档系统面向"新 agent 冷启动"补全:新增 docs/context/ 三篇(项目背景/服务器环境/上游数据源),AGENTS.md 扩充为入职第一文档,新增 ADR 与会话交接模板
- 2026-10-02 新增 docs/development/ 三篇(开发工作流/编码规范含 engine 目录结构预约束/四级质量门禁与未来计划强制测试清单)+ context/术语表:约束从背景到 M1/M2 开发细节的全链条
- 2026-10-02 全文档复审(漏缺扫描):§7 Caddy 404 改 handle_errors + reload 前 validate;§10 增三条部署风险(SSH 免密历史坑/Caddy 连累同机服务/开发机丢提交);§11 增 M1 启动前核查清单;§5.2 URL 归一黑名单标注 M1 定稿;新增 context/lessons.md 经验教训对照表;M0 plan Task 8/9/10 对应强化(诊断清单/bundle 降级/回滚演练);workflow 会话结束 push server;pipeline 增 digest 产物模板

- 2026-10-02 文档审查修订(ADR-0009):上游源码纠偏、调用尝试表与金额预占、提交/发布回执、后台有界构建、独立里程碑验收、外部事实分级。审查依据见 docs/reviews/2026-10-02-documentation-audit.md。

- 2026-10-03 内容schema、无产物失败期与恢复契约补充;现行要求已并入§4-§6。
- 2026-10-04 修正环境归因、门禁范围与操作流程;M1/M2待定实施细节明确标记,历史session不改写。
- 2026-10-04 引擎技术实施契约层(docs/engine/design.md:模块契约/配置格式/判重规则/错误分类与退出码/候选上限公式/日志观测)+ 线上线下调研定稿:AIHOT url.ts 判重规则核实(黑名单/微信特判/http统一/去末尾斜杠,§5.2 同步)、DeepSeek 定价复核与思考模式调用契约(budget.md)、topic-digest 本地库实测(无 fetched_utc 索引/正文空值约30%/90条12源,data-source);§11 核查前两项闭合。
