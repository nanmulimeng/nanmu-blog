# R5「字场 · 碑页」场景资产说明

R5 首页 3D 场景的源文件、参数与复现流程。场景由 `scene5.js` 单文件生成,无外部模型/贴图文件(页面临摹字纹理为运行时 canvas 绘制)。

## 文件

| 文件 | 角色 |
|---|---|
| `scene5.js` | 场景源。导出 `PARAMS`、`LIGHT`、`steleGeometry()`、`createScene(host, opts)`(async,返回 api) |
| `boot5.js` | 首页加载器。等 `createScene`,挂 `window.__bookscene`;WebGL 失败回退 poster |
| `poster-capture.html` | 备用图拍摄页(非公开页)。`?theme=dark` 拍夜览;完成后置 `window.__captureReady=true` |
| `poster-light.png` / `poster-dark.png` | 1440×786 静态备用图(无 JS / WebGL 失败时显示) |

## 场景构成(13 个对象,实测 1647 三角形)

1. **碑页**:弓形弯曲稿纸(`steleGeometry`,z 向弓深实测 0.091),贴 1024×1460 canvas 纹理——真实文章标题/日期/首段逐字排印(`document.fonts.load` 后 measureText 换行,左边距 TM=152 让出装订线),anisotropy 8。
2. **后衬页 ×2**:同形暗影页错层(offset 见 PARAMS.backs)。
3. **线装**:4 订眼,朱砂线 = Torus(0.085/0.026) 线环 + Cylinder(0.02) 线段,贴弯曲页面局部坐标。
4. **虚线页**(ghost):远处小页,构图呼应。
5. **ShadowMaterial 地板**:只接影不显示面(替代 R4 的网格地面与背景板)。
6. 灯光组:hemi + sun(带影)+ rim(夜)+ fill + back 点光(夜,透纸)+ sweep(入场扫光)。

## 参数表(PARAMS)

```
cam:    fov 34, r 16.4, az 0.30, el 0.17, azSpan 0.18, elMin 0.10, elMax 0.38, ty 3.55,
        txM 1.55, zoomMax 2.1
        竖屏: zoom = min(zoomMax, max(1, 1.02/aspect));
        lookAt 目标随 txK(0 横屏→1 竖屏)向碑页一侧移 txM,保住右缘与装订线
stele:  w 5.2, h 7.4, curve 0.14, x 2.1, ry -0.16
backs:  [dx -1.25, dz -1.15, tone 0.80], [dx -2.3, dz -2.3, tone 0.58]
binding:x 0.075(左缘), holes 4
ghost:  w 2.0, h 2.85, x 5.1, y 1.6, z -0.7, ry -0.5
entrance: 2.8s 立起,sweepAt 1.0 扫光
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

夜览透光:emissiveMap 用同一张字纹理(字暗纸亮 → 背光时纸亮字沉为剪影);纸面层次全部来自纹理的弓面明暗带 + 左亮右暗 wash(夜间均匀发光面靠它们成形);主题切换按 t 插值全表。

## 纹理与排印

1024×1460 canvas;`document.fonts.load` 后绘制《你好,nanmu-blog》**首段全文摘录**(逐字 measureText 换行;左边距 TM=152 让出装订线);订孔带径向渐变穿透感;弓面明暗带 + 页缘切面;anisotropy 8。字体失败时回退系统衬线仍排印(素纸之上仍有真实文字)。

## 运行时规则(修正轮补)

- **texReady 时序**:boot5 等 `scene.texReady`(3.5s 超时保护)才把场景淡入并移除 poster——访客不会看到素纸突变成文字页;纹理失败回退素纸场景并告警。
- **按需重绘**:暂停动态/reduced-motion 下渲染循环停止,但用户主动操作(拖拽、复位)与窗口变化(`resize`)都会 `renderOnce()` 立即重绘——环境动画与用户操作分开处理。
- **入场与悬停组合**:`stepEntrance` 写入的入场位移之上叠加悬停抬升与环境浮动,不再同帧覆盖;鼠标停在碑页上加载/重放,入场连续无跳变。
- **落线(thread-drop)**:boot5 创建两段直角朱砂线——竖段自碑页装订线底部孔(`api.projectBindingBottom()` 实时投影)垂落,横段沿 main.flow 顶走到正文 thread 起点;hero 在视口内随帧更新,滚出即隐;≤900px 不创建显示。
- **朱砂线节点**:普通与 reduced-motion 两种模式都执行 `layoutKnots()` 定位;resize 与 `document.fonts.ready` 后重算。

## 几何回归

```bash
node tools/check-r5-geometry.mjs
```

**口径**:本脚本是参数间距防线——断言弓深 <0.2、后衬页 |dz|>0.4、相邻后衬页间距 >0.4、ghost 与碑页中心距 >(w1+w2)/2×0.8。它不做完整三维交叉检测、不采样动态状态;PASS 只代表当前参数组合满足保守间距阈值,不能单独表述为"任意时刻无穿插"的证明。当前输出:`PASS: stele bow depth 0.091, backs offset ok, ghost distance 3.08`。**改 PARAMS 几何或展开方式后必跑**(对应 R4 的书页穿插教训)。

## poster 复现

```bash
python -m http.server 8931 --bind 127.0.0.1   # 在 prototypes/ 根起服
# 浏览器或 Playwright 开 r5/3d/poster-capture.html(?theme=dark 拍夜览),
# 等 window.__captureReady === true 后截 #scene,1440×786
```

注意 Playwright 截图须用绝对路径(相对路径解析到仓库根而非页面 cwd)。

## 已验证 / 缺测

已验证:桌面 Chromium 昼夜、移动 390 视口昼夜、reduced-motion(直跳完成态)、无 JS 与禁 WebGL 回退 poster、拖拽/悬停/点击导航、暂停恢复(aria-pressed)。

缺测:真机 iOS/Android 与触摸拖拽、桌面 Firefox/Safari、非本机 GPU 上的 WebGL 表现。
