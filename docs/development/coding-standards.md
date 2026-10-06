# 编码规范

> 约束未来所有代码(含 M1/M2)。新增代码违反本文 = review 不通过。改变架构/跨组件契约先改spec或ADR;局部实现细节、事实勘误与文字优化不要求新建ADR。

## 通用

- 标识符英文;注释与文档中文
- **最小变更**:只改与目标相关的部分,不顺手重构、不改无关格式
- 外部事实(版本号、端口、路径、价格)不硬编码进代码——进 config、环境变量或 `docs/context/server-environment.md` 指向的配置
- 错误信息面向排障:含阶段名与关键标识(entry id / url),不输出密钥
- 文件保持小而专注:一个模块一个职责;超 ~300 行考虑拆分
- 修改前搜索定义、调用方、配置消费方和相关测试,复用现有实现。不要仅凭计划中的片段推断当前API;版本和可用命令以项目配置/锁文件/实际输出为准
- 保持公共接口与存量数据兼容;不兼容变更明确迁移与失败恢复路径。不要靠删除数据库、放宽校验、吞异常或删除失败测试让门禁变绿
- 配置、文件、数据库与网络边界显式处理失败;日志说明可定位的原因。可恢复失败仅按既定降级契约继续,不得返回伪成功

## site/(TypeScript + Astro,M0)

- **零客户端 JS 是铁律**:`.astro` 组件禁止 `<script>` 标签;需要交互 = 不做(ADR-0002)
- 运行时依赖白名单:`astro`、`@astrojs/rss`。新增依赖必须有充分理由(写进 commit message)
- 样式:全局用 `src/styles/global.css` 的 CSS 变量;组件内可用 scoped `<style>`;禁止引入 CSS 框架
- 组件:展示组件放 `src/components/`,只接收 props 不做数据获取;数据获取只在页面 `frontmatter`(`getCollection`/`getStaticPaths`)
- content schema 是契约(`src/content.config.ts`):改 schema 必须同步①spec §4.1 ②M0计划中仍作为实施基线的schema ③受影响的内容/冒烟断言;不要求无关的路由清单跟着字段变化
- 列表过滤规则统一:`draft` 排除逻辑出现在列表、详情 getStaticPaths、RSS 三处,新增出口必须同样排除

## engine/(Python 3.11,M1)

### 目录结构(预先约束,M1 plan 按此展开)

```
engine/
├── config/                 # spec §5.6:sources.yaml / selection.yaml / budget.yaml / prompts/*.md
├── src/nanmu_engine/       # 主包
│   ├── __init__.py
│   ├── config.py           # 只读 config/,暴露类型化配置对象(含限额/价目版本)
│   ├── db.py               # engine.db 连接与 12 表迁移(spec §5.3,单一入口)
│   ├── collect.py          # 读 topic-digest(mode=ro)
│   ├── normalize.py        # identity_key URL 归一
│   ├── prescreen.py        # 零成本预筛
│   ├── score.py            # 双次评分(经 ledger)
│   ├── summarize.py        # 摘要写作(经 ledger)
│   ├── assemble.py         # 组装 digest markdown + frontmatter
│   ├── publish.py          # commit/push/线上确认(产出 digest_issue 状态)
│   ├── ledger.py           # receipt/receipt_attempt/budget:状态机+次数/金额预占
│   └── llm.py              # OpenAI 兼容客户端,唯一模型请求网络出口
├── tests/                  # pytest,LLM 一律 mock
└── requirements.txt
```

各模块的输入/输出/副作用与硬边界契约见 [engine/design.md](../engine/design.md)。

### 依赖纪律

- stdlib优先。运行依赖白名单:`httpx`、`PyYAML`、`tokenizers`(Task 1 选定,HF Rust 轻量库,`Tokenizer.from_file` 消费锁定版 tokenizer.json,不引入 transformers/torch;M2追加:`sqlite-vec`、`fastapi`、`uvicorn`);测试依赖:`pytest`、`pytest-mock`,部署安装与测试环境分开列出
- **LLM/embedding 的 API key 只从环境变量读**;真实key只放服务器 `/etc/nanmu-blog.env`,经systemd `EnvironmentFile`提供。本地单测只用假值与mock,config与代码里只有变量名;`.env`被gitignore不是存储真实凭据的授权

### SQLite 约定

- 本项目可写engine.db连接经 `db.py` 单一入口:`PRAGMA journal_mode=WAL`、`busy_timeout=5000`、`foreign_keys=ON`
- 打开topic-digest用独立只读连接函数 `file:...?mode=ro`,不执行写PRAGMA/迁移;验证WAL/SHM访问条件(ADR-0003)
- 迁移:DDL与有序迁移单点在db.py,带版本号;仅空库可直接建表。旧库先备份,逐版本迁移,成功后更新版本;遇到未知较新版本或迁移失败拒绝启动写入,不重置数据库。恢复用验证过的备份与匹配代码并核对付费账本/Git,不盲目回退旧库。M1计划实现失败恢复测试,不引入Alembic

### 管线约定

- 每阶段明确输入、输出与副作用:规则计算尽量纯函数,DB写入/文件/网络边界显式隔离;阶段间只经 engine.db 与明确的参数传递
- 失败隔离不变量(spec §5):单条目失败不挂整期;LLM全挂/无合格产物 → digest_issue记failed并退出非零;OnFailure通知脚本按连续2期去重,配置错误/崩溃立即通知
- **一切付费调用必须经 `ledger.py`**:先在短事务核对额度并写receipt/receipt_attempt预占,提交后再调 `llm.py`;业务代码禁止直接 import httpx 调模型
- 日志:`logging` 标准库,每行带阶段名(如 `score entry=42 s1=71 s2=68 selected=0`);密钥与全文内容不进日志
- 时间统一 UTC ISO8601 存库,展示层转 Asia/Shanghai

### 测试要求(pytest)

- **LLM 一律 mock**:单测零网络零花费;`llm.py` 本身用 httpx MockTransport 测
- 风险用例统一见 [质量门禁的未来测试清单](quality-gates.md);测试数据按spec边界构造,不在本文件另维护一份可能漂移的阈值/重试表
- 测试文件命名 `test_<模块>.py`,fixture 复用放 `tests/conftest.py`(临时 SQLite 库)
- 文件写入、Git发布和上游数据库访问在单测中使用临时目录、夹具或替身,禁止连接生产库、触发真实push或调用真实服务。集成验收单列执行前提与副作用,不混入默认单测

## RAG/(M2)

- 服务骨架遵守 engine 的 Python 约定;`rag.db` 独立、可随时删除重建(spec §6)
- 检索双通道:命中必须带 `matched_by` 标注;embedding 端点失败自动降级 FTS
- `/ask` 响应必须附来源链接(文章路径或日报条目 URL)

## 提交与文档联动

- 改行为必查文档是否需要同步:pipeline/selection/budget 三份运营文档与代码不一致 = bug
- 跨组件或长期架构决策写ADR,局部实现说明写session;模板 `docs/decisions/_template.md`

## M1/M2补充契约

- 金额使用整数微元,不以SQLite REAL作限额比较;单次HTTP请求有超时与输出上限,重试逐次记账。DB事务不跨网络等待。
- RAG对rag.db只读,付费问答仍通过ledger对engine.db记账;M2并发请求与timer必须共同验证月限额,不能靠各进程自己的flock假定互斥。
- 只索引已发布内容,排除draft;文章修改/删除有对应索引失效测试。Markdown是语料源,重建chunk/FTS/向量时不删除原文。
- 新增表/状态/API契约先改spec或ADR;不要求每个局部实现小选择都新增ADR。
