# 成本治理

> 状态:定稿 2026-10-02。月度台账按月追加——本文件是成本事实的唯一记录处。

## 红线

- 月度 LLM 总成本红线 **¥50**
- api_usage 月聚合超 **¥40** 触发告警(OnFailure 通知渠道)
- 参考量级:同类日报管线实测 ~$0.01/天——红线非常宽裕,熔断是防失控不是防常态

## 三级预算(次数,滑动窗口计数)

| 档 | 初始值 | 超限行为 |
|----|--------|----------|
| per_minute | 10 | 抛错,retryAfter 60s |
| per_hour | 100 | 抛错,retryAfter 600s |
| per_day | 400 | 抛错,本期中止 |

- 统计口径:receipt.attempts 近 1min / 1h / 24h 滑动窗口总和
- 任一档 ≤0 = 立即停用该服务(运维熔断开关)

## 回执状态机摘要(详设 spec §5.4)

```
pending → received → completed   响应先落库再做业务写,崩溃可复用已付费结果
pending → unknown                超时/结果不明
unknown → failed                 ≥30min 自动放行一次;二次必须人工
received → failed                响应不可解析
failed → pending                 重试(attempts+1,先复查预算)
received/completed               直接复用,零网络调用
```

幂等键:`service:purpose:model:sha256(stable_json(identity)):attemptTag`

## 月度台账

| 月份 | provider/model | tokens(in/out) | 成本(¥) | 备注 |
|------|----------------|----------------|---------|------|
| 2026-10 | (M1 上线后开始记录) | | | |

定价基准(2026-10,变动时更新本表):DeepSeek chat 输入 ¥1/M(cache 未命中)、输出 ¥2/M;bge-m3 免费。
