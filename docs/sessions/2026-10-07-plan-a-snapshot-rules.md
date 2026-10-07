# 方案 A 规则:上游 Online Backup 快照的完成识别与时效(2026-10-07)

授权范围:仅规则与接线准备(上游代码/服务/权限不变,不新增快照平台);
timer 继续 disabled;本文件不含真实付费授权。

## 背景(证据分类)

- **本地代码证据**:`engine/src/nanmu_engine/collect.py`(resolve 规则与测试);
  本地 `tests/test_collect.py` 五场景。
- **服务器现场证据**(2026-10-07 只读核实,未修改上游):
  - `/opt/topic-digest/src/topic_digest/backup.py` 第 19/27 行:**先创建最终
    文件名再执行 `conn.backup()`** → 文件名、存在、短时间大小不变都**不能
    单独证明备份完成**;写一半的残留件也叫最终名。
  - nanmu(无特权)`journalctl -u topic-digest-backup.service` 可读;最近
    成功任务:systemd `Result=success`/`ExecMainStatus=0`(2026-10-07
    03:35:02 CST),stdout 行 `backup -> /opt/topic-digest/backups/
    topic-digest-20261006T193501.db; pruned 1`。
- **外部官方依据**:SQLite Online Backup API 文档(事务一致快照);
  immutable=1 语义(调用者保证文件不变)仅适用于 append-only 快照件,
  活库禁用。

## 规则 1:已完成备份的选择依据

**完成证明=任务级证据链,不以读取成功/完整性检查替代:**

1. **任务成功**(唯一完成证明):`journalctl -u topic-digest-backup.service`
   倒序找最近一条**成功 invocation** 的 `backup -> <绝对路径>; pruned N`
   stdout 行——把具体备份文件与成功完成的备份任务关联起来。invocation
   结局判定:stdout 行之后(时间序)同轮出现 `Succeeded`/`Deactivated
   successfully` = 成功;`Failed` = 失败,继续倒序;无结局行(任务仍在
   跑,stdout 先于进程退出打印)= 进行中,跳过该行取更早成功件。
   - 正在生成备份 ⇒ 用上一份成功件(其年龄受规则 2 约束);
   - 最新备份失败且有残留文件 ⇒ 残留件没有成功行背书,不会被选中,
     回退上一份成功件;残留文件的名字"最新"不构成任何优势——**引擎
     从不"取目录最新 .db"**。
2. **关联文件落地防线**(全部满足才作 immutable 输入;这是防线,不是
   完成证明——防 journal 说成功但文件被事后破坏/替换):
   路径在配置目录内;名字严格匹配 `topic-digest-YYYYMMDDTHHMMSS.db`;
   文件存在;mtime 与名字时戳一致(容忍 300s,backup 秒级完成);
   `mode=ro&immutable=1` 可开;`quick_check` ok;窗口 schema 可查
   (item/source 契约)。防线不过 ⇒ E2 停止(不倒退找更旧件——journal
   与文件不一致属环境异常,需人工看)。

## 规则 2:时效与失败处置

- **年龄上限 48h**(名字时戳=备份内容时点):03:30 备份/08:30 日报
  节奏下,正常≈5h;错过一夜≈29h 仍可用;两夜无成功件即停。
- **停止行为**:`CollectError`(E2)——digest_issue failed + exit 3 +
  原因进日志;不降级(不直读活库、不取无完成证明的件)。
- **数据延迟语义(撤回此前"48h 窗口不丢条目"的说法)**:错过备份的
  数据最迟**次日 08:30** 处理,延迟接近 **29 小时**;备份或调度异常时
  延迟无上界,直到年龄上限触发 E2 停止、人工干预。
- **日志**:选中件记录 `snapshot_resolved`(file/内容时戳/年龄/关联
  任务);逐件拒绝记 `snapshot_rejected`(原因);停止事件带原因
  (过旧/证据不足/证据通道不可读)。

## 取舍

- 只取"最近一次成功"关联件,防线不过即停:牺牲一点可用性,换取
  "完成证明→文件"单链责任,失败面小而可诊断。
- journal 为唯一完成证据通道(辅以文件防线):systemctl show 不必依赖
  (journal 行已含 invocation 结局);通道不可读=权限缺口报告,不改上游。

## 验收条件(测试五场景,tests/test_collect.py)

1. 备份仍在生成(最近 stdout 行无成功结局)→ 跳过,用上一份成功件;
2. 备份失败残留(失败 invocation 的 dest 文件在目录且名字最新)→
   不选残留,取上一份成功件;
3. 有效已完成备份(journal 成功行+文件防线全过)→ 选中,日志含
   身份与年龄;
4. 快照过旧(最近成功件年龄>48h)→ E2"快照过旧"停止;
5. 没有可用快照(无成功行/文件缺失/防线不过/通道不可读)→ E2 停止。
