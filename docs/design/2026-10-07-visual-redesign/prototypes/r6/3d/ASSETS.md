# R6「字场 · 换页碑」场景资产说明

R6 首页 3D 场景的源文件、参数与复现流程。场景由 `scene6.js` 单文件生成,无外部模型/贴图文件(页面文字纹理为运行时 canvas 绘制)。承 R5「碑页」,差异:一页碑 → 一叠三张内容页(文章/日报/这个站),页签选择换页。

## 文件

| 文件 | 角色 |
|---|---|
| `scene6.js` | 场景源。导出 `PARAMS`、`LIGHT`、`steleGeometry()`、`createScene(host, opts)`(async,返回 api) |
| `boot6.js` | 首页加载器。等 `createScene`,挂 `window.__bookscene`;`onSelect` 把 3D 内点选换成 `nm-page` 事件;WebGL 失败回退 poster |
| `poster-capture.html` | 备用图拍摄页(非公开页)。`?theme=dark` 拍夜览;完成后置 `window.__captureReady=true` |
| `poster-light.png` / `poster-dark.png` | 1440×850 静态备用图(无 JS / WebGL 失败时显示) |
| `three.module.min.js` + `three.core.min.js` | three r180 本地固定(两个文件都必须存在,module 文件会再引 core) |

## 场景构成(27 个对象,实测 4351 三角形)

1. **内容页 ×3**:弓形弯曲稿纸(`steleGeometry`),各贴 1024×1460 canvas 纹理——
   文章页(真实标题/日期/首段摘录逐字排印)、日报页(空态稿纸:栏目抬头+虚线行+准确状态)、站点页(三层结构简图,在线层实线/计划层虚线)。
2. **槽位系统**:槽位 0=前景中央,1/2=后左错层(见 PARAMS.slots);换页=页面在槽位间迁移,退出页 z 向弧出(`sin(e·π)×1.0`)避免路径中点与进入页相交。
3. **线装一组**:朱砂线环+线段只挂在前景页(`binding.visible` 随 `select` 移交)——一叠稿纸共用一组装订,避免三串订环悬空;后排页只露纹理上的订孔。
4. **虚线页**(ghost):远处小页,构图呼应(检索计划)。
5. **ShadowMaterial 地板** + 接触影。
6. 灯光组:hemi + sun(带影)+ rim(夜)+ fill + back 点光(夜,透纸)+ sweep(入场扫光)。

## 参数表(PARAMS)

```
cam:    fov 34, r 16.4, az 0.30, el 0.17, azSpan 0.18, elMin 0.10, elMax 0.38, ty 3.55,
        txM 1.55, zoomMax 2.1
        竖屏: zoom = min(zoomMax, max(1, 1.02/aspect));
        lookAt 目标随 txK(0 横屏→1 竖屏)向页叠一侧移 txM,保住右缘与装订线
page:   w 5.2, h 7.4, curve 0.14, x 2.1, ry -0.16
slots:  [0,0,0] / [dx -1.25, dy -0.28, dz -1.15] / [dx -2.3, dy -0.52, dz -2.3]
binding:x 0.075(左缘), holes 4
ghost:  w 2.0, h 2.85, x 5.1, y 1.6, z -0.7, ry -0.5
entrance: 2.8s 立起,sweepAt 1.0 扫光
swapDur: 0.95s 换页
```

## 灯光表(LIGHT)

| 项 | 昼 | 夜 |
|---|---|---|
| sky / fog | #F0EDE5 / 0.012 | #090C12 / 0.016 |
| hemi(S/G) | #E9E5D9/#8F8A7B ×0.9 | #18202F/#04060A ×0.34 |
| sun | #FFEFD4 ×2.5 @(-6,13,9) | #8FA8D8 ×0.18 @(7,10,-8) |
| rim 轮廓光 #6E9BFF @(9,6,-8) | 0 | 2.3 |
| back 点光 #FFBE6E @(x-1.1,3.6,z-1.6) 距离10 | 0 | 1.6(偏装订线侧,左亮右暗) |
| fill #C8D2E4 @(-8,4,11) | 0.3 | 0.15 |
| 页面透光 pageEmI | 0.04 | 0.55 |
| 地面影 opacity | 0.18 | 0.5 |
| 朱砂 seal emissive | 无 | #8A2E18(夜间线装可读) |

