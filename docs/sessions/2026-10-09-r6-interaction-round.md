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
- 3D 页面上小字(27px 纹理)在日光下偏淡,与 R5 同水平,是否可接受留待评审。
- 内页除 post-hello 外仍是 R4 样式原样复制(R6 范围聚焦首页与阅读过渡;全站套用按指令暂缓)。

---

# 定点修正轮(2026-10-09 下午,检查点 74dd36e 之后)

四组修正全部落地并验证;验证针对 R6 实现本身(非 R5 几何复用)。以下「实测」均为桌面 Chromium + Playwright,对 no-store 服务器(8934)上的交付代码执行。

## 修正 1:三处选择状态统一(scene6.js、boot6.js)

- `select()` 在换页动画中不再拒绝新选择:存入 `pendingSelect`(后到覆盖先到),动画完成后执行;页签/面板点击即切换(即时反馈),3D 排队跟上,三方最终一致。
- boot6 在场景就绪后把当前选中页签同步给场景(覆盖"场景加载期间已点过别的栏目")。

实测:场景就绪前点「日报」→ 就绪后 scene/页签/面板三方 digest 一致;120ms 间隔连点 about→posts→digest → 终态三方 digest(最后一次点击);暂停动态下点页签 → 换页动画照常、三方一致。

## 修正 2:手机横向滚动条(scene6.js resize)

**越界节点:3D 画布**。`resize()` 用 `host.clientWidth`(四舍五入整数)——宿主实宽 374.67px 时读出 375,画布比容器宽 0.33px,整数 DOM 度量(scrollWidth/clientWidth/元素矩形)全部显示"无溢出",但经典滚动条系统(Windows 窄窗)仍渲染页面级横向滚动条。实锤路径:像素复检确认三张交付手机截图底部均有滚动条色带 → DOM 扫描无越界 → `window.scrollX` 出现 0.667 残值暴露亚像素溢出 → 逐段排除后锁定画布 375px > 宿主 374.67px → 画布压到 374px 后滚动条消失。

修复:resize 改用 `getBoundingClientRect()` + 向下取整,画布永不超宿主(非全局裁切)。实测复测 360/390/430(昼/夜):画布分别 344/374/414,均比宿主窄 ≥0.67px,maxX=0,三张新截图(shots/r6-fix-m360-day / r6-fix-m390-day / r6-fix-m430-night.png)底部像素复检无滚动条色带;桌面 1440 同样 mx=0。

## 修正 3:三层双向操作与键盘(index.html、site6.js、base6.css)

- 分层图纸卡由 `<span aria-hidden>` 改为 `<button aria-pressed>`,点击/Enter/Space 展开对应说明,与手风琴双向同步(openLayer 统一维护 .on/aria-expanded/aria-pressed)。
- `.ly.on` 去掉 `border-style:solid`——实线=在线、虚线=计划的语义不再被高亮覆盖;选中态只改颜色/位移/阴影/底色。
- 首页 tabs 补齐 ARIA 键盘行为:方向键/Home/End 移动并选中,漫游 tabindex(选中页签 0,其余 -1)。

实测:点图卡「个人检索」→ 手风琴 search 展开、正文可见、pressed=true;选中态 search 仍 dashed、posts 仍 solid;手风琴→图卡反向同步 digest 仍 dashed;图卡键盘 Enter 展开;tabs ArrowRight/End/Home 选中+聚焦+3D 同步,tabindex 分布正确。

## 修正 4:reduced-motion 转场声明顺序 + 分入口挂名(base6.css、site6.js)

- `@view-transition{navigation:auto}` 移到 reduced-motion 块**之前**(同优先级后者胜,原顺序 none 被 auto 覆盖、形同虚设)。
- 封面卡不再 CSS 常驻 `view-transition-name`(常驻会让屏幕外封面在无关导航里飞入)。按入口分别定义:点击可见封面 → 点击时挂名 morph 进页头;「读全文」按钮 / 3D 入口 → 不挂名,仅根过渡;返回 → 页头常驻名 + 首页 pagereveal 检测到 VT 时补挂封面名。

实测:加载后封面 computed name=none;点击封面挂名 latest-cover;样式表规则顺序 auto 在前、reduced-motion none 在后;「读全文」真实导航到文章页(页头名 latest-cover),返回时首页 pagereveal 补挂封面名(回程 VT 发生);emulate reduced-motion 下点击封面再返回,封面未补挂名(VT 整体禁用,navigation:none 生效)。

## R6 三页换位几何(本轮新验,非 R5 复用)

三页循环互换 posts→digest→about→posts,各取中帧与终态截图(shots/r6fix-swap-pd/da/ap-mid/final.png):中帧退出页弧出、两页分离无穿插,终态构图正常;排队链 about→posts(120ms)中帧(shots/r6fix-swap-chain-mid.png)三页分离,终态 scene=页签=posts。回归:暂停/恢复 aria 与状态双向正确;check_docs 0 错;git diff --check 干净。

**源码推断(未逐项实测)**:posts/digest/about/search-m2/404 等 R4 复制内页未受本轮文件改动影响(改动仅 r6/index.html、base6.css、site6.js、scene6.js、boot6.js)。**未测环境**:真机触摸、iOS Safari、Firefox(VT 降级路径按设计为普通跳转)。
