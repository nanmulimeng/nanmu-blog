# 会话交接模板

> 复制本文件为 `YYYY-MM-DD-<主题>.md` 后填写。格式定义:spec §8.1;纪律:ADR-0008。
> 每个开发会话结束必须留一份——这是接手入口,必须与Git/文件/运行证据核对;只读审查不强制新建记录。
> `change_scope`、`verification`用于承载接续所需细节,短会话可并入state避免重复。`pending_runtime`与`decisions_needed`无内容可省略,omissions不可省略。

```markdown
# 会话交接:<主题>(YYYY-MM-DD)

- **recorded_at**: YYYY-MM-DD HH:mm Asia/Shanghai
- **continues**: 上一份交接的相对链接
- **repository**: HEAD、分支、未提交/已暂存/未推送状态
- **objective**: 本次会话的目标(一两句)
- **change_scope**:
  - 本轮修改:文件/职责/原因;未改变的任务边界
  - 接手时已有修改/暂存:范围及本轮是否触及;无法分离时如实说明
  - 外部操作:本轮授权覆盖的目标与实际执行状态(没有则写未执行)

- **state**:
  - 完成事项 1 [verified: commit哈希 / 验证命令、工作目录、退出码及输出摘要 / 文件路径]
  - 完成事项 2 [declared: 依据是 XXX,未复核]
  (声明分级:verified 必须带证据;declared 不得伪装成有证据)

- **verification**:

  | 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
  |--------------|----------------|----------------|
  | 仓库根 | 实际运行的命令 | 通过/失败/未运行/不适用;退出码或状态、关键输出;哪些能力未覆盖 |

- **pending_runtime**: 尚在运行的任务、进程/会话标识、如何查看结果或停止;本轮遗留临时文件与用途(无则省略)
- **decisions_needed**: 具体待决定事项、推荐路径、对目标的影响;哪些独立工作已继续(无则省略)

- **disposition**: continuable | blocked | complete

- **next_action**: 下一步(具体到任务/文件/验收;blocked 时写清卡点与需要的决定)。这只是接续建议,不自动授予提交/上线/付费权限

- **omissions**:
  - 已知未验证/缺失的事实或工作(显式声明"我不知道什么";跨会话断层的主要来源)
  - (没有也要写"无",不许省略本节)
```

## 写作要点

- 每条 state 陈述都标注 [verified: 证据] 或 [declared]——接手者据此决定信任度;可引用verification中的记录,不用复制长日志
- repository记录写作时的HEAD,不是尚未产生的“本次提交哈希”。保存本轮开始时的暂存/已有修改范围,结束时准确写明未提交/未推送;不凭缺少输出猜测已提交
- disposition只评价本轮objective。complete不表示整个里程碑完成;continuable须留下可执行下一步;blocked须说明外部前提。未验证不能写verified
- 本地修改、验证、提交、推送、线上生效分别表述;例如“push成功但线上SHA未确认”不能简写为“部署完成”
- omissions 是本记录最重要的部分:漏掉的坑比完成的清单更值钱
- 终态原则:正文只交代当前有效结果,历史理由链接到ADR;不堆积草稿/评审轮次。旧session不重写,新记录用continues接续
- 敏感信息脱敏,不粘贴密钥、完整环境变量或付费请求全文。证据保留定位所需的状态码、路径、SHA和摘要
- 接手按[workflow](../development/workflow.md)先核对本轮目标与工作区,再执行适用验证;与本文不符时在新记录纠偏。修改结束后更新入口链接,中断前尽可能先保存continuable记录
