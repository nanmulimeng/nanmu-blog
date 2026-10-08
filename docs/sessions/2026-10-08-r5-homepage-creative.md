# 2026-10-08 R5 首页创意深化:字场 · 碑页

任务书:在 R4「纸筑」之上做一个明显超越的首页——两案实拍取舍、首屏完整构图、内容节奏重排、一段有记忆点的动态过程、昼夜双美术、手机端单独设计;按完整页面交付,保留 R4,新增独立 R5 原型。未改正式 site/、engine/;未提交未推送。

## 美术取舍(两案实拍 → 定案)

| 案 | 概念 | 实拍 | 结论 |
|---|---|---|---|
| A 案头剧场(lab/r5-lab-a) | R4 剧场书的改良:摊开的书 + 案头道具 + 虚空接触影 | shots/r5-lab-a-day.png | **弃选**:仍是 R4 变体,未正面回应"页面像示意板"的批评;实拍还暴露页扇背对相机成灰板的构图缺陷 |
| B 字场 · 碑页(lab/r5-lab-b) | 一页印着真实文章首段的稿纸立成碑,微弓弯曲;左缘线装 4 订眼穿朱砂 3D 线;左侧竖排标题对望;夜览背光透纸(纸亮字沉为剪影)+ 冷蓝轮廓光 | shots/r5-lab-b-day.png / r5-lab-b-night.png | **选定并深化**:真实文章本身成为材质,直接回答"示意板"问题;竖排标题与碑页对望有构图张力;朱砂装订线可延伸进 2D 页面;夜览透光是 A 没有的戏剧性 |

吸收:把 A 案"虚空 + 接触影"的优点并入 B——去掉 R4 的背景板与网格地面,改 radial-gradient 接触影 + ShadowMaterial 地板。

## 交付内容(r5/ 原型)

- **首屏完整构图**:碑页场景(右)与竖排标题「先把最小的东西做完」+ 作者定位句 + 两个阅读按钮(左)对望;核心内容与按钮在正常文档流,不要求拖拽/悬停/看完动画。无 JS / WebGL 失败时 poster 静态图同样成立。
- **碑页真实排印**:1024×1460 canvas 纹理,`document.fonts.load` 后绘制真实文章标题/日期/首段(逐字 measureText 换行);文字左边距让出装订线位;线装为 3D 线环+线段,贴弯曲页面局部坐标。
- **内容节奏**:精选文章大区块(真实摘要两段,忠实改写自原文 + 专门设计的封面卡:装订线/4 孔/印章/行线,hover 转正浮起)→ 日报空态(虚线稿纸,准确写"暂无已发布日报",无虚构)→ 这个站窄栏(只用已知事实)→ 订阅书签卡(打孔)+ footer。大与小、疏与密、静与动交替。
- **动态过程**(入场 / 滚动衔接 / 交互分别交付证据):
  1. 入场:碑页立起(2.8s)+ 扫光(sweepAt 1.0)+ 内容区 reveal;
  2. 滚动衔接:碑页左缘朱砂装订线落进页面左侧 2D thread,scaleY 随滚动延伸,4 个 knot 节点对应 #posts/#digest/#about/#subscribe 逐一点亮——书签延续为栏目标识;
  3. 交互:拖拽环视(az/el 钳制)、悬停碑页抬升+微亮、点击跳转文章、暂停/恢复(aria-pressed 同步)。
  不锁滚动、reduced-motion 直跳完成态且线全显全亮、无 JS 不出现 thread 且内容完整。
- **手机端单独设计**:场景上置(56dvh,order 调整而非缩小桌面模型)、标题转横排、按钮全宽在文档流、HUD 贴场景下缘;scrollWidth 375 ≤ 390 无横向溢出。
- 内页 7 个复用 R4(引用 ../r4/assets/*),仅首页为新设计。map.html 已加 R5 区块;`r5/3d/ASSETS.md` 记录参数/灯光/复现流程/缺测。

## 验证结果(桌面 Chromium + 模拟移动视口,逐项实测)

| 项 | 结果 | 证据 |
|---|---|---|
| 几何回归(穿插防线) | PASS:弓深 0.091、后衬页错层、ghost 距离 3.08 | `node tools/check-r5-geometry.mjs` |
| 入场动画 | 立起平滑、扫光自然、静止完成态稳定 | 录屏 shots/rec/r5-entrance.webm(AI 复核通过) |
| 朱砂线滚动 | scaleY 随滚动(实测 0.428@中段),节点按节点亮 | 录屏 shots/rec/r5-thread-scroll.webm + shots/r5-dev-thread-mid.png + 脚本断言 |
| 交互三项 | 拖拽钳制/悬停无闪变(自截四帧)/点击落地 post-hello.html(URL 断言) | 录屏 shots/rec/r5-interact.webm + shots/r5-dev-hover-*.png |
| 桌面昼夜全页 | 构图、对比度、内容完整 | shots/r5-full-day.png / r5-full-night.png |
| 手机 390 昼夜全页 | 场景上置、无横向溢出、按钮可达 | shots/r5-mobile-day.png / r5-mobile-night.png |
| R4/R5 同视口昼对照 | 差异在构图/字体/材质/光影,非换色 | shots/r4-vs-r5-hero-r4.png / r4-vs-r5-hero-r5.png |
| reduced-motion | 直跳完成态、线全显、节点全亮、主题切换 400ms 内重绘(4 断言) | shots/r5-dev-reduced-day/night.png + 脚本断言 |
| 无 JS | poster 显示、无 thread、内容完整 | shots/r5-dev-nojs.png |
| WebGL 失败 | 回退 poster、内容完整 | shots/r5-dev-nogl.png |
| 暂停/恢复 | 文案与 aria-pressed 一致 | 脚本断言 |

全页截图曾两轮拍成空白:reveal 未触发,根因 `scroll-behavior:smooth` 使 scrollTo 平滑化;改 `behavior:'instant'` + 断言"无未 reveal 元素"守门后重拍,最终图与代码一致(thread 加粗 3px 后重拍)。

AI 录屏复核两次误报(thread 不存在/悬停闪变),均以自截帧 + transform/URL 断言反驳后定论;AI 复核只作参考,不作终审。

## 未覆盖项(如实声明)

- 真机 iOS/Android 与触摸拖拽未测(仅 390 视口模拟);桌面 Firefox/Safari 未开浏览器实测;非本机 GPU 的 WebGL 表现未测。
- 碑页文字为 canvas 排印,文章标题变更需改 scene5.js 常量并重拍 poster(自动化未做)。
- R5 是否取代 R4 成为当前视觉方向,留待用户评审定夺,本轮不自封。

## 边界

仅新增/修改 docs/design/2026-10-07-visual-redesign/{prototypes,shots,tools} 与本报告;README/map.html 加索引行;未改正式 site/、engine/、服务器;未提交、未推送。