夜览透光:emissiveMap 用同一张字纹理(字暗纸亮 → 背光时纸亮字沉为剪影);纸面层次全部来自纹理的弓面明暗带 + 左亮右暗 wash;主题切换按 t 插值全表。

## 纹理与排印

1024×1460 canvas,三页共用 `paperBase`(纸底噪点纤维)+ `pageHead`(朱砂印+栏目名)+ `paperFinish`(弓面明暗带/页缘/订孔)。文章页排印《你好,nanmu-blog》**首段全文摘录**(逐字 measureText 换行;左边距 TM=152 让出装订线);日报页与站点页只用真实状态文案(暂无日报/三层关系),无虚构内容。

**字体就绪门控(本轮修复)**:`document.fonts.load` 必须带实际排印的汉字样本(SAMPLE 覆盖三张纹理全部文案)——默认文本是空格,空格不需字形,load 会立即 resolve,纹理将用系统回退字体排印。R5 的 `fontsReady()` 存在同一隐患,未回修(R5 冻结为比较基线)。

## 运行时规则

- **texReady 时序**:boot6 等 `scene.texReady`(3.5s 超时保护)才把场景淡入并移除 poster;纹理失败回退素纸场景并告警。
- **按需重绘**:暂停动态/reduced-motion 下渲染循环停止,但用户主动操作(拖拽、复位)与窗口变化都 `renderOnce()` 立即重绘。
- **换页**:`select(pid)` 交换槽位并播放 0.95s 弧出补间;动画中再次 select 忽略(状态可预期);reduced-motion 立即完成 + renderOnce。`needsLoop` 含 swap——暂停动态时换页动画照常播放。
- **双向联动**:页签点击 → `__bookscene.select(pid)`;3D 内点后排页 → `onSelect` → `nm-page` 事件 → 页签/面板同步(site6.js)。点前景页进栏目链接。
- **落线(thread-drop)**:自前景页装订线底孔(`api.projectBindingBottom()`,换页后跟随新前景页)直角两段接入正文 thread;hero 在视口内随帧更新;≤900px 不显示。
- **朱砂线节点**:普通与 reduced-motion 两种模式都执行 `layoutKnots()`;resize 与 `document.fonts.ready` 后重算。

## poster 复现

```bash
# 在 prototypes/ 根起服(建议带 Cache-Control: no-store,否则静态资源缓存会盖住改动)
python -m http.server 8934 --bind 127.0.0.1
# 浏览器或 Playwright 开 r6/3d/poster-capture.html(?theme=dark 拍夜览),
# 等 window.__captureReady === true 后约 3.8s(入场结束)截 #scene,1440×850
```

注意 Playwright 截图须用绝对路径(相对路径解析到仓库根而非页面 cwd);录屏须在新 context 创建时指定 recordVideo。

## 已验证 / 缺测

已验证(桌面 Chromium 1440×850,2026-10-09):页签→3D 换页与 3D→页签双向联动、换页中帧无穿插(连拍)、落线跟随前景页、封面卡→文章页头跨页 View Transition(pagereveal 双向确认)· reduced-motion(入场即完成/换页立即/节点定位/拖拽重绘)、暂停后拖拽+resize+换页+复位组合、字体延迟 2.5s 下 poster 保留与真字体替换、移动 360/390/430 构图与无横向溢出、直接访问文章 URL、目录 scrollspy、复制盖印。

缺测:真机 iOS/Android 与触摸拖拽、桌面 Firefox/Safari(跨页 View Transition 在不支持的浏览器自动降级为普通跳转,按设计)、非本机 GPU 上的 WebGL 表现。
