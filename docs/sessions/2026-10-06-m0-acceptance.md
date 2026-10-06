# 会话交接:M0 验收通过,首篇文章上线与 tag m0(2026-10-06)

- **recorded_at**: 2026-10-06 11:57 Asia/Shanghai
- **continues**: [resume-implementation](2026-10-06-resume-implementation.md)
- **repository**: 写作时 HEAD=03015b1(main,已推 server 未推 origin),工作区新增 [evidence/2026-10-06-m0/](../evidence/2026-10-06-m0/) 三张验收截图(未提交);本 session 与三指针更新在其后一次 commit
- **objective**: 完成 M0 Task 10 收尾——首篇文章按用户收窄表述修正后真实发布,线上验收(计时/RSS XML+真实订阅/明暗主题),持锁回滚演练并恢复,验收交接与 tag `m0`

## 用户授权范围(2026-10-06,本轮执行的依据)

文章唯一修改:替换"一直运行到现在,采集十五个信息源"为收窄句(15 源属上一会话记录、线上状态未复核);其余正文保留,改后复跑 verify 无需再交文章评审。整体授权①—④连续推进:①push server main;②计划内线上验收;③持锁回滚演练(deploy.md §7,切旧确认后切回);④验收交接+文档更新+第二次 push server main+tag `m0`。四条执行要求:发布目标=修正后最终 SHA(03015b1);回滚严格按手册、不顺手改配置清理目录;第二次推送后确认部署、tag 指向已验证提交不反复移动;origin 推送/验收残留清理/M1 部署/真实付费不在授权内。

## state

