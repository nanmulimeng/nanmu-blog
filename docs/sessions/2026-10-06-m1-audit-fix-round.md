# 2026-10-06 M1 审计修复轮(8 项)交接

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

1. **跨模块核验**(用户既定要求):修复完成后做一次跨模块核验——四组修复的交界处(账本↔身份↔发布↔站点)是否仍有缝。
2. Task 25(部署环境核查)/Task 26(真实付费启用):**须用户当次显式授权**,不自动进入。
3. 台账:`.superpowers/sdd/2026-10-05-m1-engine-implementation/progress.md` 保留(用户指示不删),本轮记录在 "Audit round:" 各行。
4. 上轮 Deferred 清单更新:M7(UTC 月切)已被用户指出过时移除;W1 entry_ids='[]' minor 已随 P1-4 关闭;其余 Final minor 维持在案。
