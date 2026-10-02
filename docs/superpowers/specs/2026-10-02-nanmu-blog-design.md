# nanmu-blog 设计文档

> 状态:草案(骨架已完成,细节章节随调研补充)
> 日期:2026-10-02
> 路径:Architectural(brainstorming → spec → writing-plans → 实施)

---

## 1. 背景与定位

### 1.1 三个前项目的结论

| 项目 | 结局 | 对本项目的输入 |
|------|------|----------------|
| nanmuli-blog(2026-04~06,已废弃) | 12.5 周烂尾,死因"开始设计太多导致后期无法进行" | 反面教材:范围铁律、伪需求清单(标签系统/自动优化闭环/质量评分趋势不做);正面资产:日报/AI 整理的产品想法、AesEncryptor/请求层等可参考实现 |
| topic-digest(2026-08-31 上线,生产运行中) | 9 月 720/720 全绿,零故障 | 已验证的极简运维模式(SQLite + systemd timer + flock + 原子 symlink 发布);**继续在产,本项目的 AI 引擎直接读它的数据** |
| AIHOT(开源,4 天 4893 stars) | 生产级 AI 聚合框架 | 六大可搬模式:URL 判重、双次独立评分、单一公开投影、回执+预算熔断、industry 配置包、append-only 判断+人工覆盖;不整体引入(重装备+成本) |

### 1.2 定位(2026-10-02 与用户确认)

- **博客本体做简单版本**——git 写作流,静态站,无后台无数据库
- **项目重心是 AI 与博客的连接层**,两个方向:
  1. **AI 内容自动发布**:topic-digest 聚合数据 → AI 精选/评分/摘要 → 自动发布为博客"日报"栏目(借鉴 AIHOT 模式 + 旧博客日报想法)
  2. **博客内容 → AI 知识库**:个人文章 + AI 精选内容向量化 → RAG 问答/搜索(先自用)
- 部署:同服务器(123.56.223.97,当前 load 0 / 内存余量 1.4G)+ 子域名走 Caddy
- 设计参考:AIHOT 的设计模式 + 旧博客(nanmuli-blog)的产品想法,轻量实现

### 1.3 默认决策(用户未反对即生效,均可推翻)

| 决策点 | 默认值 |
|--------|--------|
| 子域名 | `blog.nanmu.xyz`(已核实:主域名已备案则子域名免单独备案,阿里云官方口径) |
| AI 内容形态 | 每日一期日报(延续旧博客想法) |
| RAG 使用者 | 仅自己(basicauth 保护) |
| LLM 提供商 | DeepSeek 为主(兼容端点,沿用现有账号),Qwen 备选 |

## 2. 设计原则(铁律)

1. **范围是生死线**(nanmuli-blog 头号教训):每个里程碑必须独立可发布,不欠债进下一个
2. **博客本体永远不为 AI 功能加复杂度**:AI 挂了博客照常在线
3. **AI 引擎独立进程独立数据库**:engine 崩溃不影响博客,反之亦然
4. **topic-digest 保持现状不动**:本项目只读它的 SQLite(同机文件只读),不改它
5. **付费请求先记回执再消费 + 三级预算熔断**(AIHOT 模式),LLM 月预算红线 **¥50**
6. **页面永不调模型**:读者打开页面只读预生成内容
7. **AI 生成内容必须标注**:digest 栏目页脚/文件头注明 AI 生成,与个人文章视觉区分
8. **文档随代码走**:AGENTS.md 第一天就有,决策记录(ADR)随设计落盘

## 3. 总体架构

```
                     ┌─ 个人写作流 ──────────────────────────────┐
                     │ 本地 Markdown → git push → bare repo     │
                     │   (/opt/git/nanmu-blog.git)              │
                     │   post-receive hook → 触发构建           │
                     └──────────────┬───────────────────────────┘
                                    ▼
┌─ AI 引擎(engine)─┐      ┌─ 博客站(site)──────────────┐
│ Python worker     │      │ Astro 5 静态构建            │
│ systemd timer     │─────▶│ content/posts  (个人文章)   │
│  ├ collect:读     │ 写   │ content/digest (AI 日报)    │
│  │  topic-digest  │ digest│        ↓ astro build       │
│  │  SQLite(只读) │ md + │ releases/<ts>/              │
│  ├ 判重/精选/摘要 │ git  │ current symlink 原子切换    │
│  ├ 回执+预算熔断   │ commit│ (topic-digest 已验证模式)  │
│  └ 向量索引 → RAG │      └──────────────┬──────────────┘
└──────┬────────────┘                     ▼
       ▼                          ┌─ 入口(Caddy)──────────────┐
┌─ RAG 服务 ────────┐             │ blog.nanmu.xyz → 静态站    │
│ 轻量 API(FastAPI) │◀────────────│ /api/* → RAG 服务反代      │
│ basicauth 保护     │             │ (443, 主域证书覆盖)        │
└────────────────────┘             └───────────────────────────┘
```