- 文章修正与发布:替换句落盘,verify 通过(6 页/RSS 含标题/新句进产物/旧句 grep 零命中),commit 03015b1,push server main 成功(push 1s) [verified: release.txt 轮询命中 03015b139652a720d931c9001b1e5e6a90aa0ae8,总耗时 12s ≤180s]
- 线上验收①计时:push 完成到 release.txt 命中 12s [verified: 轮询脚本 elapsed=12s,ok=1]
- 线上验收②RSS XML:posts RSS(`https://nanmu.xyz/rss.xml`)HTTP 200,ElementTree 解析 ok,1 item(title=你好,nanmu-blog/link/posts/hello-nanmu-blog//pubDate=Fri, 02 Oct 2026 00:00:00 GMT) [verified: d:/tmp/rss.xml 解析输出;digest RSS 正确路径为 `/digest.xml`,HTTP 200 解析 ok items=0(digest 集合未创建,符合 M0 预期);首次误用 `/digest/rss.xml` 得 404 HTML 属 URL 笔误,非线上问题]
- 线上验收②真实订阅:CommaFeed(www.commafeed.com 公开 demo)真实订阅 `https://nanmu.xyz/rss.xml` 成功——服务端抓取并识别 feed 名"nanmu blog",条目《你好,nanmu-blog》链接与"4 天前"(2026-10-02)吻合,见截图 [verified: [m0-rss-subscription-commafeed.png](../evidence/2026-10-06-m0/m0-rss-subscription-commafeed.png)]
- 线上验收③明暗主题:Playwright `emulateMedia colorScheme` light/dark 切换,计算样式 light=rgb(255,255,255)/rgb(26,26,26),dark=rgb(15,23,42)/rgb(226,232,240),纯 CSS media query(`site/src/styles/global.css:6`)无 JS [verified: 截图 [light](../evidence/2026-10-06-m0/m0-theme-light.png)/[dark](../evidence/2026-10-06-m0/m0-theme-dark.png) + evaluate 输出]
- 附属核验:文章页 200(3627B)+正文命中;随机不存在 URL `/posts/definitely-not-exist-2026/` 真实 404 [verified: curl 状态码]
- 回滚演练:无部署进程/等锁任务(`ps` 精确路径 grep 零匹配);4 个 releases 全部 `.complete` 且内容匹配;持锁(`flock -E 75 -w 900` 同一 build.lock)校验 `.complete`+`dist/release.txt` 后原子切到 c8a4567,旧版复核 release.txt=c8a4567/首页 200/RSS 200 且 0 item/文章页 404(内容随版本回退,语义正确);同锁同校验切回 03015b1,复核 release.txt=03015b1/文章页 200/RSS 1 item;两次切换 exit 0,未删任何版本/锁文件,未改部署配置 [verified: 服务器命令输出逐条记录于本 session 验证表]
- tag `m0`:docs commit 推送并确认部署后创建,指向该已确认部署的提交 [verified: tag 对象 5205dc5→commit cb6898a(`git rev-parse m0^{commit}`),`git push server m0` 输出 `* [new tag] m0 -> m0`;创建后不再移动]

## verification

| 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
|--------------|----------------|--------------|
| site/ | `npm run verify`(文章修正后复跑) | 通过;exit 0,6 页构建 ~1.5s,产物含新句、旧句零命中 |
| 本机→server | `git push server main`(03015b1) | 成功;c8a4567..03015b1,轮询 release.txt 12s 命中 |
| 本机 | `curl https://nanmu.xyz/...`(release.txt/rss.xml/digest.xml/文章页/随机 URL) | 全部符合预期,状态码与解析结果见 state |
| 本机 Playwright | CommaFeed demo 订阅 + emulateMedia 主题切换 | 成功;截图三张入 evidence/;console 仅 1 个 favicon.ico 404(见 omissions) |
| server(SSH alias checkmate) | `ps` 进程核查;`ls releases/`+`.complete` 核验;两次 `flock -E 75 -w 900 ... ln -sfn ... mv -T` | 回滚演练通过;两次 exit 0,切换秒级,首页全程 200 |
| 本机→server | `git push server main`(cb6898a)→轮询 release.txt→`git tag -a m0`+`git push server m0` | 部署确认通过(release.txt=cb6898a,5s 命中;首页/文章页 200、RSS 1 item);tag m0→cb6898a 推送成功;随后一次 session 引用补正小提交推送后结束 |
| 仓库根 | `python scripts/check_docs.py --snippets --bash ... --node ...` | 通过;71+ md/247 local_links/12 表 DDL 一致/snippets 6 组,errors 与 warnings 均为空(本 session+三指针+evidence 提交前复跑) |

## 验收结论

M0 全部 10 个任务(+Task 8a)完成:博客静态站在 https://nanmu.xyz 稳定运行,首篇文章真实发布并被第三方订阅客户端真实订阅,回滚路径实操验证。**M0 验收通过,tag `m0` 已创建并推送(见 verification)**。M1 前置条件(spec §9:M0 独立上线验收)满足。

## pending_runtime

无在运行任务。遗留临时文件:`d:/tmp/rss.xml`、`d:/tmp/drss.xml`(404 HTML,误 URL 所得)、`d:/tmp/drss2.xml`(线上 digest.xml 副本)与旧工作区根三张截图原件,均为本轮取证副本,可随时删除。

## decisions_needed

无(授权范围①—④已全部执行完毕;后续 M1 Task 0-12 已有批量授权)。

## disposition

complete(本轮 objective=M0 收尾;M1 是下一阶段)

## next_action

进入 M1 Task 0-12 批量本地实现(按 [resume-implementation](2026-10-06-resume-implementation.md) 批次规范:Task 0-4 接口稳定后 5-8 与 9-12 并行;替身模型/真实上游只读/不部署不付费;Task 1 计量依据与停点从严)。origin 推送、验收残留清理、M1 部署、真实付费仍待用户单独授权;skills.nanmu.xyz DNS 与 ICP 备案在用户侧。

## omissions

- **favicon.ico 404**(Playwright console 唯一报错):浏览器默认请求 `/favicon.ico`,站点未提供该文件;`<head>` 中如有其他 favicon 声明则影响极小,未逐项核对。属外观小瑕疵,不阻塞 M0 验收(plan 无 favicon 验收项),留 M1 顺手修复。
- CommaFeed 为公开 demo 环境,订阅记录不持久(数据可能被重置);本轮已用截图+快照固化证据。真实读者订阅体验需自有账号长期验证,不在本轮范围。
- 明暗主题核验基于 `prefers-color-scheme` 模拟与计算样式断言,未覆盖手动切换开关(站点本就无此开关,纯跟随系统,符合 M0 设计)。
- 本地 `npm run verify` 与线上产物的一致性依赖部署链路(hook 内同样执行构建冒烟),未在服务器上单独重跑 verify。
- 用户侧遗留:skills.nanmu.xyz DNS 恢复、ICP 备案核实;origin(GitHub)未推送,本地领先 origin 多个提交。
