# 术语表

新 agent 快速对齐词汇。按主题分组;详细定义见链接。

## 里程碑

| 词 | 含义 |
|----|------|
| M0 | 博客上线(Astro 站 + git 写作流 + 子域名) |
| M1 | AI 引擎:collect→评分→摘要→日报发布全链 + 成本治理 |
| M2 | RAG:向量索引 + `/ask` 自用问答 |
| M3 | 可选扩展(周报/热度/事件聚簇)——**只记录不动工**(铁律 1) |

## engine 数据模型(8 表,spec §5.3)

| 词 | 含义 |
|----|------|
| entry | 候选条目快照;`identity_key` 唯一判重 |
| identity_key | URL 归一化后的判重键(AIHOT 式:去追踪参数/参数排序/微信特判) |
| receipt | 付费调用回执;状态机 pending/received/completed/failed/unknown |
| 幂等键(logical_key) | `service:purpose:model:sha256(identity):attemptTag`,防重复扣费 |
| budget | 三级预算(10/100/400 次 per min/hour/day),任一档 ≤0 = 停用 |
| analysis | append-only 评分记录(score_1/score_2/prompt_version) |
| override | 人工覆盖(force_include/exclude),优先于一切自动判断 |
| digest_issue | 每期日报(date 唯一;status draft/published/failed) |
| api_usage | 月度成本聚合 |

## 编辑策略(engine/selection.md)

| 词 | 含义 |
|----|------|
| tier / T1 / T2 | 信源编辑分级;门槛 T1=60、T2=75 |
| 和判均显 | 入选判据 `score_1+score_2 ≥ 2×threshold`,展示 `floor(平均)` |
| 双次评分 | 同 prompt 独立调 2 次抑制方差(AIHOT 模式) |
| 两清单 | "必须正常评价"与"必须压住"的内容清单 |

## 部署与运维

| 词 | 含义 |
|----|------|
| bare repo | `/opt/git/nanmu-blog.git`,接收 push 的裸仓库 |
| post-receive | push 触发的 hook:只认 main,flock 后台构建 |
| release / current | `releases/<sha>/dist` 版本目录;`current` symlink 指向当前版,`mv -T` 原子切换 |
| runbook | 逐字可执行的运维手册(docs/ops/) |

## 协作纪律(spec §8.1)

| 词 | 含义 |
|----|------|
| session 记录 | docs/sessions/ 的会话交接:objective/state/disposition/next_action/omissions |
| verified / declared | 声明分级:verified 必带证据;declared 是未复核陈述 |
| omissions | 交接记录中"已知不知道什么"——最重要的字段 |
| live_state 核对 | 接手会话先跑验证核对交接声称的状态 |
| verify | `npm run verify` = build + 冒烟,commit 门槛 |

## 外部系统

| 词 | 含义 |
|----|------|
| topic-digest | 上游数据源(在产,只读;docs/context/topic-digest-data-source.md) |
| nanmuli-blog | 前身项目(已废弃,反面教材;docs/context/project-background.md) |
| AIHOT / PowerContext | 外部参考项目(借鉴不引入;ADR 与 spec §11) |
