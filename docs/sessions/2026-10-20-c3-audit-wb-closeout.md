# A 线发布前核对 + B 线三处契约收口(2026-10-20)

基线 af67d83;A 线纯核对(无代码改动、无提交),B 线三提交(e8841c5/273bc65/6e2aa5d)。

## A 线:发布对象核对(等待用户推送与发布范围的明确授权)

- **实况**(接手时核对):分支 main,工作区与暂存区干净;HEAD=af67d8397cd6ea394de27f167be26aaa6e113932。
- **76672f5..HEAD 差异**:`git diff --stat 76672f5..HEAD -- site/ engine/ deploy/` 为空——后续两提交(b92cd7c 设计、af67d83 session/AGENTS)仅文档,**无产品变化,未重跑浏览器/性能验收**(按指令不因纯文档提交重复全套验收)。
- **发布口径**(2026-10-20 勘误修正,见文末):产品修正基线=76672f5;最终发布对象**不是任何提前写下的 SHA**,而是**完成全部必要提交后实际读取的 main 完整 SHA**(取值规则,文档不硬写);af67d83 与 50e0191 分别为各轮接手时 HEAD,仅作基线记录。
- origin 与 server 均未推送,线上仍 9120bf3(含被撤文章)。
- **发布清单**(授权后逐项;全部需用户当次明确授权):
  1. 核对远端与拟推送范围,不强推:`git push origin main`(GitHub 备份)与 `git push server main`(发布)分别列明、分别授权;
  2. `git push server main` 沿既有 hook 发布(不改 hook);
  3. 线上 release.txt == 发布开始时固定并记录的 main 完整 SHA(授权后发布开始时读一次、写入记录;推送后核对远端引用仍指向它;期间 main 若再变化,先核对差异再继续);
  4. 旧文章 URL 404;文章 rss.xml items=0(日报 RSS=digest.xml,勿混称);
  5. 首页/列表/3D 纸面/poster-stack-* 均不展示被撤文章;
  6. digest.xml 无「每日一期」等不实频率承诺;
  7. 矮视口切三页签+resize 后标题不压目录(本地 86/86 已验,线上抽查目视)。
- 回滚约束:含被撤文章的旧版不作普通回滚目标;异常先报告影响再定前向修复。

## B 线:三处契约收口(仅设计+本地探针,未实现工作台)

**第一项 e8841c5(§2.1,文档推演)**:删「github 领先→快进双推收敛」(内容夹带通道);改为未终态 operation 闸门阻止新发布+同一 operation 按身份恢复(github==SHA→只重试 push deploy 等)+无法解释领先/分叉转人工;时序=创建时一次 fetch 双远端;取消本地≠撤销远端提交;收敛只允许 deploy→github 方向。六场景反例表(A 部分成功后开 B/A 同操作重试/取消 A/无关提交领先/真实分叉/同 slug 占用)。

**第二项 273bc65(§4.3+探针,本地实测)**:隔离定案=响应头 `CSP: sandbox allow-scripts allow-popups`(与加载方式无关,覆盖内嵌/直开/新标签页;iframe 属性仅纵深);管理 API 校验独立成立(会话+Origin/预检,不以「无 CORS」「opaque origin」一句话替代);首版内容边界与保留体验明示。**探针 probe_preview_isolation.py 实测 7/7**:未登录三类资源 401;预览内(iframe+直开)活动脚本 fetch 管理 API 抛 TypeError(CORS 层拦截,强于 401)而顶层同 API 200;伪造 Origin 写 403/同源 200;真实排版+Noto Serif SC 分片字体加载成功;localStorage/document.cookie 抛 SecurityError、内嵌读 window.top 被拒(降级如实记录)。探针边界:临时服务、测试占位口令(非真实凭据)、不连生产;是设计验证非正式实现。

**第三项 6e2aa5d(§4.4+§5,历史证据推演)**:按 deploy/deploy.sh 实际顺序(L28-38 mv 产物→L41-42 切 current)撤回「release 目录存在=曾上线」;四态=构建完成/当前上线(内容身份核对)/曾确认上线(唯一证据=operation 的 confirmed 记录)/历史无法确认(保守显示未知);不改 hook、不新增审计平台;保留「后续变更→早期 op 显示被替代」。§5 存储示例对齐 §4.2 单记录(draft.json+draft.prev.json,删 meta.json/body.md 旧例)。

## B 线:预览机制勘误轮(同日续;有痕勘误,不改写历史提交)

