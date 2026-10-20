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

## 状态与停止点

- 本地 main=6e2aa5d+本交接;origin/server 未推送,发布待用户授权。
- B 线停在设计复核位置,未开始正式工作台开发;反例为验收预期非已通过测试数。
- 未改 engine/上游/timer/付费配置/deploy hook/服务器配置。
- 未覆盖环境维持:真机 Safari/触摸/设备帧率。

## 勘误(2026-10-20,本节有痕追加,不改写历史提交)

上文「拟发布完整 SHA=af67d839…」口径**作废**:af67d83 是该轮接手时 HEAD,不是最终发布对象;把它硬写为发布对象意味着每新增一次文档提交口径即过期。修正为取值规则:

- 76672f5 = A 线产品修正基线(此后 site/engine/deploy 无变化,实测 `git log 76672f5..HEAD -- site/ engine/ deploy/` 为空);
- af67d83 / 50e0191 = 各轮接手时 HEAD(历史记录,保留);
- **最终发布对象 = 完成全部必要提交后实际读取的 `git rev-parse main` 完整 SHA**。发布授权后、发布开始时固定并记录该值;推送与 release.txt 对照都以该值为准;期间 main 再变化则先核对差异。任何提交正文不硬写「包含该文档提交自身的最终 SHA」;实测 SHA 在最终报告中附上(报告时点在提交完成之后)。

本轮发布清单其余条目不变;无新增产品变化,不重复浏览器/性能验收。
