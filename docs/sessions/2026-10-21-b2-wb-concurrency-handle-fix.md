# 会话交接:工作台批 1 定点修正——并发 list 缺陷与句柄释放(2026-10-21)

- **recorded_at**: 2026-10-21 18:05 Asia/Shanghai
- **continues**: [批 1 实施交接](2026-10-21-b1-workbench-batch1-implementation.md)
- **repository**: 分支 `workbench-batch1`,基线 e002691(与审计起点一致,无中间提交);本轮两提交 a7d0cf1/3686ee2+本文档;未合并 main、未推送、未部署
- **objective**: 修复审计确认的确定性并发缺陷(list 删保存中 tmp→save ENOENT)+定位并消除 DEP0137 句柄警告;不新增功能,不进批 2

## 结论

**完成,停在待审计复核**。两项缺陷均先在旧实现上复现/目睹测试失败(RED)再做最小修正,修复后接口 34/34+浏览器 e2e 22/22+DEP0137 警告清零。

## B1:列表与保存并发缺陷

**审计结论核实属实**:[drafts.js](../../workbench/src/drafts.js) 旧实现 `list()` 直接调 `#readCurrent()`(不入 slug 队列),而 `#readCurrent` 开头 `rm draft.json.tmp`。临时调试脚本(已删,不入库)在独立临时目录完整复现审计五步:save 停在「tmp 写完+fsync、rename 未执行」→并发 list 删掉 tmp→rename 放行→**save ERR:ENOENT,磁盘停留 v1 rev1,本次修改丢失,list 返回旧版**。

**最小修正**([a7d0cf1](../../workbench/src/drafts.js)):`list()` 内改为 `enqueue(ent.name, () => #readCurrent(ent.name))`——与保存/删除同队列串行。满足审计五条要求:普通读取不再清理活动写入的文件(队列内无并发写者);同 slug 读/存/删协调一致(同一 `enqueue`);无嵌套排队(list 在队列外逐 slug 入队,不嵌套);tmp 残留恢复语义不变(队列内清理时机未动);列表与保存均正常结束(测试断言)。

**回归测试设计**(drafts.test.js「回归:列表读取不得干扰进行中的保存」):
- 同步屏障一:patch `fs.promises.rename`,把 save 确定性停在 rename 前(拦截器同步置位+setImmediate 轮询等待,不靠 sleep 碰撞);
- 观测信号:patch `fs.promises.rm` 监听**屏障期间**对该 tmp 的删除(`renameArrived` 守卫)——**首跑教训(如实)**:无守卫时信号被 save 自身写 tmp 前的残留清理 rm(空删除)误触发,放行过早,list 的真实 rm 落在 rename 之后,旧实现伪 GREEN;加守卫后正确复现:旧实现 `保存应成功,得 500`(RED),修正后全过;
- 修正后语义:list 排队等 save 完成,返回新版 rev;1s 观测窗仅用于兼容两实现路径(新实现下并发删除在语义上不可能发生,非概率等待)。

## B2:文件句柄关闭警告(DEP0137)

**来源定位**:
- **已复现主来源**=目录句柄:每次保存的「尽力 fsync 目录」在 Windows 上 `dfd.sync()` 抛错,旧代码直接跳过 `dfd.close()`→每次保存泄漏 1 个目录句柄;修复前 `npm test` 32/32 但大量 `Closing file descriptor N on garbage collection`(fd 3-11 多批,与保存次数吻合)。
- **源码推断同构缺口**(未自然复现,结构同修复):主 tmp 句柄与 prev 句柄的 `sync()` 若抛错同样跳过 `close()`——异常路径无 finally。

**最小修正**([3686ee2](../../workbench/src/drafts.js)):`#atomicReplace` 三处句柄统一 `try { sync() } finally { close().catch(()=>{}) }`——成功与异常路径都显式释放;Windows 目录 sync「尽力而为」边界保留,未宣称全平台验证;未隐藏警告、未用强制退出掩盖;不重构无关模块。

**针对性测试**(drafts.test.js「句柄释放」):patch `fs.promises.open` 收集全部 FileHandle,双注入——目录句柄 sync 抛错(Windows 实况同构)+tmp 文件句柄 sync 抛错(段3)→断言两次成功保存+一次 500 失败保存后,全部句柄已关闭。**判据教训(如实)**:Node 22 的 FileHandle 无 `closed` 属性(恒 undefined),首次断言用 `!h.closed` 永真;实证 close 完成后 `fd` 置 -1,改用 `fd !== -1` 判泄漏。修正判据后用 stash 撤销实现复验 RED:旧实现真泄漏 fd=5,6,7(两个目录句柄+注入 tmp 句柄)被抓住,恢复后全绿。prev 句柄的 sync 异常路径未单独注入(与 tmp 结构同构,finally 同款覆盖),如实标注。

## 实际验证

| 环境 | 命令 | 结果 |
|---|---|---|
| workbench(修复前) | `npm test` | 32/32 pass,**大量 DEP0137/Closing 警告**(基线复现,输出比对留档) |
| workbench(B1 RED) | `npm test`(仅新增回归测试) | 旧实现 FAIL:「保存应成功,得 500」;修正后该测试过(33/33) |
| workbench(B2 RED) | `npm test`(句柄测试) | 首断言 `closed` 属性缺陷→修正判据;stash 撤实现复验:泄漏 fd=5,6,7 FAIL;恢复后过 |
| workbench(修复后) | `npm test` | **34/34 pass,0 fail**,完整输出 grep `Closing file descriptor|DEP0137` 计数 **0**(日志 /c/tmp/wb-npmtest-after-fix.log) |
| site(复用 Playwright) | `python -I ../workbench/tests/e2e_browser.py` | **22/22 PASS**(A-G 全组:保存/失败提示与补救恢复/双窗口冲突/重开一致/周期与防抖/登出/日志脱敏) |
| 仓库根 | `git diff --check` / `python scripts/check_docs.py` | exit 0 / 0 错 0 警 |

同 rev 冲突、中断恢复(tmp 丢弃/prev 回退)、保存失败不误标、DELETE、slug 不触盘等既有断言全部保留并通过(34/34 内)。

## 修改范围核对

`git diff e002691..HEAD --stat`:仅 `workbench/src/drafts.js`(+30/-9)与 `workbench/tests/drafts.test.js`(+90)+本文档与 AGENTS 状态句;未动 engine/deploy/site/服务器/公开站。

- **disposition**: complete(本轮两项定点修正),整体停在**批 1 定点修正待审计复核**
- **next_action**: 审计复核;通过后批 2(真实构建+静态预览)仍待用户明确指示
- **omissions**:
  - prev 句柄 sync 异常未单独注入(结构同构覆盖,见上)
  - 真实时间流逝的 12h 过期/15min 限速等待、真机环境沿批 1 交接口径不变
  - 临时调试脚本 debug-concurrency.mjs 已删,复现步骤以本文记录的屏障设计为准
