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
| identity_key | URL 归一化后的判重键;参考 AIHOT 不机械移植:保留路径大小写与业务查询参数,候选追踪参数(utm_*、fbclid/gclid/spm/ref/from)逐项核实语义,微信特判等反例 M1 验证后定稿(spec §5.2) |
| receipt | 付费调用回执;状态机 pending/received/completed/failed/unknown |
| 幂等键(logical_key) | provider/endpoint/purpose/model/request_hash/attemptTag,防本地重复调度;不能保证供应商端exactly-once |
| receipt_attempt | 每次网络尝试的时间、额度预占、实际用量与未知结果;窗口按此计数 |
| budget | 三级次数10/100/400;另有月¥50/期¥1金额预占,任一档≤0停用 |
| analysis | append-only 评分记录(score_1/score_2/prompt_version) |
| override | 人工覆盖(force_include/exclude),优先于评分判断,不绕过来源/安全/预算 |
| digest_issue | 每期日报(date唯一;status draft/submitted/published/failed) |
| api_usage | 月度成本聚合 |

## 编辑策略(engine/selection.md)

| 词 | 含义 |
|----|------|
| tier / T1 / T2 | 信源编辑分级;门槛 T1=60、T2=75 |
| 和判均显 | 入选判据 `score_1+score_2 ≥ 2×threshold`,展示 `floor(平均)` |
| 双次评分 | 同prompt独立调用2次取均值判定,质量收益待样本验证 |
| 两清单 | "必须正常评价"与"必须压住"的内容清单 |

## 部署与运维

| 词 | 含义 |
|----|------|
| bare repo | `/opt/git/nanmu-blog.git`,接收 push 的裸仓库 |
| post-receive | push 触发的 hook:只认 main,后台有界等待锁并构建,失败显式重跑 |
| release / current | `releases/<sha>/dist` 版本目录;`current` symlink 指向当前版,`mv -T` 原子切换 |
| runbook | 核对现场前提后执行的运维手册(docs/ops/) |

## 协作纪律(spec §8.1)

| 词 | 含义 |
|----|------|
| session 记录 | docs/sessions/ 的会话交接:objective/state/disposition/next_action/omissions |
| verified / declared | 声明分级:verified 必带证据;declared 是未复核陈述 |
| omissions | 交接记录中"已知不知道什么"——最重要的字段 |
| live_state 核对 | 接手会话先跑验证核对交接声称的状态 |
| verify | Task7起的`npm run verify` = build + 冒烟;不包含TypeScript类型检查或服务器验收 |

## 外部系统

| 词 | 含义 |
|----|------|
| topic-digest | 上游数据源(在产,只读;docs/context/topic-digest-data-source.md) |
| nanmuli-blog | 前身项目(已废弃,反面教材;docs/context/project-background.md) |
| AIHOT / PowerContext | 外部参考项目(借鉴不引入;ADR 与 spec §11) |

## 容易混淆的状态

| 词 | 含义 |
|----|------|
| posts.draft | 文章是否排除构建产物;不负责Git内容保密 |
| digest_issue.draft | 日报文件已落盘,尚未确认远端接收;不是文章草稿开关 |
| .complete | release构建完成标记,不单独证明当前在线 |
| release.txt | 当前公开版本的Git SHA;还需核对目标页面内容 |
| 未决预占 / 实际结算 | 同一次attempt取已核实实付,否则保留预占;不相加重复计费,未知不等于零 |
