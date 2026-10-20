# 会话交接:上线页面修正与公开内容整理(批次 C,2026-10-20)

- **recorded_at**: 2026-10-20 15:45 Asia/Shanghai
- **continues**: [R6 发布 session](2026-10-13-r6-release.md)(线上 release=9120bf3)
- **repository**: 本轮全部为本地 main 提交,**未推送 origin、未推送 server(发布待用户另行授权)**
- **objective**: 按用户真实使用反馈:修复首页左侧布局错位;撤下《你好,nanmu-blog》(真撤稿);公开文案回到个人博客定位;产出文章管理工作台最小设计(不实现)

## SHA 清单(本轮)

| 口径 | SHA | 内容 |
|---|---|---|
| 起点(=线上 9120bf3 + 纯文档交接) | `4d7cbe4` | — |
| 布局修复 | `ef78ab5` | hero 左列结构锚定+T 段几何断言 |
| 撤稿+零文章态 | `ff3fa0e` | 删文章源+全部消费方同步+测试改造 |
| 公开文案 | `c3aa570` | 首页/关于/日报/3D 文案+copy-clean 断言 |
| 工作台设计(纯文档) | `d9db3c2` | [DESIGN.md](../design/2026-10-20-writing-workbench/DESIGN.md) |
| 交接提交 | 本提交 | 纯文档 |

线上仍为 `9120bf3`;`d9db3c2` 与本提交相对已验收产品代码为纯文档差异。

## 一、布局错位:复现→根因→修复(ef78ab5)

**复现**(一次性探针 C:/tmp/c3-layout-probe.py,8 视口×DPR×字体状态量化,截图 C:/tmp/c3-shots/):
- 所有桌面视口(含 1920×1080)`heroTitle×tocBlock` 容器交叠恒 **51.4px**;视口高 ≤768 竖排标题文字压页签(最大 30.9px);≤691 标题折两列、副题压面板(45.1px);与 JS 无关(无 JS 同值)。
- 访客全路径体验(首页→页签×3→读全文→返回→列表→正文→返回→关于→404,桌面+手机):除上述外零问题,零 console 错误(favicon 404 为既有登记项)。

**根因**:`.hero-title{bottom:250px}` 硬编码预留 < `.toc-block` 实际总高(实测 ~311px,内容决定);`.v-title` 高度约束 5.4vh 未扣导航 74px 与目录实占。

**修复**:index.astro 包 `.hero-left` 左列(标题区底边锚定目录块顶边,与面板内容高度解耦);home.css 目录块改列内流式、v-title 字号约束按(视口-导航-目录-底距)实扣(极矮窗 24px 下限、超出折 ≤2 列仍不叠);手机端 display:contents 恢复平铺。

**验收(TDD)**:verify_browser 新增 T 段 4 断言(1280×600/1366×768/1920×1080/无 JS 600,几何不变式不绑文案)RED 3 FAIL(压 45/31px+折列)→GREEN 87/87;修复后 8/8 视口重叠 area=0、全部单列。前后对照〔2026-10-20 定点轮勘误:下述「归档于 CDN」为误述〕:截图实际在本地临时目录 C:/tmp/c3-shots/(不入库);且定点轮核查发现旧 probe-d-1366x620/probe-d-1920x1080 与修复后 after-* 同哈希——当时的「修复前」截图实为修复后状态重拍,已失效;定点轮在修复前提交 4d7cbe4 的隔离 worktree 用同款探针重拍 8 视口 rebuilt-before-*(1366×768 哈希 55565c21≠修复后 be20d426,实测标题缺口 -51.4px 与本节记录吻合),来源标注「本轮重建」,见定点轮 session。批内 3 浏览器全绿(87/87→85/85 项数随断言演进)、npm run verify 绿。

## 二、撤下《你好,nanmu-blog》(ff3fa0e)

真撤稿(用户授权,非藏入口)。**消费方清单(全同步)**:
- 文章源 `site/src/content/posts/hello-nanmu-blog.md` 删除(git 历史保留,不重写)
- about.astro 时间线「第一篇文章」行移除
- scene6.js FIXED_SAMPLE 预载字符去该标题(渲染内容本就同源 data-*,空态纸面「暂无文章」为既设计)
- 路由/列表/首页/RSS/3D:全部动态走零文章空态(模板空态分支既有,实测生效)
- 站内链接、digest 页、sitemap(无此产物):零残留(grep 终检 src/public 业务侧零命中)