数据流三句话:
1. **写作流**:人写 markdown → git push → hook 构建 → 静态发布
2. **AI 流**:engine 定时读 topic-digest 数据 → 评分精选 → 摘要 → 产出 digest markdown + git commit(触发同一构建链)→ 发布
3. **RAG 流**:engine 对全部内容建向量索引 → RAG API 供问答

## 4. 博客本体(site,M0)

- **Astro 5**,零客户端 JS 优先,明暗主题跟随系统(topic-digest 同款审美)
- 内容模型(content collections):
  - `posts/`——个人文章,手写,frontmatter: title/date/tags/draft
  - `digest/`——AI 日报,程序生成,frontmatter 额外带 `generated: true`、`ai_model`、`cost_cny` 等溯源字段
  - `about`——关于页,`src/pages/about.astro` 普通页面,不进 collection
- 页面:首页(文章+日报双栏或单列)、`/posts/*`、`/digest/*`、`/about`、RSS(个人文章一条、日报一条)
- 无管理后台:git 即 CMS

### 4.1 混合内容组织(Astro 5 Content Layer,已验证)

- 配置文件为 `src/content.config.ts`(Astro 5 起不再用 `src/content/config.ts`);两个独立 collection = 独立目录 + 独立 schema,手写与生成天然隔离:
  ```ts
  import { defineCollection, z } from 'astro:content';
  import { glob } from 'astro/loaders';

  const posts = defineCollection({
    loader: glob({ pattern: '**/*.md', base: './src/content/posts' }),
    schema: z.object({
      title: z.string(), pubDate: z.coerce.date(),
      tags: z.array(z.string()).default([]), draft: z.boolean().default(false),
    }),
  });

  const digest = defineCollection({
    loader: glob({ pattern: '**/*.md', base: './src/content/digest' }),
    schema: z.object({
      date: z.string(), generated: z.literal(true),
      ai_model: z.string(), entry_count: z.number(), cost_cny: z.number(),
    }),
  });

  export const collections = { posts, digest };
  ```
- 生成内容由 engine 落盘 + git 提交触发构建(build 开始时文件已存在)——构建确定性、可回滚、离线可复现;**绝不在 build 内调 LLM**(铁律 6);`.astro/` 数据存储目录 gitignore,跨构建持久化
- 分页分开:`/posts/[...page]` 与 `/digest/[...page]` 各自 `paginate(getCollection(...))`;RSS 分开:`/rss.xml`(个人文章)与 `/digest.xml`(日报)两个 endpoint
- **schema 即契约**:digest frontmatter 不合法 → 构建失败 → 部署不发生——天然闸门;engine 的测试必须覆盖此 frontmatter 契约

## 5. AI 引擎(engine,M1)——项目重心

> 细节设计基于 AIHOT 操作级深挖结论(2026-10-02),轻量化适配单机 SQLite 场景。AIHOT 25 张表 → 本设计 8 张表;PostgreSQL advisory lock → flock + 单进程串行。

### 5.1 形态
- Python 3.11 venv + SQLite(WAL)+ systemd timer + flock(整套 topic-digest 已验证运维模式)
- 目录:`engine/`(与 site/ 同 repo,monorepo 但边界清晰:engine 只产出 markdown 到 `site/src/content/digest/`,不碰构建)

### 5.2 管线(每日一期,总流程)
```
collect   读 topic-digest SQLite 只读(item JOIN source,近 24-48h;字段已实读 schema.sql 核实:
          item.url_hash/url/title/published_utc/content_text/status,source.name/weight/enabled;
          cluster/pick/daily 三表为预留空表——M1 从未动工,engine 不依赖它们)
   ↓
判重      identity_key 归一(AIHOT url.ts 规则:去 www/强制 https/删 20+ 追踪参数/
          参数排序/微信四参特判)→ entry 表 INSERT OR IGNORE
   ↓
预筛      本地规则零成本:标题关键词黑名单、死源排除、已上过日报的 identity_key 排除
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
发布      git add + commit 到本仓库 → 触发博客构建链(post-receive 或 timer)
   ↓
记账      digest_issue 表记录本期成本;api_usage 月度聚合
```

