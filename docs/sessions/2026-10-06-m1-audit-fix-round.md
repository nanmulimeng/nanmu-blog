# 2026-10-06 M1 审计修复轮(8 项)+ 跨模块核验与交界缝修复轮 + 复核轮三处修复 交接

## 背景与授权

用户对 200aad0(Task 0-24 实现+整分支评审修复轮)审计,结论:**上轮四个账本 P1 可关闭,但 200aad0 不能认定"Task 0-24 全部验收完成",不建议进入 Task 25 部署或 Task 26 真实付费**。本轮提出 8 项问题(P1-1..P1-6、P2-7、P1-8),指示:合并成一批本地修复,按现有模块分工(账本与校准/内容身份与运行序/发布与恢复/站点产物验证),继续开发修复不退回全面设计审查,完成后做一次跨模块核验。台账(`.superpowers/sdd/`)保留不删;交接时更新 Agent 入口。

纪律红线延续:全部模型调用替身;上游 topic-digest 只读(mode=ro);不部署、不真实付费、不读真实 API key、不 push 真实远端;不启动 M2/M3;Task 25/26 需当次显式授权。

## 修复内容与提交映射

| 审计项 | 一句话 | 提交 |
|---|---|---|
| P1-2(Task 8/13/14/19) | reusable_scores identity_ctx 缺 system/参数字段;analysis/summary 查重缺输入绑定(换正文读旧结果) | 8d24fbe |
| P1-6(Task 17/18) | 可重试失败提前落 failed;单条输入失败挂整期 | 8d24fbe |
| P1-3(Task 22) | 校准缺 usage 仍 passed;logical_key 自拼;指纹绑 config 声明;预算预占口径 | e92a3e2 |
| P1-1(Task 21) | restore 切换前删活动库 -wal/-shm=已提交回执可能丢 | 8ff31be |
| P1-4(Task 17) | 纠错/重上仅凭 URL 可读判成功;W1 补记 entry_ids='[]' 丢成员事实 | 8ff31be |
| P1-5(Task 17) | 隔离只查未推送提交;提交不带文件身份校验;_sync_workdir fast-forward 判断反向 | 8ff31be |
| P2-7(Task 16) | escape 后裸 URL 经真实 Astro GFM autolink 仍成 `<a>` | 4df3174 |
| P1-8(Task 23) | digest/2026-10-04.md 夹具无隐藏机制,正常构建公开为正式日报 | 9e4d8e0 |

## 关键机制(实现层)

- **P1-1**:restore 五步序列 copy→set_flag→verify→checkpoint→switch;步骤④对活动库 `wal_checkpoint(TRUNCATE)`,busy≠0 或异常→OpsCommandError 中止不切换。测试用子进程 `os._exit(0)` 真实硬杀残留 WAL 帧(伪文件测试不算数)。
- **P1-4**:确认证据链=部署 SHA 树内 blob 身份(`_deployed_evidence`,None=路径应消失)+远端接收(`_is_ancestor`)+URL 可读,三者缺一保持未确认或转人工;URL 只是辅助信号。W1 entry_ids 从 `claim_issue` 反查,查不到成员→ManualIntervention,不写 '[]'。
- **P1-5**:提交用 pathspec(`git commit -- <rel>`,暂存区无关文件不带出);提交前 `_staged_sha`(`git show :rel`)校验暂存字节 sha=库内预期(Windows CRLF 下工作树原始字节经 clean 过滤后才可比);`_sync_workdir` 分支修正:head==origin 已同步 / base==head 落后→ff-only / base==origin 领先→等 push / else E8。
- **P1-6**:评分失败 statuses 含 retryable/unknown→return 4 保存进度续接;仅 no_retry 全灭→E6.all_failed。替身:500→retryable,400/401/422→no_retry,429/503→retryable。
- **P2-7**:反斜杠转义与数字字符引用(`&#46;`/`&#58;`)经项目实际安装的 @astrojs/markdown-remark 实测**均无效**(实体解码后 autolink literal 仍匹配);最终方案=在触发前缀连接点插入 U+200B 零宽字符(www‖`\.`、scheme‖`://`、邮箱本地部分‖`@`)。验收测试直接驱动真实渲染器,不再用自制子集渲染器。代价见台账 Ruling:断链字符可被复制(对恶意构造文本属防护)。
- **P1-8**:夹具 git mv 至 `site/tests/fixtures/`;`verify-fixture.mjs` 用 mkdtemp 临时副本(node_modules junction 复用,清理先 rmdir 摘链)注入夹具走真实 astro build+smoke;smoke.mjs 加泄漏检查(生产源目录出现 fixtures 同名文件报错;`NANMU_FIXTURE_BUILD=1` 上下文跳过)。顺带修正 Task 23"永久夹具入 digest 目录"的 Ruling(被审计推翻)。