**测试改造**(硬编码「必须有这篇文章」的断言改为验证零文章态):矩阵移除 post 页、fontck 移挂首页、posts/empty、post/withdrawn-404、rss/withdrawn-empty、nojs/index 空态、home/withdrawn-no-entry(封面卡/读全文不残留)、cover-vt 生命周期用例随对象撤下移除、btn-contrast 改注入元素实测同一 CSS 规则、fx/wk 同步、Q/R 段内页代表改 /digest/、measure_budget 路径改 /digest/。

**验收**:三浏览器 TDD(RED:rows=1/URL 200/items=1/cover 在 →GREEN)。零文章态证据:旧 URL 404;rss.xml `<channel>` 完整且 items=0;3D tris=4351 空态纸面;列表空态;手机端正常(截图 zero-01/02/03)。

## 三、公开文案(c3aa570)

用户初稿采纳:v-title「记录所想，留住所得。」;v-sub「这里是 nanmu 的个人博客，收录随笔、阅读记录与值得分享的内容。」;关于页开篇「我用这个博客记录想法，也整理阅读与生活中的发现。文章不定期更新，欢迎通过 RSS 订阅。」。移除:烂尾经历/开发周数/评审核验/部署链路(推送/自动构建/原子切换)/topic-digest 与 AIHOT/PowerContext 借鉴说明/两处「待填」占位/「每日一期」频次宣传(全部改「暂无已发布日报」准确表述)。未编造任何个人信息,缺的(联系方式等)直接不展示。

验收:copy-clean/home|about 负面清单断言(14 内部词)先 RED(首页 7 词/关于 8 词)→GREEN;copy/home-position 定位词;about 断言零待填(todo==0)。3D 纸面三处文案与 FIXED_SAMPLE 同步。

## 四、工作台设计(d9db3c2,不实现)

[DESIGN.md](../design/2026-10-20-writing-workbench/DESIGN.md):公开站保持静态,工作台独立进程;口令认证(仅服务器 env)/草稿物理隔离三道闸/预览=临时 worktree 真实构建/发布沿用 Git 链路+四态状态机(已保存/发布中/已上线/发布失败,轮询 release.txt)/非 ff 拒绝不 force/工作台停运公开站照常;对 ADR-0002 的分面修订说明(实施第 1 步立 ADR-0011);实施分解五步+安全清单。

## 五、发布方案(待用户授权,本轮未推送未部署)

- 待发布:main 上 `ef78ab5..c3aa570` 三笔产品提交(+d9db3c2/本提交纯文档);无合并步骤(main 直线)。
- 流程:[deploy.md §6](../ops/deploy.md):发布前 fetch 实核 origin/server 与本地无分叉 → push origin main(备份)→ push server main 触发 hook → 轮询 release.txt ≤180s。
- 线上验收清单:现有全量断言之外重点核对零文章四查(旧 URL 404/RSS items=0/首页与 3D 无残留入口/列表空态)+ hero 几何(矮视口不压目录)。
- **⚠️ 回滚影响警示(必读)**:本批发布后,线上旧版 9120bf3 及更早 release 仍含《你好,nanmu-blog》。**回滚到任何批次 C 之前的版本会重新公开该文**。若发布后发现缺陷,优先前向修复(新提交);确需回滚时必须接受文章重新公开,或回滚后立即以新提交再撤。
- 工作台实施是另一批次(设计文档实施分解五步),不随本批发布;不把本轮任何授权自动套用到新增后台。

## 边界与遗留(登记)

- 真机触摸/Safari/帧率仍登记待验(沿 R6 口径);favicon 404 仍为既有观察项(不在本轮范围)。
- 极矮视口(高 <~680)v-sub 折两列属竖排自然排版(不压目录,几何断言把关);v-title 全视口单列。
- change_scope: site/(index/about/digest 页、home.css、scene6、5 个验证脚本、删 1 文章源)+docs/(设计文档、本 session、AGENTS.md);无 engine/deploy/hook/Caddy 改动。
- verification:见各节;最终态 Chromium 85/85、Firefox 14/14、WebKit 13/13、npm run verify 绿、check_docs 零错误零警告、git diff --check 干净。
- pending_runtime: C:/tmp 一次性脚本(c3-layout-probe/c3-walkthrough/c3-zero-shots/c3-mobile)与 c3-shots/ 截图不入库。
- disposition: complete(四项交付+交接;发布待授权)
- next_action: 用户裁决 ①发布本批(含回滚影响知悉)②工作台设计评审后另批实施 ③真机补验。