### 5.3 数据模型(engine SQLite,8 表 DDL 要点)

```sql
-- 候选条目(topic-digest 条目的快照,判重后)
CREATE TABLE entry (
  id INTEGER PRIMARY KEY,
  identity_key TEXT NOT NULL UNIQUE,      -- url:{归一URL} 判重键
  url TEXT NOT NULL, title TEXT NOT NULL,
  source_name TEXT NOT NULL, source_tier TEXT NOT NULL DEFAULT 'T2',  -- T1/T2
  published_utc TEXT, discovered_utc TEXT NOT NULL,
  content_text TEXT,                       -- 提取正文(来自 topic-digest)
  status TEXT NOT NULL DEFAULT 'pending'   -- pending/scored/selected/rejected/used
    CHECK(status IN ('pending','scored','selected','rejected','used'))
);
CREATE INDEX idx_entry_discovered ON entry(discovered_utc DESC);

-- 回执(每次付费调用前落一条;幂等键防重复扣费)
CREATE TABLE receipt (
  id INTEGER PRIMARY KEY,
  logical_key TEXT NOT NULL UNIQUE,        -- service:purpose:model:sha256(identity):attemptTag
  service TEXT NOT NULL,                   -- llm
  purpose TEXT NOT NULL,                   -- score/understand/summarize
  model TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'   -- pending/received/completed/failed/unknown
    CHECK(status IN ('pending','received','completed','failed','unknown')),
  request_digest TEXT,                     -- 脱敏摘要(不含 key)
  response_json TEXT, usage_json TEXT,     -- tokens 等由月度聚合读
  cost_cny REAL,                           -- 单次成本(按价目表折算)
  attempts INTEGER NOT NULL DEFAULT 0,
  created_utc TEXT NOT NULL, completed_utc TEXT
);
CREATE INDEX idx_receipt_open ON receipt(status) WHERE status IN ('pending','unknown');

-- 三级预算(次数限制;行缺失=不限;任一档 ≤0 = 立即停用)
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

-- 人工覆盖(优先于一切自动判断)
CREATE TABLE override (
  identity_key TEXT PRIMARY KEY,
  action TEXT NOT NULL CHECK(action IN ('force_include','exclude')),
  reason TEXT, created_utc TEXT NOT NULL
);

-- 每期日报
CREATE TABLE digest_issue (
  issue_date TEXT NOT NULL UNIQUE,         -- YYYY-MM-DD
  entry_ids TEXT NOT NULL,                 -- JSON 数组
  markdown_path TEXT NOT NULL,
  git_commit TEXT,
  cost_cny REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','failed')),
  created_utc TEXT NOT NULL
);

-- 月度成本聚合(报表用,从 receipt 聚合)
CREATE TABLE api_usage (
  month TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
  tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,
  cost_cny REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (month, provider, model)
);

-- (M2 追加)向量数据不入本库:独立 rag.db(vec0 虚拟表 float[1024] + 溯源列),
-- 与 engine.db 解耦,可随时删除全量重建(见 §6)
```

### 5.4 回执状态机与预算熔断(AIHOT 模式,逐条搬)

**状态机**:
```
pending → received → completed   (正常成功:响应先落库再做业务写,崩溃可复用已付费结果)
pending → unknown                (超时/崩溃等结果不明)
unknown → failed                 (≥30min 自动放行,每条只放一次;二次必须人工)
received → failed                (响应不可解析)
failed → pending                 (重试:attempts+1,先复查预算)
status ∈ {received, completed}   (直接复用,零网络调用)
```

**幂等键**:`service:purpose:model:sha256(stable_json(identity)):attemptTag`