## 验证证据

- engine 全套件:**294 passed**(226s,2026-10-06;含新增:真实 WAL 硬杀窗口、部署证据链、pathspec/暂存身份、ZWSP 真实渲染链)
- site:`npm run verify` 全链绿——生产构建 6 页(无夹具详情页)、RSS 零 2026-10-04 条目、泄漏检查(拷回夹具→优雅报错 exit 1,已验证检查本身能抓)
- 提交:200aad0 → 8d24fbe → e92a3e2 → 8ff31be → 4df3174 → 9e4d8e0(五提交精确列文件;mid-history 单提交不保证独立绿,tip 全绿为准)

## 接手事项

1. ~~跨模块核验~~ **已完成(2026-10-06,见下节)**:三路并行只读核验发现 7 处 P2+1 低危边缘交界缝,已按"继续开发修复"授权全部修复(TDD,四提交)。
2. Task 25(部署环境核查)/Task 26(真实付费启用):**须用户当次显式授权**,不自动进入。
3. 台账:`.superpowers/sdd/2026-10-05-m1-engine-implementation/progress.md` 保留(用户指示不删),本轮记录在 "Audit round:" 与 "Cross-module round:" 各行。
4. 上轮 Deferred 清单更新:M7(UTC 月切)已被用户指出过时移除;W1 entry_ids='[]' minor 已随 P1-4 关闭;其余 Final minor 维持在案。

---

## 跨模块核验与交界缝修复轮(同日接续)

三路并行只读核验(A 账本×校准 / B 发布×恢复 / C 安全×构建):核心安全命题(ZWSP×git 身份链恒等、Windows junction 穿越、探针×构建)无缝;交界处发现 7 处 P2+1 低危边缘,按模块本地修复(每项 RED→GREEN):

| 交界缝 | 一句话 | 提交 |
|---|---|---|
| A1 校准 replay | 只认 attempt_no=1——首发 unknown 过窗补发结算在 no=2,重跑判"未复用"重复付费 | 9075620 |
| A2 校准再发送 | 绕过 can_retry 三条件,origin 恒 initial;窗内应等待 | 9075620 |
| B-缝A W1 回填 | claim 全集≠产物成员,被剔除成员借 W4 清算置 used | 3808295 |
| B-缝C 线上自洽 | restore 回退 ops_json 后 correct 基于回退认知重建已撤回文件 | 3808295 |
| B-缝D 部署 SHA | 不可解析时 None==None 把"无法验证"误判"已删除",撤回误确认 | 3808295 |
| B-边缘 ff merge | 重叠暂存致 merge rc=1→RuntimeError 逃逸异常协议(无 fail 行/无 E8) | 3808295 |
| B-缝B 清算口径 | 发布主链 final_keys=fsr.final 全员 vs 恢复路径 entry_ids(ready)双口径 | b1155c4 |
| C1 Linux 清理 | symlinkSync junction 在 Linux 退化为普通 symlink,rmdir 恒 ENOTDIR→每次部署残留 /tmp 副本 | a68cae2 |

机制要点:A1 replay 取最新带 usage 的 attempt(2026-10-07 复核轮已修正为仅 `status='received'`,见下节);A2 同构 `score._attempt_side`(recover_stale_pending+can_retry,unknown_wait 单列状态);缝A 以产物 markdown 内容反解成员(成员 `safe_source_url` 出现在产物文本=进产物;复核轮已改链接目标精确匹配,见下节);缝C `_assert_remote_consistent`(withdraw/correct 期望在线、relist 期望已消失,不一致转人工);缝D `git cat-file -e deployed^{commit}` 前置;缝B `final_keys` 排除 `draft.safety_excluded`;C1 摘链接两步制(rmdir→rmSync 非递归),链接未摘除绝不 `rmSync(recursive)`。

