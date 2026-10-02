# 编码规范

> 约束未来所有代码(含 M1/M2)。新增代码违反本文 = review 不通过。改本文先提 ADR 或改 spec。

## 通用

- 标识符英文;注释与文档中文
- **最小变更**:只改与目标相关的部分,不顺手重构、不改无关格式
- 外部事实(版本号、端口、路径、价格)不硬编码进代码——进 config、环境变量或 `docs/context/server-environment.md` 指向的配置
- 错误信息面向排障:含阶段名与关键标识(entry id / url),不输出密钥
- 文件保持小而专注:一个模块一个职责;超 ~300 行考虑拆分

## site/(TypeScript + Astro,M0)

- **零客户端 JS 是铁律**:`.astro` 组件禁止 `<script>` 标签;需要交互 = 不做(ADR-0002)
- 运行时依赖白名单:`astro`、`@astrojs/rss`。新增依赖必须有充分理由(写进 commit message)
- 样式:全局用 `src/styles/global.css` 的 CSS 变量;组件内可用 scoped `<style>`;禁止引入 CSS 框架
- 组件:展示组件放 `src/components/`,只接收 props 不做数据获取;数据获取只在页面 `frontmatter`(`getCollection`/`getStaticPaths`)
- content schema 是契约(`src/content.config.ts`):改 schema 必须同步①spec §4.1 ②`scripts/smoke.mjs` 清单 ③受影响的冒烟断言
- 列表过滤规则统一:`draft` 排除逻辑出现在列表、详情 getStaticPaths、RSS 三处,新增出口必须同样排除

## engine/(Python 3.11,M1)

### 目录结构(预先约束,M1 plan 按此展开)

```
engine/
├── config/                 # spec §5.6:sources.yaml / selection.yaml / prompts/*.md
├── src/nanmu_engine/       # 主包
│   ├── __init__.py
│   ├── config.py           # 只读 config/,暴露类型化配置对象
│   ├── db.py               # engine.db 连接与 8 表 schema(单一入口)
│   ├── collect.py          # 读 topic-digest(mode=ro)
│   ├── normalize.py        # identity_key URL 归一
│   ├── prescreen.py        # 零成本预筛
│   ├── score.py            # 双次评分(经 ledger)
│   ├── summarize.py        # 摘要写作(经 ledger)
│   ├── assemble.py         # 组装 digest markdown + frontmatter
│   ├── publish.py          # git commit(产出 digest_issue 状态)
│   ├── ledger.py           # receipt/budget:回执状态机 + 三级熔断
│   └── llm.py              # OpenAI 兼容客户端,唯一网络出口
├── tests/                  # pytest,LLM 一律 mock
└── requirements.txt
```

### 依赖纪律

- stdlib 优先。白名单:`httpx`、`PyYAML`、`pytest`、`pytest-mock`(M2 追加:`sqlite-vec`、`fastapi`、`uvicorn`)
- **LLM/embedding 的 API key 只从环境变量读**(本地 `.env` 已 gitignore / 服务器 `/etc/nanmu-blog.env` 经 systemd `EnvironmentFile`);config 与代码里只有变量名

### SQLite 约定

- 打开一律经 `db.py` 单一入口:`PRAGMA journal_mode=WAL`、`busy_timeout=5000`、`foreign_keys=ON`
- 打开 topic-digest 必须 `file:...?mode=ro`(ADR-0003)
- 迁移:engine.db schema 变更 = 改 `db.py` 内 DDL + 版本号,启动时自动建表/加列;不用 Alembic(YAGNI)

### 管线约定

- 每阶段是纯函数式模块:输入明确(上阶段产物/DB 查询),输出明确(DB 写入/文件);阶段间只经 engine.db 与明确的参数传递
- 失败隔离不变量(spec §5):单条目失败不挂整期;LLM 全挂 → digest_issue 记 failed 退出 0(不触发 OnFailure 告警噪音,连续 2 期失败才人工)
- **一切付费调用必须经 `ledger.py`**:先 INSERT receipt,再调 `llm.py`;业务代码禁止直接 import httpx 调模型
- 日志:`logging` 标准库,每行带阶段名(如 `score entry=42 s1=71 s2=68 selected=0`);密钥与全文内容不进日志
- 时间统一 UTC ISO8601 存库,展示层转 Asia/Shanghai

### 测试要求(pytest)

- **LLM 一律 mock**:单测零网络零花费;`llm.py` 本身用 httpx MockTransport 测
- 必测清单(每个 M1 任务的部分已被 M0 计划模式预演):URL 归一边界(追踪参数/微信四参/大小写)、评分和判边界(59+60 于 T1=60 落选/60+60 入选)、回执状态机全迁移(含 unknown 30min 放行一次)、三级预算窗口计数、frontmatter 契约(生成→Astro schema 过)、topic-digest schema 依赖(改字段名测试红)
- 测试文件命名 `test_<模块>.py`,fixture 复用放 `tests/conftest.py`(临时 SQLite 库)

## RAG/(M2)

- 服务骨架遵守 engine 的 Python 约定;`rag.db` 独立、可随时删除重建(spec §6)
- 检索双通道:命中必须带 `matched_by` 标注;embedding 端点失败自动降级 FTS
- `/ask` 响应必须附来源链接(文章路径或日报条目 URL)

## 提交与文档联动

- 改行为必查文档是否需要同步:pipeline/selection/budget 三份运营文档与代码不一致 = bug
- 新决策(哪怕小)写 ADR;模板 `docs/decisions/_template.md`
