# ADR-0005: 付费调用治理——回执先行 + 幂等键 + 三级预算熔断

- 状态:已接受
- 日期:2026-10-02
- 关联:spec §5.4 / 铁律 5;模式来源 AIHOT

## 背景

月预算红线 ¥50 的个人项目,任何一次失控(重试风暴、崩溃后重复扣费、prompt 回归变长)都不可接受。

## 决策

- **回执先行**:每次付费调用前 INSERT receipt(状态 pending);响应先落库(received→completed)再做业务写——崩溃后可复用已付费结果
- **幂等键**:`service:purpose:model:sha256(stable_json(identity)):attemptTag`,UNIQUE 约束防重复扣费
- **五状态机**:pending→received→completed;pending→unknown(超时/结果不明);unknown→failed(≥30min 自动放行,每条只放一次,二次必须人工);failed→pending(重试前先复查预算)
- **三级预算**(次数,滑动窗口计数):per_minute=10 / per_hour=100 / per_day=400,任一超限抛错,任一档 ≤0 = 立即停用
- 月红线 ¥50 由日预算逼近 + api_usage 月聚合超 ¥40 告警兜底

## 理由

- AIHOT 生产模式,直接移植
- 按次数而非按金额熔断:次数是稳定代理,不需维护单价表(单价会变,调用次数不会)

## 后果(代价)

- 每次调用多一次本地 SQLite 写(微秒级,可忽略)
- 状态机实现与测试成本(M1 计划内消化)

## 被否决的替代方案

1. 只记账不熔断——失控风险不可接受,否决
2. 按金额实时熔断——需维护各模型单价表且计价粒度不便,否决