**三级预算**(单进程下用 flock + 计数查询替代 advisory lock):
- 统计口径:近 1min / 1h / 24h 三个滑动窗口内 `receipt.attempts` 总和,任一窗口超限即抛错
- 超限抛错,retryAfter 60s/600s/3600s;**任一档 ≤0 = 立即停用**
- 初始值(按 DeepSeek 日报量级估算,可调):per_minute=10 / per_hour=100 / per_day=400 次调用;月红线 ¥50 由日预算 × 单价逼近 + `api_usage` 月聚合超 ¥40 告警兜底

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
  ├── sources.yaml        # 源偏好:tier 映射(机器之心=T1 等)、排除死源(36氪/机器之心当前 feed 已坏)
  ├── selection.yaml      # 门槛 {T1: 60, T2: 75}、每期条目数上限、板块划分
  └── prompts/            # score.md / understand.md(摘要写作)/ rules-anti-hallucination.md
```

### 5.7 调度与运维

- `nanmu-blog-engine.timer`:每日 08:30(Asia/Shanghai,无时区后缀——systemd 239 限制,topic-digest 已踩坑)+ RandomizedDelaySec=300 + Persistent=true(missed 补跑一次)
- flock `/run/lock/nanmu-blog-engine.lock`
- 失败隔离:单条目失败不挂整期;LLM 全挂 → 该期不生成(digest_issue 记 failed),博客照常在线
- OnFailure 通知:与 topic-digest 共用 `/etc/topic-digest.env` 通知凭据(这次配好)

## 6. RAG 知识库(M2)

选型已定(2026-10-02 调研验证):

- **向量存储:sqlite-vec v0.1.9**(PyPI 稳定版;requirements 锁版本——官方声明 pre-v1 会有 breaking changes)
  - 万级向量 brute-force KNN 毫秒级、内存 ~50MB——不需要 ANN 索引(stable 通道本就没有 ANN)
  - 排除 Chroma(~800MB 常驻内存,1.8G 机器直接出局);LanceDB 仅当向量涨到数十万级再考虑
  - SQLite 单写入者约束恰好契合架构:**engine timer 写向量,常驻 RAG API 只读**
  - 向量以紧凑二进制存储(float32 `struct.pack`);**embedding 身份 = model+dimension+distance+normalization 钉成整体**(PowerContext EmbeddingProfile 模式),每条向量绑定被嵌入内容的 hash——换模型/内容变更可机器检测陈旧向量;**索引表一律视为可重建投影,chunk 行表才是唯一真相**,提供一键 rebuild
  - 长期观望 SQLite 官方 vec1 扩展(真 ANN,v0.7,当前仅源码编译、无 Python 包生态,不选)
- **embedding:SiliconFlow `BAAI/bge-m3` 主用**(免费、1024 维、8K 上下文、OpenAI 兼容 `/embeddings`,与 sqlite-vec `float[1024]` 对齐);备选阿里百炼 `text-embedding-v4`(¥0.5/M token,精度更高,免费档限速或需要精度时切换)。DeepSeek 无 embedding API,排除。本量级月成本个位数元,远低于红线
- **架构**:
  ```
  engine(timer)→ 增量索引(posts 全文 + digest 精选条目)→ rag.db(vec0 虚拟表 float[1024])
  FastAPI /ask(仅自用,basicauth)→ 向量检索 top-k=8 → DeepSeek 生成答案(必须附来源链接)
  Caddy(rag 子域名或 blog 站块 /api/* 反代)→ localhost:8787
  ```
- **检索设计(双通道混合,PowerContext 模式)**:
  - FTS5(bm25)+ 向量两条通道独立检索,融合去重后取 top-k=8;每个命中标注 `matched_by: fts|vector|both`——检索质量可观测
  - **embedding 端点失败自动降级纯 FTS**,不报错拒答
  - chunk 带 `corpus` 列(posts/digest)按语料分区;注入 prompt 的检索结果设字节预算上限
- 曾评估 OceanBase PowerContext 整体采用,结论**不采用**:它解决 agent 跨会话交接而非知识库问答,server 栈常驻约 150-250MB(手写方案 50-100MB),六周三版 breaking change;且其检索底座恰是 FTS5+sqlite-vec 同款积木,反向验证本选型
- 验收(M2):检索相关性人工抽查合格;响应 < 5s;答案必须带来源(博客文章路径或日报条目 URL)

## 7. 部署与运维

- 服务器:123.56.223.97(Alinux 3,systemd 239,Caddy 80/443 已有,1.8G 内存 + 2G swap)
- **子域名与备案(已核实,2026-10-02)**:阿里云官方口径——主域名已有 ICP 备案,其子域名无需单独备案,直接 DNS 解析即可;备案与服务器同在阿里云,不存在跨商接入备案问题;公安备案同以主域名为单位
- **Caddy**(注意 v2.8+ 指令名是 `basic_auth`,不是旧名 `basicauth`):
  ```caddyfile
  blog.nanmu.xyz {
      root * /var/www/nanmu-blog/current/dist
      file_server
      try_files {path} /404.html
  }
  rag.nanmu.xyz {            # M2;或并入 blog 站块用 handle_path /api/* 反代,二选一
      basic_auth {
          admin <bcrypt-hash>   # `caddy hash-password` 预生成;凭据不落盘
      }
      reverse_proxy localhost:8787
  }
  ```
  `basic_auth` 默认在 `reverse_proxy` 之前执行,自动覆盖被代理上游;依赖 Caddy 为公网域名自动签 TLS
- **git push 自动构建**(bare repo + post-receive;topic-digest 已验证模式 + 调研补强两个坑):
  - 只部署 `refs/heads/main`;忽略删分支(null SHA)
  - post-receive 内 `flock -n /tmp/nanmu-blog-build.lock -c 'deploy.sh'` **后台执行、立即返回**——push 不被 astro build 阻塞;并发构建自动跳过
  - deploy:`GIT_WORK_TREE=临时目录 git checkout -f` → `npm ci --cache`(服务器留 npm 缓存缩短构建)→ `astro build --outDir /var/www/nanmu-blog/releases/<sha>/dist` → 清理临时目录
  - **原子切换必须 `mv -T`**(先建 `current.tmp` 软链再 rename);`ln -f` 存在 unlink 窗口,不可用;保留最近 N 版目录供回滚
  - 权限:git 用户写 releases/,Caddy 经 symlink 只读,全程无需 sudo
  - 内存:topic-digest 同机实测 astro build 峰值 241MB,本项目同量级无虞,swap 已配
- 新增 systemd units:
  - `nanmu-blog-build.service`(oneshot,post-receive 调用)
  - `nanmu-blog-engine.timer`:每日 08:30 + RandomizedDelaySec=300 + Persistent=true(missed 补跑一次)
  - `nanmu-blog-rag.service`(M2,常驻,MemoryMax=200M)
- 备份:engine SQLite 纳入每日备份(复用 topic-digest 的 `conn.backup()` Online Backup 模式,保留 30 天);异地备份与 topic-digest 一起补课(两项目共同债)
- 监控:journal 留痕 + OnFailure 通知(通知凭据这次配好,不再欠)

## 8. 文档系统

```
nanmu-blog/
├── AGENTS.md                        # AI agent 项目说明书(第一天就有,AIHOT 模式)
├── README.md                        # 定位 + 快速上手 + 三个前项目结论链接
├── CLAUDE.md                        # 项目记忆(与 AGENTS.md 同口径)
├── docs/
│   ├── superpowers/specs/           # 设计文档(本文档)
│   ├── superpowers/plans/           # 实施计划(writing-plans 产物)
│   ├── architecture.md              # 三件套架构与数据流(M0 时写)
│   ├── engine/pipeline.md           # 管线各阶段说明(M1 时写)
│   ├── engine/selection.md          # 精选标准/门槛/调整记录(编辑策略文档)
│   ├── engine/budget.md             # 成本治理与月度成本记录
│   ├── ops/deploy.md                # 部署 runbook(topic-digest 模式,逐字可执行)
│   ├── ops/runbook.md               # 巡检/回滚/故障处理
│   └── decisions/                   # ADR 架构决策记录(0001 起)
```

文档纪律:设计变更先改文档再改代码;每个里程碑的验收清单写入 plan;过期文档宁可删除不留误导(nanmuli-blog 教训)。

### 8.1 会话交接纪律(PowerContext 模式,针对 nanmuli-blog 头号死因)

nanmuli-blog 复盘的死因之一是跨会话上下文断层(9 月观测真空即此类)。本项目从第一天执行轻量交接纪律(纯 markdown,不引入工具):

- **交接记录** `docs/sessions/`:每次开发会话结束写一份(agent 生成),字段——
  - `objective` 本次目标;`state[]` 已完成事项,**每条附证据**(commit/测试/文件路径)
  - `disposition` continuable | blocked | complete;`next_action` 下一步
  - `omissions` 已知未验证/缺失项——**显式声明"我不知道什么"**(跨会话断层的主要来源)
- **声明分级**:陈述标注 [verified: 证据] 或 [declared];declared 不得伪装成有证据
- **接手检查**:新会话先 `git log` + 跑测试核对交接文档声称的状态,不符先纠偏再动工
- **终态原则**:交付文档是终态,不引用草稿/评审轮次/被否决的决策(与 ADR 写法一致)

## 9. 里程碑与验收标准

| 里程碑 | 内容 | 验收标准 | 量级 |
|--------|------|----------|------|
| **M0 博客上线** | Astro 站 + git 写作流 + 构建发布 + 子域名 | 手写一篇文章 push 后 3 分钟内线上可见;RSS 可订阅;明暗主题正常 | 1-2 天 |
| **M1 AI 引擎** | collect→评分→摘要→日报发布全链 + 成本治理 | 连续 3 天自动产出日报且入选质量可接受;单期成本 ≤¥1;熔断器注入测试通过;AI 内容有明确标注 | 3-5 天 |
| **M2 RAG** | 向量索引 + /ask API | 个人文章+日报可问答,检索相关性抽查合格;响应 < 5s | 2-3 天 |
| **M3 可选** | 周报/热度/更多 AIHOT 模式 | 按需定义 | — |

## 10. 风险清单

| 风险 | 对策 |
|------|------|
| 范围蔓延(头号历史死因) | 里程碑铁律;M3 功能一律"记录想法不动工" |
| LLM 成本失控 | 回执+三级熔断+月红线;日报 frontmatter 记成本可见 |
| 子域名/DNS 异常 | 已核实子域名免单独备案;降级:IP+端口先跑(topic-digest 的 8080 模式) |
| 服务器内存(1.8G) | topic-digest 同机实测 astro build 峰值 241MB;RAG 常驻 MemoryMax=200M;swap 2G 已配 |
| AI 日报质量不可接受 | 双次评分+人工覆盖表;M1 验收含人工抽查;门槛可配置随时调 |
| topic-digest 变更破坏读取 | 只读 + 明确 schema 依赖清单;坏读取只影响当天日报 |

## 11. 调研落地记录(原待定项已全部补全)

- [x] §4.1 Astro 混合内容:双 collection + glob loader + 分页/RSS 分开(Astro 5 官方文档验证)
- [x] §5 引擎详设:DDL 8 表 / 回执状态机 / 三级预算 / 评分 prompt 结构(AIHOT 操作级深挖移植)
- [x] §5.2 collect 字段:topic-digest `schema.sql` 实读核实(item JOIN source;cluster/pick/daily 为空表不依赖)
- [x] §6 sqlite-vec v0.1.9 + SiliconFlow bge-m3(免费 1024d);排除 Chroma(内存不匹配)
- [x] §7 Caddy `basic_auth` + 子域名免单独备案(阿里云官方口径)+ post-receive 后台 flock 构建 + `mv -T` 原子切换
- 参考项目补充:Horizon(9.6k★,采集→LLM 编辑→日报,与本项目管线同构)的"先过滤后增强/分类配额防霸屏/`api_key_env` 间接引用"已吸收进 §5;open-aggregator 的"LLM 不可达→降级输出、站点保持在线"已吸收进 §5.7 失败隔离。同类日报管线实测成本 ~$0.01/天,¥50/月红线非常宽裕
- PowerContext(oceanbase,1.2k★):评估后**不采用**(问题域是 agent 会话交接而非知识库问答),搬走其最值钱的模式——§6 双通道混合检索 + matched_by 观测 + EmbeddingProfile + FTS 降级,§8.1 会话交接纪律(omissions/声明分级/接手检查,直击 nanmuli-blog 跨会话断层死因)

---

## 附:变更记录

- 2026-10-02 初稿(骨架 + 已确认决策;细节章节随调研补充)
- 2026-10-02 细节补全:§4.1(Astro 双 collection)、§5 全章详设(AIHOT 模式移植 + topic-digest schema 核实)、§6(sqlite-vec + bge-m3)、§7(部署细节),待定项清零
- 2026-10-02 增补 PowerContext 调研:§6 检索设计(双通道混合/FTS 降级/EmbeddingProfile/可重建投影)、§8.1 会话交接纪律;结论"借鉴不采用"
