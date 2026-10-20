# 批次 C 发布前定点修正 + 工作台设计补齐(2026-10-20)

基线 eaf200e;本轮 A 线(发布前修正)与 B 线(工作台设计补齐)独立推进,A 不等 B。停止边界遵守:未推送 origin/server、未部署、未改服务器/engine/timer/付费配置、未实施工作台。

## A1 生产 poster 清除撤稿残留(f9c9e3e)

- **问题**:poster-light/dark.png 由 R6 原型 scene6 拍摄,完整排印被撤文章(标题/2026-10-02/烂尾经历正文/topic-digest/AIHOT/PowerContext/「第 1 篇」落款)。图像分析核实(非 grep)。
- **改法**:scene6 纹理通用化(articleTex 日期/标签/落款字段缺省整行跳过;digestTex 新增 intro 栏目介绍态),poster_capture.py + poster-capture.html(入库)从生产 scene6 拍中性主视觉「记录所想,留住所得。」+栏目介绍——结构性表达,不含文章正文/标题/日期/开发经历,不随文章状态过期、不写「暂无文章」防过期。新资产 poster-stack-{light,dark}.png(名字含 poster 保 L 段断言兼容),153.2/148.8 KiB(dsf=1 与旧图同口径,预算内);旧图 git rm(历史保留);index.astro 引用新名使浏览器缓存失效。
- **既有缺陷顺带修复**:FIXED_SAMPLE 从未含零期空态文案字(「第/一/到/达/时/会/出/现/里」等),fonts.load 缺字静默回退系统字体——重写为排印字面量全集,新增 check_scene_sample.mjs 对账(函数体字面量提取 vs 样本串)挂入 npm run verify。
- **验收**:verify_browser I 段断言 src=poster-stack-*,L 段 no-webgl 断言旧图零请求(TDD RED→GREEN 85/85);四态(正常加载初期/无 JS/WebGL 禁用/3D 模块加载失败)×昼夜 8/8 请求新资产、旧图零请求(一次性脚本 C:/tmp/c3a1-states.py,截图 C:/tmp/c3a1-shots/poster4-*);新图人工图像核查通过(无旧内容,纸页造型/昼夜风格保留;右侧虚线框=ghost 检索计划页为有意设计)。

## A2 日报状态文案派生(6709365)

- **问题**:有期时 siteLayers 仍显「在线 · 每日一期」(以存在推导频率),订阅卡有期仍显「暂无发布」;零期「计划 · 暂无发布」正确。
- **改法**:digestState=digests.length ? '在线 · 已发 N 期' : '计划 · 暂无发布',siteLayers/订阅卡/RSS 描述/scene6 零期纸面全部从同一份 digests 数据派生;全站无「每日一期」负面断言;有期面板描述去「引擎每日一期」。
- **验收**:verify_digest_states.py 三态升级(零期/单期/两期+订阅卡断言+perDay 负面断言),RED(态 2/3 真缺陷)→GREEN 3/3;多期夹具仅临时副本。

## A3 布局验收与证据(5b34dd5)

- verify_browser T 段新增 hero-geom/tabs-resize:1280×600 矮窗依次切三页签(面板高度不同)逐步断言 hero 几何不变式,再 resize 1366×768 复断言→常驻 86/86。
- verify_posts_fixture.py(入库):零文章不灭非空验收——临时长标题文章夹具真实构建,7 断言(四方同源/hero 矮窗与常规窗/列表/文章页/RSS)全过;正式内容源零改动。
- **before 证据重建**:上轮 session「CDN 归档」勘误(误述,实为本地 C:/tmp/c3-shots/);旧 probe-* 与 after-* 同哈希=当时「修复前」截图实为修复后重拍、已失效。真原始证据未找到→在修复前提交 4d7cbe4 隔离 worktree(临时+junction 构建,用完已清)同款探针重拍 8 视口 rebuilt-before-*,1366×768 哈希 55565c21≠修复后 be20d426,实测标题缺口 -51.4px 与 session 记录吻合,来源标「本轮重建」。旧 session 该句已按用户明示授权勘误并标注。

## B 工作台设计 B1–B5 补齐(5c198fb,仅设计不实现)

DESIGN.md 按 00c9 契约逐项落:B1 §2.1(github/deploy remote 消歧+固定 worktree+凭据政策+部分成功恢复+禁 force push);B2 §4.2(base 编辑基准+外部修改检测+rev 乐观锁+原子保存中断恢复+保存失败不显过期已保存);B3 §4.4(内部七态/界面五态+operations 持久化重启重放+180s=暂未确认+幂等+列表上线判定以 URL/release.txt 为准+五中断推演);B4 §4.3/§3/§10(预览独立目录全量鉴权+24h 存活+worktree 删除不失效+删「无新增注入面」结论+CSRF+随机哨兵验收);B5 §2.2(Node+Fastify+argon2+系统 git;并发 1+120s 超时+hook 互斥;「空闲极低」「2-3s」降待测假设列实测方法;不动 engine/timer/付费)。

## 验收汇总(本轮实测)

- Chromium 86/86(新增 tabs-resize)、Firefox 14/14、WebKit 13/13
- npm run verify 绿(build+smoke+fixture+check_scene_sample:FIXED_SAMPLE 覆盖 125 字符,冗余字符 Sop 无害)
- verify_digest_states 3/3;verify_posts_fixture 7/7;check_docs 0 错误
- git diff --check(本轮四提交)无空白错误
- 未覆盖环境(与前轮登记一致):真机触摸/Safari/帧率

## 状态与下一步

- 本地 main=本轮五提交(f9c9e3e/6709365/5b34dd5/5c198fb+本交接);**origin/server 均未推送,线上仍 9120bf3(含被撤文章),发布待用户授权**。
- ⚠️ 回滚到批次 C 前版本=重新公开被撤文章;「先恢复旧文再立即撤下」不是安全操作;未经用户接受不得重新公开该文。
- 一次性脚本与截图均不入库(C:/tmp/c3a1-states.py、c3-shots/、c3a1-shots/)。
