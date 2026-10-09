# R6「字场 · 换页碑」交互创意深化轮报告(2026-10-09)

指令:R5 为底稿,转向交互创意——让访客的操作产生有意义的状态变化、内容发现和视觉回应。三个完整体验:会回应的首页目录、封面进入正文再返回、首页下半部的新发现(「这个站」深化)。保留 R5 修正轮验收项。仍在独立原型,不接入正式站。

## 交付概览

| 体验 | 做法 | 证据 |
|---|---|---|
| 会回应的首页目录 | 碑变为一叠三张内容页(文章/日报/这个站)。页签 ↔ 3D 页叠**双向联动**:点页签 → 对应页弧出换到前景 + 预览面板同步;点 3D 后排页 → 换页 + 页签同步(nm-page 事件);点前景页 → 进栏目 | shots/r6-about-front.png、shots/r6-swap-mid1/2.png、录屏 |
| 封面→正文→返回 | 跨页 View Transition(渐进增强):首页封面卡与文章页稿纸页头共名 `latest-cover`,进出双向 morph;普通链接不劫持,直接访问文章 URL 正常,不支持的浏览器自动降级普通跳转 | shots/r6-post-head.png;pagereveal 双向确认(见下) |
| 「这个站」新发现 | 三层结构图 + 手风琴联动:分层纸卡(在线层实线/计划层虚线)与可展开说明互相同步高亮;替换重复文字 | shots/r6-layers.png |
| 精细反馈 | 复制 RSS 盖「已录」小印(按下-落定-微斜);页签选中为朱砂书签(顶部垂线绳);导航选中态承 R5;阅读页目录 scrollspy 标记当前节 | shots/r6-copy-stamp.png、shots/r6-post-scrollspy.png |

主页昼夜:shots/r6-hero-day.png / r6-hero-night.png;与 R5 同视口对照:shots/r6-vs-r5-r5.png vs r6-hero-day.png。访客全流程录屏(选择内容→进入文章→阅读→返回→订阅,真实节奏未剪辑):shots/rec/r6-visitor-flow.webm(23s)。

## 场景改动(scene6.js,承 R5)

- 单页碑 → 三页槽位系统:槽位 0 前景、1/2 后左错层;`select(pid)` 交换槽位,退出页 z 向弧出(`sin(e·π)×1.0`)避免路径中点与进入页相交;动画中重复 select 忽略;reduced-motion 立即完成。
- **线装只有一组**,挂在前景页,换页时 `binding.visible` 移交——三串订环悬空的视觉问题由此消除(一叠稿纸共用一组装订,语义也通)。后排页只露纹理订孔。
- 纹理系统重构为三页共用 `paperBase/pageHead/paperFinish`;日报页为空态稿纸、站点页为三层简图,均只用真实状态文案。
- **字体门控修复(本轮新发现)**:`document.fonts.load()` 默认文本是空格,空格不需要字形,load 会立即 resolve——R5 的 `fontsReady()` 因此形同虚设,纹理在字体未就绪时就用系统回退字体排印(实测确认)。R6 改为携带覆盖三张纹理全部文案的汉字样本。**R5 存在同一隐患,未回修(R5 冻结为比较基线)**。
- 订孔纹理减淡(径向渐变 r17→13,alpha 降),避免后排页露出部像霉斑。

## 页面改动

- index.html:页签目录块(toc-block)定位在 hero 左下(承 R5 hero-actions 位),不遮前景页文字;「这个站」改为分层图+手风琴;其余承 R5 修正轮。
- base6.css:R6 增量段(页签/面板/三层图/盖印/VT 规则/移动端);竖排标题字号改为 `min(4.4vw, 5.4vh)` 双约束——目录块占位后矮视口(850px)下标题曾折成两列,已修;v-sub 文案收紧防折列。
- post-hello.html:页头改为与封面卡同构的稿纸页头(装订线/订孔/印/标题/行纹,VT 目标);目录加 scrollspy 阅读书签;仍引用 R4 内页资源,未机械套用全站。
- boot6.js:承 boot5(texReady 门控/HUD/主题联动/落线),`onSelect` → `nm-page` 事件。

## 验证结果(全部在桌面 Chromium 实测;Playwright 自动化)

| 项 | 结果 |
|---|---|
| 页签→3D 换页 | current/panel/aria-selected 同步;换页中帧连拍两页分离无穿插 |
| 3D→页签反向 | 点后排页 → select + 页签同步,URL 不跳转 |
| 换页动画中再点 | 忽略(状态可预期) |
| 落线跟随 | 换页后 projectBindingBottom 取新前景页,落线 x 随之移动 |
| 跨页 VT | pagereveal `e.viewTransition` 去程/返回均为 true(真实浏览器行为);reduced-motion 下 `navigation:none` 禁用 |
| reduced-motion | 入场即完成态;换页立即;4 节点定位并全亮;拖拽触发重绘(像素断言) |
| 暂停后主动操作 | 暂停→拖拽(重绘)→resize(重绘)→换页(动画照常)→复位→恢复;aria-pressed 双向正确 |
| 字体延迟(2.5s,冷缓存) | poster 保留、host 透明;放行后纹理以 Noto Serif SC 排印后替换(early/late 图) |
| 手机 360/390/430 | 构图完整(三页叠+装订线+标题+页签),无横向溢出;页签 44px 触控 |
| 直接访问文章 URL | 页头/目录/进度条正常 |
| 录屏 AI 复核 | 流程事件齐全,无黑屏卡顿(仅参考,以脚本断言与截帧为终审) |

**自动化环境现象(非真实用户行为)**:Playwright `goto` 默认等 load 事件,而字体的进行中的请求会拖住 load——字体延迟测试若用默认 goto 会量不到延迟窗口,须 `waitUntil:'domcontentloaded'`;python http.server 不发缓存头时浏览器启发式缓存会盖住改动的 CSS/JS,联调需 no-store 服务器。

**尚未验证的推断**:真机触摸拖拽与 iOS Safari;Firefox/Safari 的 VT 降级路径(按设计为普通跳转,未实测);非本机 GPU 性能。

## 已知边界

- 跨页 VT 的 morph 是封面卡(竖版)与页头(横版)之间的形变,首访即成立;若从面板「读全文」进入,封面卡在首屏外,VT 仍会以其屏幕外快照参与(视觉为卡从下方飞入),未视作缺陷。
- 3D 页面上小字(27px 纹理)在日光下偏淡,与 R5 同水平,评审已接受该浓度。
- 内页除 post-hello 外仍是 R4 样式原样复制(R6 范围聚焦首页与阅读过渡;全站套用按指令暂缓)。
