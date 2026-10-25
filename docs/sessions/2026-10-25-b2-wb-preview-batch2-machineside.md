# 2026-10-25 批 2 机器侧完成:真实构建+静态校对预览(2.1–2.4)+双线推进记录

## 线 A:workbench 批 2(workbench-batch2 分支)

前置:任务 1.0(ADR-0011)在 main 补齐(fce4daf);main 合入 workbench-batch2(3d13d34,冲突解:spec 三处注取 main 侧、AGENTS 融合+批 1 复核通过句);批 1 经用户 2026-10-25 复核通过。

| 任务 | 提交 | 内容 | 验证 |
|---|---|---|---|
| 2.1 预览构建 | ad3c142 | worktree 脚手架+草稿入 posts/+buildCmd 注入+dist→previews/<op-id>(tmp+rename 防半目录)+失败留证 .failed.log+失败不建预览+20min 超时 | RED→GREEN 3/3(临时 bare fixture) |
| 2.2 改写器 | f6dbd79+a527b88 | 根路径→/preview/<id> 前缀;css/font/img 注 ?t=(query 追加);srcset 逐候选;站内/外部/mailto `<a>` 去 href 留 data-wb-target;#锚点保留;/api/ 永不入命名空间;script src 前缀不注 token(类别外);相对/data: 原样 | RED→GREEN 8/8 |
| 2.3 预览服务 | 685a0ec | GET /preview/:opId/*:HTML 会话 401(不重定向)+CSP sandbox+noindex+no-referrer+横幅+改写注 token;子资源 bearer token 四项校验(有效/预览绑定/类别/会话活跃)+js 持 token 亦 401;CSS 服务端改写分片;字体 ACAO:*;过期/删除/总量清理(24h+10 份)一律 410;穿越 404 | RED→GREEN 9/9(可控时钟) |
| 2.4 哨兵验收 | c18b5de | 双预览 HTML+CSS 两层哨兵互不串、token 独立、公开面零命中(验收性组装,组件各自已 RED) | 2/2;全量 **56/56** |

**真实构建冒烟 PASS(一次性,PLAN「尚待实现验证」首条闭合)**:本仓库裸镜像 clone→buildPreview 真实 `npm ci && npm run build`→哨兵草稿真实渲染进 `posts/<slug>/index.html`,15.5s 全链。坑:哨兵串不可用 `__x__` 形式(markdown 解析为粗体吃掉下划线),改用连字符串。

## 批 2 剩余(停止点前)

1. ~~浏览器级验收~~ **已完成(2026-10-25 补,d9ffcce)**:e2e_preview_isolation.py(入库可复现)真实服务 16/16:触发链/未登录 401/哨兵+横幅+CSP+字体全链/活动脚本零执行(服务端记录)/实际点击零导航(修复假阳性)/锚点滚动/双预览互不串/登出连带失效/410/BLOCK 反向。验收驱动两处产品修复:①预览 URL 直达文章详情页(原返回站点根,哨兵实为首页摘要,点击断言全假阳性——经「回读 body 320B 相等+原始 dist 锚点完好」定位);②rewriteCss 相对分片 url('shards/x.woff2') 补 token(原只改根路径→分片 401 字体断)。另补 POST /api/preview(bd9af04,e2e 首跑暴露缺口:无触发入口预览永不注册)。全量 59/59。
2. ~~作者实际校对~~ **已通过(2026-10-25,本地试用工作台实测)**:用户登录 http://127.0.0.1:8790(独立临时目录 c:/tmp/wb-try+bare 镜像,随机占位口令)校对样稿;反馈两轮均针对文章页上下文导航空态卡片(公开站样式,非预览机制):①贴边(70e18c1 补 padding)②仍丑(默认 dashed 虚线框=wireframe 感)→重设计为书页页脚式(f8eecda:通栏细线+两端文字+对仗文案+hover 朱砂,posts/digest 同构)→空态去箭头整簇降半+标题截断(5414552);均先入 main 再合入批 2 分支,昼/夜双主题截图+视觉复查验收。用户终判「目前没有问题了」——**批 2 全部通过**;
3. e2e_browser.py(批 1 写作流)扩预览段:可选,判据已被 e2e_preview_isolation.py 覆盖。

## 遗留登记

- main 领先 origin 三提交(70e18c1/f8eecda/5414552,上下文导航三轮)——公开站产品变更,推送 origin/部署上线待用户授权;
- 本地试用工作台(8790)与 c:/tmp/wb-try 仍在运行,批 3 开发期间保留(构建链复用),用毕停。

## 线 B:方案 A 服务器现场验证 ✅

ssh 只读:`/opt/nanmu-blog/engine/.venv` 环境下 `resolve_upstream_snapshot('/opt/topic-digest/backups', now)` → **RESOLVED topic-digest-20261024T193111.db**(今晨成功件,≈17h<48h),规则 1(journal 证据链→文件防线)+规则 2(时效)在真实数据闭环,零写入。线 B 下一节点=真实校准授权(M1 五步第 2-3 步),须用户当次显式授权。

## Git 状态

- main=origin=7e8a2ae;server=线上=230db76;工作区干净(批 2 提交前)
- workbench-batch2:3d13d34+ad3c142+f6dbd79+a527b88+685a0ec+c18b5de(本地,未推送——批 2 验收收口后随批合并处理)
