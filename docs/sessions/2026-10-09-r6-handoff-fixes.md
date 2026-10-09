# R6 交接收口:两审计遗留修复(2026-10-09)

指令:另一设计 AI 完成 R1–R6 原型探索后交接;本轮承接设计成果、只修两个
审计遗留问题,不做视觉改向、不开 R7;审计与方向管理归另一会话。

## 现场核对(只读,未 reset/clean/切分支)

分支 `codex/r6-interaction` @ 879cdef(R6 四组定点修正),工作区干净;
8a8e719(R5 阶段基线)= main = origin/main;分支未推远端。与交接描述一致。

## 问题 1:最后一次选择没有取消旧排队(scene6.js)

**机制**:`select()` 中 `target.userData.slot === 0` 的提前返回发生在排队
处理之前——槽位在换页动画**开始时**即交换,动画进行中再点"正在换入的页"
会空返回,既不受理也不取消 `pendingSelect`,动画完成后旧排队照样执行,
终态 ≠ 用户最后一次选择。

**复现(RED,Playwright/Chromium,120ms 连点)**:初始文章,动画中点
「日报→这个站→日报」→ 终态 scene=tab=panel=**about**(审计反例逐字复现);
3D 等价入口(`__bookscene.select`)与两种其它排列(about→digest→about、
digest→posts→digest)、暂停动态路径同样失败(5 组 FAIL);慢节奏(第三次
点击落在动画完成后)、reduced-motion、无回点基线通过。

**最小修正**:`select()` 把"目标已是前景"从空返回改为——动画进行中时
取消 `pendingSelect` 并 `onSelect(pid)` 把外部(可能被旧排队链拉走的)
页签/面板同步回来;无动画时状态已一致,无动作。

**验收(GREEN 8/8)**:三方(scene/页签/面板)一致且等于最后一次选择;
覆盖页签与 3D 等价入口、两种排列、慢节奏、暂停动态、reduced-motion、
无回点排队基线(旧排队语义未破坏)。

## 问题 2:View Transition 临时挂名未清理(site6.js)

**机制**:点击封面与首页 `pagereveal` 两处设 `viewTransitionName=
'latest-cover'` 均无清理;回程补挂后挂名永久残留,后续「读全文」按钮/
3D 前景页进入文章时旧页快照带名 → 与文章页头(常驻同名)配对 → **屏幕外
封面卡 morph 飞入页头**(继承)。且 `pagereveal 带 viewTransition` 不等于
"从文章返回":posts→首页的同型导航也会误补挂。

**复现(RED)**:封面进入→返回→按钮进入→返回→3D 进入链路,返回 900ms
后挂名仍为 `latest-cover`;按钮/3D 进入时旧页卸载挂名 `latest-cover`
(配对成立=继承发生);posts→首页误补挂;reduced 下点击封面仍留挂名。

**最小修正(挂名生命周期 = 按需挂上、转场完成/跳过/形态改变即摘除)**:

- 去程:点击可见封面才挂名;reduced-motion(VT 已被 CSS 禁用)与
  修饰键/非左键(新窗口打开,无同窗 VT)不挂;bfcache 往返恢复时摘除;
- 回程:仅当本页处于 VT 中**且来源是文章页**(`navigation.activation.from`,
  缺失时退 `document.referrer`,都读不到则保守不挂)才补挂;补挂后
  `viewTransition.finished`(完成或跳过)即摘除。

**验收(GREEN 8/8)**:封面进入/返回的 morph 保留;返回后挂名清理;
按钮/3D 入口旧页无挂名(无配对=不继承);posts→首页不补挂;reduced
全程无挂名、普通导航正常。

**morph 存在性的独立硬证据(双时刻几何探针)**:pagereveal 后 80/260ms
采样 `::view-transition-group(latest-cover)` computed 几何——封面进入
539×277@ (639,211) → 760×167@ (340,180)(morph 插值中);按钮/3D 入口
恒 760×167@ (340,180)(组存在=页头常驻名,但无旧页配对、无动画)。

**观测手段曲折(记录给后续接手者)**:跨文档 VT 的动画不进
`document.getAnimations`;`getComputedStyle` 查命名伪元素对不存在的名也
返回实值(假阳性,about:blank 已证);`ViewTransition.transition()`
在此 Chromium 不存在(带回退的冻结脚本实际未冻结);外部图像分析对
root 交叉淡化与 morph 的区分不可靠(两次结论与机制断言矛盾,弃用)。
最终采用:旧页 `pagehide` 把挂名写入 sessionStorage、新页 `pagereveal`
读出(配对规则:两端同名才 morph,旧页卸载挂名即判定依据)+ 上述几何
探针双确认。截图辅证:shots/r6fix2-vt-cover-mid.png(封面 morph 自然
中段帧:飞行纸卡 + 交叉淡化)。

## 回归(受本轮修改影响,6/6 PASS)

排队链中帧两页分离无穿插+终态一致(shots/r6fix2-swap-chain-mid.png);
site6.js 同文件未触碰段(页签 aria/漫游 tabindex、三层双向联动);HUD
暂停 aria;画布无横向溢出(maxX=0,resize 未触碰);base6.css VT 声明
顺序(auto 在 reduced none 之前)。

## 边界与状态

- 只改 prototypes/r6/3d/scene6.js 与 prototypes/r6/assets/site6.js 两个
  文件;R6 纸张/排印/朱砂装订线/三页 3D 目录/阅读转场基线未动。
- R6 仍是独立原型:内页除 post-hello 外沿用 R4,**尚未全站统一**;
  未接入生产 site/,不代表获得生产接入许可。
- 本轮未:修改 site/engine/上游、服务器操作、真实付费、timer 启用、
  分支合并、远端推送(授权边界见交接指令)。

## 下一步建议(待审计/用户裁决)

1. R6 基线评审:确认换页排队语义(最后一次选择优先)与 VT 挂名生命
   周期为期望行为;
2. 若通过:讨论全站套用(R4 内页 → R6 语言)与生产接入的 ADR 增补
   (客户端脚本白名单已在 README §10 提案);
3. 真机(iOS Safari/触摸)与 Firefox 降级路径仍未实测(沿用 R6 已知
   边界)。
