# 2026-10-08 视觉重做 batch4:R4「纸筑」全站原型

本轮按用户 R4 开工令执行:保留 R3 页面与组件骨架,重做主视觉、构图、材质、灯光与配色;四项定点修复同批完成;正式接入/提交推送/部署不在范围。

## 方向选择(两试验实拍,自主选定)

- 试验 A「纸筑」([lab/r4-lab-a.html](../design/2026-10-07-visual-redesign/prototypes/lab/r4-lab-a.html)):6 页扇形书页雕塑为主角,弧形纸幕为配角。概念一句话:站是一本正在写的发光的书(实页=文章,发光页=最新文章,虚线页=日报计划,朱砂书签=当前位置)。
- 试验 B「光束书房」([lab/r4-lab-b.html](../design/2026-10-07-visual-redesign/prototypes/lab/r4-lab-b.html)):悬浮桌板+台灯+光锥尘埃。昼景平庸、更接近现成方法,弃选。
- 两试验构图实拍:shots/r4-lab-a-day/night.png、r4-lab-b-day/night.png。**选定 A**,理由:有主角、昼夜都成立、概念专属于本站。

## 交付物

- 全站原型:[r4/index.html](../design/2026-10-07-visual-redesign/prototypes/r4/index.html) 起共 8 页(首页/文章列表/文章详情/日报列表/日报详情/关于/404/M2 预案),共用 assets/tokens4.css + base4.css + site4.js。
- 3D 源资产:[r4/3d/book.js](../design/2026-10-07-visual-redesign/prototypes/r4/3d/book.js)(PARAMS/LIGHT 参数表即源文件)+ boot4.js + poster 昼夜两张;清单与缺测项见 [r4/3d/ASSETS.md](../design/2026-10-07-visual-redesign/prototypes/r4/3d/ASSETS.md)。实测 723 三角形/13 对象。
- 入口总览:[site/map.html](../design/2026-10-07-visual-redesign/prototypes/site/map.html) 已加 R4 区块与完成矩阵。
- **R3→R4 同页面同视口对照**(用户点名的首要证据):shots/cmp-index-day.png / cmp-index-night.png(单图上下对照,原图 cmp-r3/r4-index-*.png 同目录)。
- 录屏:shots/rec/r4-entrance.webm(招牌入场:书页展开+扫光,已经 zai 复核内容)、r4-theme-toggle.webm、r4-mobile-nav.webm。

## 视觉要点

- 首页构图:场景满幅到视口边缘,不再是框内模型查看器;大标题 mix-blend-mode 叠印(昼 multiply/夜 screen),与纸面、导航、留白成一个构图。
- 昼夜:昼=纸纹+长影+朱砂书签;夜=页缝透光+冷轮廓(rim 0x6E9BFF)+相机向补光+材质 emissive 分层,造型不黑成剪影。
- 内页同一语言:关于页插图与 404 均重画为纸筑线稿(页扇/发光页/虚线页/朱砂书签;缺页意象),不再出现小院元素。
- 移动:竖屏相机自动拉远(aspect<1.2 按比例,上限 1.9),书页组与虚线页完整入画。

## 四项定点修复验证(均已实测)

1. **日报真实 Markdown**:r4/digest-2026-10-05.html 逐行对齐 assemble.py 输出——`### ` 纯文本标题(无链接)、来源链接在「理由」列表项内、`(源名 · 展示分 N)` 纯文本、一瞥标题即链接、人工纳入在括号内逗号后、空板块省略变体、cost_pending 两态引用行。截图 r4-digest-day-1.png。
2. **lightbox 原生 dialog**:site4.js 改用 `<dialog>.showModal()`;实测 `:modal` 匹配、焦点约束在对话框内、背景元素 focus 被 inert 拦截、Esc 关闭、焦点归还触发按钮。截图 r4-lightbox.png。
3. **reduced-motion 场景重绘**:book.js `setTheme` 在 immediate/reduced 下强制 `applyTheme + renderOnce`。两场景实测:初始深色(reduced 下直接呈现夜景完成态,r4-reduced-dark-init.png)、reduced 下主题切换立即重绘为昼(r4-reduced-switch-light.png)。
4. **环境动画暂停入口**:HUD「暂停动态/恢复动态」按钮,实测文案与 aria-pressed 同步切换、scene.isAmbientOn() 状态一致。

## 交互实测

拖拽环顾(有限范围)✓、点击发光页→post-hello.html ✓、复位视角 ✓、主题按钮三态联动场景 ✓、无 JS 走查(poster 降级+导航常显,r4-nojs-index.png)✓、移动菜单开合 ✓。

## 已声明未测/边界

- 真机(iOS/Android)未测,全部验证为桌面 Chromium + 模拟视口。
- WebGL 失败回退仅代码层审查(webglOK + import catch 双路径)。
- R3 保留为对照基线未动;`site/` 正式站页面未动;未提交未推送。
- 夜景沿用 lab-A 已验收参数;背景幕在夜景下的「大色块」观感已知,属可继续打磨项而非缺陷修复。

## 文件清单(新增/修改)

- 新增:prototypes/r4/(index/posts/post-hello/digest/digest-2026-10-05/about/404/search-m2 + assets/tokens4.css、base4.css、site4.js + 3d/book.js、boot4.js、three r180 两文件、poster 两张、ASSETS.md)
- 新增:prototypes/lab/r4-lab-a.html、r4-lab-b.html(试验,前轮已建)
- 修改:prototypes/site/map.html(R4 区块/矩阵/试验条目)
- 新增截图 shots/r4-*.png、cmp-*.png;录屏 shots/rec/r4-*.webm
- 修改:README.md(「从哪里读」更新 R4 入口)
