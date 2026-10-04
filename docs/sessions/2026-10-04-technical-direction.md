# 会话交接:技术契约修订与开发方向(2026-10-04)

- **recorded_at**: 2026-10-04 15:54 Asia/Shanghai
- **continues**: [M0 Task2-8实施](2026-10-04-m0-task2-8.md);承接其后只读文档审查结论,旧交接保持历史快照。
- **repository**: main,HEAD `109e3dc`;接手时工作区/暂存区干净。本轮仅修改文档并新增本记录,未暂存、未提交、未推送;未查询远端最新状态。
- **objective**: 落实用户接受的审查建议,修正文档技术/功能契约,明确后续开发顺序和阶段进入条件。
- **change_scope**:
  - spec维护产品/内容边界与阶段策略;engine/design统一请求、配置、错误、重试、URL判重与预算计算,运营文档跟随对应口径。
  - M0 plan新增未勾选Task8a;quality-gates/workflow/writing补原始路径和缓存检查;根入口、索引、环境和架构同步真实阶段。
  - 未修改site/deploy实现、依赖锁文件、检查工具或历史session;未安装依赖、连接服务器、调用模型或发布。

- **state**:
  - 原始路径与缓存问题已进入契约和Task8a,尚未修复代码。[verified: 当前site/src/lib/content.ts仍只校验entry.id;site/package.json仍直接astro build后smoke;本记录下表区分文档处置与实现状态]
  - M0→M1→M2进入条件、交付边界与调整策略统一写入spec §9,未另建路线图/M1/M2实施计划。[verified: spec §9.1-9.2]
  - 以下审查建议已落实到对应文档;示例和链接验证结果见verification。[verified: 本轮diff]

  | 审查事项 | 本轮文档处置 | 后续实现/验收 |
  |----------|--------------|----------------|
  | slug/自动清洗绕过原始路径限制 | spec禁止slug,检查原始相对路径及入store前冲突;计划新增Task8a | Task8a代码与正反例待做 |
  | 删除最后一篇后旧store残留 | quality-gates定义手工恢复和连续构建回归,writing/pipeline引用 | Task8a正式构建/dev入口修复待做 |
  | 多入口阶段过时 | README/AGENTS/docs索引/架构/写作/部署统一Task1-8已实施、8a与9-10待做 | 上线证据仍需Task9-10 |
  | SDK extra_body混入HTTP body | design给出顶层thinking的原始JSON、usage/finish_reason及mock断言 | M1客户端与替身测试 |
  | 合法停用被误判配置错 | 字段级校验,限额≤0停增但保留结算/复用/发布,下一授权前响应配置变化 | M1 config/ledger测试 |
  | 错误映射/重试口径冲突 | 单一错误矩阵、持久化普通/unknown计数及总attempt上限、退出码与通知边界 | M1恢复字段映射和故障注入 |
  | 百万token金额单位与次数预留 | 整数向上取整、摘要/纯重试分别预留、9600微元与N=34算例 | M1预算单测和实际计量核对 |
  | URL归一与上游行为不同 | 标明本项目默认端口/尾斜杠规则,增加固定样例与上游可变来源边界 | M1固定引用commit、序列化与反例测试 |

- **verification**:

  | 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
  |--------------|----------------|----------------|
  | 仓库根 | `python scripts/check_docs.py --snippets --bash D:/software/Git/Git/bin/bash.exe --node D:/software/JavaWab/nodejs/node.exe` | exit0;43份Markdown、129本地链接、8表DDL、schema示例一致;Bash2/JS4/JSON2/冒烟夹具6,errors和warnings均空。为允许Node读取临时目录使用批准的沙箱外检查,不部署/联网 |
  | 仓库根 | PowerShell here-string经`python -`读取engine/design代码块,PyYAML解析3块、json解析1块并断言HTTP顶层字段 | exit0;thinking=disabled、无extra_body、json_object、stream=false、输出上限与budget示例一致;仅验证示例,未实现客户端 |
  | 同上Python检查 | 从YAML取价目/token/预留参数执行整数计算,检查小额向上取整与耗尽 | 单次9600微元;N_money=34、N_hour=40、N_day=190、N=34;1 token×1微元/M进位为1微元,负余额候选归0。仅算例,不是运行预算闸门测试 |
  | 同上Python检查 | 用check_docs的schema提取器对比spec与实际site/src/content.config.ts | 两份schema一致;禁slug/原始路径属于Task8a待实现的额外约束 |
  | 仓库根 | `git -c core.safecrlf=false diff --check`、diff/stat/status核对 | exit0,无空白错误;仅18份现有Markdown修改及本记录新增,site/deploy/锁文件/工具和历史session无diff;暂存区为空 |

- **disposition**: complete(本轮文档契约与策略修订已完成并通过适用检查,不代表M0或未来引擎已验收)
- **next_action**: 开发接续首项是M0 Task8a,按独立临时副本复现→最小修复→真实构建正反例→更新状态推进;通过后才进入Task9-10。该建议不自动授予提交、部署或付费权限。
- **omissions**:
  - 本轮是文档调整,未把先前审查中的临时Astro复现重跑为新结果;代码缺陷仍在,Task8a保持未勾选。
  - 本轮未重跑站点build/verify、浏览器或Linux部署;上一实施/审查的通过结果仅代表当时覆盖,不证明本轮新边界已实现。
  - DeepSeek/AIHOT外部依据沿用同日此前审查读取,未进行真实账户调用;价格、输入上界、供应商计量与源commit在M1计划时复核。
  - M0 Task9-10、线上环境/DNS/SSH/Caddy、真实发布和回滚未验收;M1/M2代码尚未创建,运行及付费结果均未知。