- **对上轮「探针 7/7」的勘误**:其 typography 断言无效——用户审计并经本轮复现:预览 HTML 200 但 fonts.css 401、document.fonts 为空、fonts.check 对目标字体与不存在的字体都返回 true(无区分度)。「7/7 已证明字体加载与完整隔离」不成立;隔离部分结论仍有效,字体部分作废。提交 273bc65 不改写,勘误记录于 DESIGN.md 与本节。
- **失败判据先行(RED)**:探针 v2 重写为三阶段。RED 阶段用 cookie-only 模式(资源仅认会话 cookie,模拟旧方案)实测资源组 5 FAIL(fonts.css 401、分片 0 个 200、FontFace 空、check 无区分度、外部 CSS 变量空)——探针先能识别当前失败,再调整方案。
- **定案=静态校对预览**(优先评估的禁脚本方案经实验证实可行:CSP sandbox 无 allow-scripts 下 Playwright CDP 注入仍可读 FontFaceSet/computed style,判据不依赖页面脚本):响应头 `CSP: sandbox`(无 allow-scripts),作者活动内容与公开站增强脚本一律不执行;一套承诺(保留排版/字体/配图/内链,零脚本),删除「保真增强」与「降级」并存表述。
- **资源加载三层修复**(GREEN 16/16 的前提):①opaque origin 子资源不带会话 cookie→子资源改**短期 token** 鉴权(返回 HTML 时签发、绑定会话、30 分钟过期、注入资源 URL、服务端改写 CSS 内分片 URL 补 token、Referrer-Policy: no-referrer);②字体加载走 CORS 模式,opaque origin 视为跨源——网络层 200 但字体层拒绝(FontFace 停留 unloaded),字体分片响应加 `Access-Control-Allow-Origin: *` 后样文所需 14 个分片真实加载(FontFace 14 条 loaded);③GREEN 实测 16/16:资源组 9(fonts.css/分片/图片 200、FontFace loaded、外部 CSS 变量生效、中文样文、check 无区分度如实记录)。
- **安全验证以服务端记录为准**:探针服务记录每请求(到达/方法/Origin/会话校验/返回状态/数据是否被修改);写目标=内存 dict,四路非法直连(无会话 401/伪造 Origin 403/null Origin 403/缺 X-Requested-With 403)后数据未变;合法对照真实删除(mutated=true)。撤回 v1「TypeError 比 401 更强不可达」表述——浏览器层抛错只说明响应不可读,不作「请求未到达服务端」证据。预览内活动脚本零执行的判据=服务端零 /api 到达+页面无副作用标记。
- **反向自检(BLOCK)**:token 方案但 fonts.css 恒 401→资源组 4 FAIL,阻断资源时验收必须失败,不静默以系统字体算通过。
- 反例表扩至十一条(新增:check 无区分度禁作证据/网络 200≠字体可用(CORS 拒绝同显 200)/内联样式≠外部 CSS/阻断必须 FAIL)。探针 v2 入库替换 v1(276 行→约 470 行,--phase red|green|block|all 可复现)。
- 边界不变:临时服务+占位口令、不连生产、未改 engine/hook/服务器;工作台仍未实现。

## 状态与停止点

- 本地 main=本轮勘误提交之后(最终发布对象按文末勘误节的取值规则,发布开始时实读);origin/server 未推送,发布待用户授权。
- B 线停在设计复核位置,未开始正式工作台开发;反例为验收预期非已通过测试数。
- 未改 engine/上游/timer/付费配置/deploy hook/服务器配置。
- 未覆盖环境维持:真机 Safari/触摸/设备帧率。

## 勘误(2026-10-20,本节有痕追加,不改写历史提交)

上文「拟发布完整 SHA=af67d839…」口径**作废**:af67d83 是该轮接手时 HEAD,不是最终发布对象;把它硬写为发布对象意味着每新增一次文档提交口径即过期。修正为取值规则:

- 76672f5 = A 线产品修正基线(此后 site/engine/deploy 无变化,实测 `git log 76672f5..HEAD -- site/ engine/ deploy/` 为空);
- af67d83 / 50e0191 = 各轮接手时 HEAD(历史记录,保留);
- **最终发布对象 = 完成全部必要提交后实际读取的 `git rev-parse main` 完整 SHA**。发布授权后、发布开始时固定并记录该值;推送与 release.txt 对照都以该值为准;期间 main 再变化则先核对差异。任何提交正文不硬写「包含该文档提交自身的最终 SHA」;实测 SHA 在最终报告中附上(报告时点在提交完成之后)。

本轮发布清单其余条目不变;无新增产品变化,不重复浏览器/性能验收。
