# ADR-0008: 会话交接纪律写入手册

- 状态:已接受
- 日期:2026-10-02
- 关联:spec §8.1;模式来源 PowerContext Handoff

## 背景

nanmuli-blog 死因复盘包含跨会话上下文断层(项目一度无人知道真实状态,文档与代码漂移两个月无人发现——"9 月观测真空"是同类问题)。本项目大概率由 agent 分多个会话开发。

## 决策

`docs/sessions/` 每个开发会话一份交接记录(纯 markdown,不引入工具),字段:

- `objective` 本次目标
- `state[]` 已完成事项,**每条附证据**(commit/测试/文件路径),声明分级 **[verified: 证据] | [declared]**,declared 不得伪装成有证据
- `disposition` continuable | blocked | complete
- `next_action` 下一步
- `omissions` 已知未验证/缺失项——**显式声明"我不知道什么"**(跨会话断层的主要来源)

接手会话先 `git log` + 跑测试核对交接声称的状态(live_state 核对),不符先纠偏再动工。

## 理由

- PowerContext Handoff 模式验证过的字段设计;omissions 与声明分级是它对断层问题的核心解法
- 纯 markdown 零成本,agent 与人都能读写;已作为固定步骤写入 M0 计划(Task 9/10 收尾)

## 后果(代价)

- 每会话收尾多 5-10 分钟文档(相对烂尾风险,值得)
- 需要自律维持——用 plan 步骤强制(agent 执行计划时必然经过)

## 被否决的替代方案

1. 引入 PowerContext 工具化做会话记忆——等其 1.2-1.3 稳定期再评估;当前纪律先行
2. 不做交接纪律——重蹈 nanmuli-blog 覆辙,否决
