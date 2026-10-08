# R4「纸筑」3D 资产清单

概念:站是一本正在写的发光的书。实页=文章,发光页=最新文章,虚线页=日报(计划),朱砂书签带=当前位置。

## 运行时依赖

| 文件 | 来源 | 校验(SHA-256) |
|---|---|---|
| three.module.min.js | three r180,jsdelivr 固定版本,MIT | e2b5ee6b…(与 site/3d 同文件,完整值见 site/3d/ASSETS.md) |
| three.core.min.js | 同上 | 61ba0df0…(同上) |

本地化,无外网请求。与 R3 `site/3d/` 各持一份副本(两处独立目录,互不影响)。

## 源文件

| 文件 | 角色 |
|---|---|
| book.js | 场景模块(核心源资产):`PARAMS`(构图/书页/灯光/入场)与 `LIGHT`(昼夜参数表)均在文件头部导出;`createScene(host, opts)` 返回 `{setTheme, resetView, replay, setAmbient, isAmbientOn, start, stop, stats}` |
| boot4.js | 加载器:WebGL 检测→动态导入→画布淡入换 poster;HUD(暂停动态/复位视角);`nm-theme` 事件联动;失败静默回退 poster |
| poster-light.png / poster-dark.png | 实拍静态兜底(隐藏 HUD/标题后对 #scene3d 元素截图,1440×757) |

## 场景构成(实测 stats())

- 723 三角形 / 13 对象(`window.__bookscene.stats()` 实测,1440×860 桌面)。
- 主角:6 页扇形书页组(**书脊枢轴**:`bookPageGeometry` 局部 x=0 即书脊,页面向外弯出;
  各页 `rotation.y` 绕书脊展开,`spineGap=0.014` 微间距避免书脊处共面;
  完成态与入场全程页间零交叉,由 `tools/check-r4-book-geometry.mjs` 回归
  ——完成态 + 121 个展开采样截面检查 PASS);
  第 3 页为发光页(夜间 emissive + 暖光池),顶缘夹朱砂书签带(贴合弯曲页缘定位;夜间极弱暖红自发光,不沉成黑色)。
- 配角:弧形背景幕(w13 h9 curve 0.35,FrontSide 纸纹 + BackSide 裱背双 mesh)、2 张浮动样张页(可点→posts.html)、1 张虚线页(可点→digest.html)、种子随机 Canvas 纹理(纸纹/行线/地面,LCG 确定性)。
- 灯光:昼 sun 2.6 + 天光;夜 rim 0x6E9BFF 轮廓 + fill 0x93A8CC 相机向补光 + 暖光池 + 材质 emissive 分层(backing 0x22304A / panel emissiveMap / glow 0.9)。
- 透明纪律:纸页全程不透明(不透明深度测试队列);只有 fade 类元素(地面径向渐变、虚线页)使用透明,消除入场期透明排序闪烁。

## 交互与性能

- 拖拽环顾有限范围(az±0.30rad,el 0.18–0.58),Raycaster hover 抬升 0.35、点击导航(moved<6px 判定点击)。
- 按需渲染 needsLoop(入场中/主题过渡中/环境动效开且在视口);IntersectionObserver 0.05 + visibilitychange 暂停。
- 移动端:pixelRatio≤1.5、关阴影;竖屏自动拉远(camera.userData.zoom,aspect<1.2 时按比例,上限 1.9)。
- 入场分镜:书页 ry -0.62 展开(unfold)+ SpotLight 扫光(sin 包络,sweepAt 1.2s);reduced-motion → finishEntrance() 直跳完成态。
- setTheme:immediate 或 reduced-motion 下 `applyTheme + renderOnce` 强制重绘(评审定点 #3);其余情况 start() 插值过渡。
- 环境动效读者可控:HUD「暂停动态/恢复动态」按钮,aria-pressed 同步(评审定点 #4)。

## 复现拍摄与回归工具

- **poster 拍摄**:`r4/3d/poster-capture.html`(无 HUD/标题的纯净场景页,`?theme=dark` 拍夜景;
  视口 1440×757,等入场完成后整页截图)。本目录 poster-light.png / poster-dark.png 即其产物,与当前 book.js 几何一致。
- **几何回归**:`tools/check-r4-book-geometry.mjs`(`node` 直接运行,无浏览器/渲染依赖):
  对完成态与 121 个展开采样做书页截面交叉检查,任何穿插即失败。改 PARAMS.book 后应重跑。

## 缺测项

- 真机(iOS Safari / Android Chrome)GPU 与触摸拖拽未测,仅桌面 Chromium + 模拟视口。
- WebGL 失败回退路径只在代码层审查,未在真实无 WebGL 环境验证(boot4 有 webglOK 检测 + import catch 双重回退)。
