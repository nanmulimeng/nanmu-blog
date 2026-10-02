# 会话交接模板

> 复制本文件为 `YYYY-MM-DD-<主题>.md` 后填写。格式定义:spec §8.1;纪律:ADR-0008。
> 每个开发会话结束必须留一份——这是接手者唯一可靠的状态来源。

```markdown
# 会话交接:<主题>(YYYY-MM-DD)

- **objective**: 本次会话的目标(一两句)

- **state**:
  - 完成事项 1 [verified: commit 哈希 / 测试输出 / 文件路径]
  - 完成事项 2 [declared: 依据是 XXX,未复核]
  (声明分级:verified 必须带证据;declared 不得伪装成有证据)

- **disposition**: continuable | blocked | complete

- **next_action**: 下一步(具体到任务/文件;blocked 时写清卡点与需要的决定)

- **omissions**:
  - 已知未验证/缺失的事实或工作(显式声明"我不知道什么";跨会话断层的主要来源)
  - (没有也要写"无",不许省略本节)
```

## 写作要点

- 每条 state 陈述都标注 [verified: 证据] 或 [declared]——接手者据此决定信任度
- omissions 是本记录最重要的部分:漏掉的坑比完成的清单更值钱
- 终态原则:不引用草稿/评审轮次/被否决的决策
- 接手会话第一步:`git log` + 跑 `npm run verify` 核对本文声称的状态(live_state 核对),不符先纠偏再动工
