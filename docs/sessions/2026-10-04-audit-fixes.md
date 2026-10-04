# 会话交接:文档审查核验与小修(2026-10-04)

- **recorded_at**: 2026-10-04 12:52 Asia/Shanghai
- **continues**: [Agent开发文档完善](2026-10-04-agent-development.md)
- **repository**: 写时 HEAD `74c23f8`,分支 main;接手时已有 2026-10-02~04 的 4 轮未提交文档修订(约 35 文件,暂存区为空)。本轮追加 2 处文档修正、3 处入口链接与本记录;用户随后授权将累计修订一次性提交并推送 GitHub origin(main),本记录随该提交入库,提交与推送结果以 git log 与远端为准。
- **objective**: 对 4 轮未提交文档修订做逐份审查核验(只读);按审查结论修复其中 2 处小瑕疵。

- **change_scope**:
  - 本轮修改:glossary `identity_key` 行对齐 spec §5.2 契约措辞;AGENTS 项目结构 `engine/` 行补"尚未创建"标注;README/AGENTS/文档索引三处最新交接入口指向本记录;新增本文档。
  - 接手时已有修改:4 轮修订全部未提交(范围见各轮 session 的 change_scope);本轮仅追加上述行级修正,未触碰历史 session、ADR 与 M0 计划。
  - 外部操作:未执行服务器、发布或付费操作。

- **state**:
  - 38 份文档逐份读回核验:状态口径、sessions `continues` 链、ADR 有效口径头与勘误节、关键数字交叉(8 表 DDL、¥50/¥40/¥1、次数 10/100/400、门槛 T1=60/T2=75、保留 5 个 release、幂等键格式)、部署脚本与 deploy.md 互检,结论为内部一致、检查可自证、M0 Task 2 可开工 [verified: 核验命令见 verification,结论已在对话中交付]
  - 独立复核 2026-10-04 修订的 systemd 结论:v239 手册原文支持日历事件 IANA 时区后缀,此前"239 不支持时区后缀"的说法为误,修订方向正确 [verified: v239 man/systemd.time.xml 原文含 "timezone in the IANA timezone database format" 与 `Mon *-*-* 00:00:00 Pacific/Auckland` 示例]
  - glossary.md `identity_key` 行补齐"不机械移植/保留路径大小写与业务查询参数/逐项核实语义/M1 反例验证后定稿"限定,消除与 spec §5.2 的口径差 [verified: 修改后读回]
  - AGENTS.md `engine/` 行补"尚未创建",与 `site/`、`deploy/` 行标注对称 [verified: 修改后读回]
  - 第 3 处审查发现(topic-digest-data-source.md:16 "读近 24-48h 窗口足够")经评估与契约口径"fetched_utc 近48h"相容,按审查结论不改;ADR 正文旧表述均在有效口径头/勘误节覆盖内,属有意保留

- **verification**:

  | 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
  |--------------|----------------|----------------|
  | 仓库根 | `python scripts/check_docs.py` | 通过;退出码 0,39 份 Markdown、本地链接、8 表 DDL 可执行、spec↔plan schema 一致,errors/warnings 为空。仅覆盖文档结构与既有契约,不代表应用已构建 |
  | 仓库根 | `git -c core.safecrlf=false diff --check` | 通过;退出码 0,无输出。命令级选项仅消除换行转换提示,未改 Git 配置 |

  本轮未改 M0 计划代码片段,未复跑 `--snippets`。

- **disposition**: complete(本轮审查与 2 处修正完成)
- **next_action**: 提交推送完成后按 M0 计划从 Task 2(Astro 脚手架)开始;服务器 bare repo 与 server remote 属 Task 8-9,GitHub origin 只是开发机代码副本,不等于部署、engine/rag 数据或灾难恢复备份。
- **omissions**:
  - 审查报告全文仅在对话中交付,未落盘 reviews/(只读审查不强制写盘;结论要点已在 state 摘要)。
  - site/engine/deploy 均不存在;未运行 Astro 构建、engine 测试、服务器访问或付费调用。累计提交与 GitHub 推送的实际结果以 Git 与远端为准,本记录不代为声称成功。
  - systemd OnCalendar `Asia/Shanghai` 后缀在目标服务器的实际行为仍待 M1 部署时以 `systemd-analyze calendar` 与 next elapse 实测(设计口径已按 v239 支持时区后缀修正)。