- **B-缝B 可达性说明**:采集侧 normalize R0 scheme 白名单本就把 javascript URL 挡在 entry 表外(正常链路 safety_excluded 几乎不可达);该修复属防御性口径统一,e2e 测试用直插 entry 构造。
- **C1 验证边界**:Linux 分支行为在 Windows 开发机不可复现,验证=Windows `npm run verify` 全链回归绿+tmp 零残留+清理逻辑推演(Ruling 在台账);服务器首跑可观察。
- 验证:engine 全套件 **301 passed**(192s,含 7 个新交界测试);site `npm run verify` 全链绿。
- C 路核验另附 5 处 P3 deferred(台账 "Cross-module round: minor (deferred)" 各行:夹具日期撞车误报窗、杂散合规 .md 无清单校验、崩溃路径 tmp 残留、人工删除提示未警告活链接、探针 dotfile/并发 flaky)。


---

## 复核轮(2026-10-07,用户复核 00950e8 后限定三处)

用户复核结论:`00950e8` 主要修复成立、301 测试实跑通过,但 2 个 P1+1 个 P2 未闭合,暂不进入正式部署与真实付费;本轮只修三处,不重开总体设计与已关闭项。三项全部 TDD 修复(RED→GREEN→全套件),本地替身环境完成,零网络零付费:

| 项 | 缺陷 | 修复 | 测试(RED→GREEN) | 提交 |
|---|---|---|---|---|
| P1 校准 replay 有效性 | replay 只查 `usage_json IS NOT NULL`——HTTP 400 body 带 usage 时 `record_failure` 也写 usage_json,带 usage 的失败回执被当通过证据,重跑直接 passed+`calibration_effective=true`(一次失败请求变成正式付费链路的校准许可) | replay 加 `a.status='received'`:通过证据=成功 attempt 且带 usage,与首次消费条件统一;失败回执仍是费用证据(usage_json 保留)但不作通过样本,重走 can_retry(no_retry 拒,stopped=`resend_error_class_no_retry`) | `test_calibration_failed_attempt_with_usage_not_pass_evidence`(400+usage 首发拒;重跑零网络+attempt 不增+不 passed;关连接重开判定一致) | 10b10b8 |
| P1 校准预算口径 | `_calibration_spent_micro`="已结算取 actual"——每样本实付极低(如 240 微元)时 6000 预算下累计预占 11606 仍 passed,违反契约"按预占值批准的调用量上限" | 改 `SUM(reserved_micro_cny)` 全部 calibration attempt:授权口径=已批准预占累计,不因结算回落(model-calls.md §3 规则 11) | `test_calibration_budget_limits_approved_reservations`(6000 微元→`budget_exhausted`,0<attempt<4,累计预占≤上限) | 10b10b8 |
| P2 W1 URL 子串反解 | `safe_source_url(url) in text` 子串匹配——A url=`https://e.com/a` 是 B url=`https://e.com/ab` 的前缀,产物只含 B 但恢复 [A,B],W4 后 A/B 均 used | 提取产物全部 `](url)` 链接目标集合(`re.findall`),成员 safe_url 精确集合成员判定;`len(ids)`!=`len(links)` 转人工(无法唯一确认成员清单不以部分命中回填;不扩建版本表或恢复平台) | `test_w1_backfills_only_members_in_artifact` 改造前缀陷阱(A rejected/B used);`test_w1_member_count_mismatch_with_artifact_links_goes_manual`(链接 2/命中 1→转人工且无行落库) | 3b74a5d |

- 验证:engine 全套件 **304 passed**(301+3 新增,259.82s,2026-10-07 实跑);RED 阶段四测试均按预期失败且失败点=缺陷本身(重跑误 passed / 预算全放行 passed / 子串恢复 [A,B] / 无数量校验 DID NOT RAISE)。
- 既有测试兼容:A1 轮 `test_calibration_replay_uses_latest_settled_attempt` 的 attempt_no=2 是 received 不受 status 条件影响;两预算测试(probe reserved/极小上限 1)在 SUM(reserved) 口径下语义不变,均实跑确认仍绿。
- 上节"机制要点"A1/缝A 两处描述已按本轮实现更正(勘误括注)。
- 接手不变:Task 25/26 须用户当次显式授权;Linux 清理分支留 Task 25 现场验证;台账追加 "Review round:" 四行。
