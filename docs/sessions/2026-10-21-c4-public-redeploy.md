# 会话交接:公开博客重新部署(2026-10-21)

- **recorded_at**: 2026-10-21 17:20 Asia/Shanghai
- **continues**: [2026-10-20 审计收口](2026-10-20-c3-audit-wb-closeout.md)
- **repository**: 本轮 A 线在 main 完成(HEAD=17d008c+本交接提交);B 线工作台定点修正在 `workbench-batch1` 分支独立进行(见该分支后续交接)
- **objective**: 沿既有链路把批次 C 公开站修正(布局/撤稿/文案/poster/日报状态)真实上线并完成线上验收;不含工作台任何内容

## 结论

**完成**:批次 C 修正已真实上线,线上验收 20/20。发布对象 **17d008c2966f024bbfb0c3db0030c4b511b002a8**(发布开始时实读 main 固定),origin/main 与 server/main 均已推至该 SHA,线上 release.txt 与之一致(30s 确认,≤180s 达标)。无回滚操作。

## 实际变更

- **零产品代码变更**:76672f5(批次 C 产品基线)..main 的 site/engine/deploy 树级差异为空(实测 `git diff --stat` 空),本轮为纯部署+验证+文档。
- 本提交:本 session+AGENTS 发布状态更新。
- 外部操作(均在授权内):`git push origin main`(4d7cbe4→17d008c)、`git push server main`(9120bf3→17d008c)、服务器只读检查(deploy.log/current)、线上只读验收。

## 发布过程(四阶段分立)

1. **Git 接收**:origin 4d7cbe4..17d008c(fast-forward;4d7cbe4=R6 发布交接提交,origin 曾于 2026-10-13 收到,无分叉,merge-base=origin/main 证实);server 9120bf3..17d008c。
2. **构建**:hook 自动,deploy.log 末行 `2026-10-21T16:43:44+08:00 deployed 17d008c2966f024bbfb0c3db0030c4b511b002a8`。
3. **切版**:current → releases/17d008c2966f024bbfb0c3db0030c4b511b002a8(readlink 实读)。
4. **线上响应**:release.txt 轮询 30s 确认;A4 验收全过(见下)。

## 实际验证

| 环境 | 操作 | 结果 |
|---|---|---|
| 本地 main 候选 | `npm run verify`(site/) | exit=0:build 2.62s/5 页、smoke ok、fixture ok;「digest collection 空」为撤稿后无日报数据的预期空态 |
| 本地 main 候选 | `python scripts/check_docs.py` / `git diff --check` | 0 错 0 警 / exit 0 |
| 发布前核对 | 五项修正 SHA 祖先检查+产品差异+workbench 夹带检查 | ef78ab5/ff3fa0e/c3aa570/f9c9e3e/6709365(+5b34dd5/76672f5)全在 main;4d7cbe4..main 产品差异=批次 C 7 提交;main 无 workbench/ 目录 |
| 线上 HTTP | 页面/RSS/404/资产 GET | 全过:四页 200、乱路径 404、被撤旧 URL /posts/hello-nanmu-blog/ **404**、rss.xml items=0=本地公开集合(drafts-example 为永久 draft fixture,排除机制为设计行为)、digest.xml items=0、/3d/poster-stack-{light,dark}.png 200(中性资产在线) |
| 线上浏览器 | Playwright Chromium 一次性脚本(20 断言) | **20/20**:被撤标题/slug/正文特征在首页/列表/日报/关于 DOM 与 scene6.js 中零残留;3D 就绪(window.__bookscene)且主题循环 auto→light→dark→auto;hero 几何不变式(竖排标题单列、kicker/标题/副题与目录块零相交、与页签 gap≥0)在 1280×600/1366×768/1920×1080 三档全过;矮窗逐页签(digest/about/posts)+resize 768 后不变式仍立;手机 390×844 无横向溢出+菜单接管+hero;无 JS(内容可达+poster 2 张+几何不变式)/WebGL 禁用(no-webgl 终态+poster 常显+零引擎请求)/3D 模块 abort(内容可达+poster 接替)三路降级全过;资源 404 监控 0(favicon 既有项本轮未出现) |

**失败轮次(如实)**:线上验收脚本首跑 18/20、次跑 19/20,四轮修正均为**脚本侧断言缺陷**(urllib 对 404 抛 HTTPError 未按状态返回;元组解包把 PNG bytes 当状态码;poster 断言误写为在 boot6/scene6 文本找 `poster-stack-` 字面量——scene6 为程序化纹理无 png 引用,改为直接验证资产 URL;主题断言误猜点击一次到 dark——产品循环为 auto→light→dark→auto;3D 就绪标记误用子元素查询——实为 `window.__bookscene` 全局)。**产品零缺陷**,与 R6 首轮验收经验同类。

## Git 与部署状态

- 固定发布对象:**17d008c2966f024bbfb0c3db0030c4b511b002a8**
- origin/main:17d008c(发布版本,第一推 rev-parse 实读);⚠️本交接提交(d06041a)因 github.com 连接失败(连续三次 Connection reset/443 不通,环境抖动)暂未推 origin——发布版本已在 origin 保存,不阻塞;待网络恢复补推
- server/main:17d008c(push 输出 9120bf3..17d008c)
- 线上 release.txt:17d008c(轮询确认+验收断言第 1 项)
- 恢复操作:无;旧版 9120bf3 及更早**含被撤文章,不作回滚目标**(⚠️回滚到 9120bf3 及更早会重新公开被撤文章;9120bf3 为发布前线上版本,现已被替换)

## 遗留问题

- 真机 Safari/触摸/设备帧率未验证(沿批次 3b 口径,模拟浏览器≠真机)——不阻塞本轮目标(授权范围为线上桌面/模拟验收)。
- 六个长任务窗口内输入响应线上未测(本地结论沿用,200ms 为建议目标)——不阻塞(非本轮验收项)。
- Cache-Control 缺失(ETag 协商)与 favicon 补齐沿既有观察项——不阻塞;补头属 Caddy 配置变更,未授权不动。
- 批次 C 之后未重跑 Firefox/WebKit 线上(授权范围为 Playwright Chromium;候选树与本地 Chromium 86/86 时完全一致)。

## 证据

- 截图 8 张+验收日志:docs/design/2026-10-07-visual-redesign/shots/c3-release-*.{png} 与 logs/c3-release-live-accept.log(本地 gitignored 证据目录,R6 先例;不只在 C:/tmp)
- 验收脚本:一次性不入库(C:/tmp/nanmu-live-accept.py,R6 rc-live-accept 先例),断言模式复用 verify_browser.py T/C 段同款几何不变式

- **disposition**: complete(A 线)
- **next_action**: 无 A 线待办;B 线工作台批 1 定点修正独立进行(workbench-batch1 分支),完成后待审计复核
- **omissions**:
  - 线上验收脚本未入库,复现需参照本记录的断言清单与 verify_browser.py T/C 段
  - 线上未做 RSS 真实订阅端验证(与 M0 的 CommaFeed 口径不同;本轮以 XML 解析+条目数对齐为验收)
  - 服务器只读检查未覆盖 Caddy 进程状态(改版未动 Caddy,现网响应正常即覆盖)
