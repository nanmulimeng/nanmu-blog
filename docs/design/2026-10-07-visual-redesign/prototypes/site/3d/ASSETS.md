# 3D 小院 · 资产清单(R3)

场景为**程序化建模**:`courtyard.js` 即源资产,`PARAMS` 参数表可调整重建,无外部模型文件、无付费素材。

## 文件

| 文件 | 字节 | 说明 |
|---|---|---|
| `courtyard.js` | 22,297 | 场景源码:参数表、纸纹生成、建模、灯光、入场分镜、交互、主题插值 |
| `boot.js` | 2,096 | 加载器:WebGL 检测 → 动态导入 → 海报换画布 → HUD;失败静默回退 |
| `scene.html` | 4,311 | 独立演示/调试页(交互说明 + 参数表 + 运行时几何量回填) |
| `poster-light.png` | 72,757 | 昼态静态降级图,从实际场景截取(已隐藏 HUD) |
| `poster-dark.png` | 80,331 | 夜态静态降级图,同上 |
| `three.module.min.js` | 338,908 | three.js r180,MIT |
| `three.core.min.js` | 381,124 | three.js r180 核心(r167+ 拆分,module 依赖它) |

## 依赖

- three.js **0.180.0**,MIT 许可,来自 jsdelivr 固定版本:
  `https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.min.js`(及 `three.core.min.js`)
- SHA-256 锁定:
  - `three.module.min.js` = `e2b5ee6bccd38fd6d8a2428546b83c5f2426d84b152ef82be8055556e3b40eb6`
  - `three.core.min.js` = `61ba0df005b05991361d040d8ff670e1aadfd0ce7aeebd1fdb0725957a8957de`
- 无其他运行时依赖;无构建步骤,`<script type="module">` 直引。

## 几何量(运行时实测,`__courtyard.stats()`)

- **619 三角形 · 38 个场景对象**(桌面与移动一致;移动端仅关阴影、降 pixelRatio)

## 纹理

- 纸纹为运行时 Canvas 生成,`paperTexture(hex, seed)` 种子随机、**确定性**(同种子同图);无二进制纹理资产。

## 镜头与灯光

- 镜头:fov 36 · 半径 15.5 · 方位 0.64rad(拖拽 ±0.24rad)· 仰角 0.42–0.72rad;`resetView()` 回主镜头。
- 灯光:`LIGHT.day` = 半球光 + 暖色平行光(投影);`LIGHT.night` = 冷平行光(相机侧)+ 窗内点光;主题切换时参数逐帧插值,窗灯/门前光池乘以入场末拍的点灯系数。

## 交互与降级

- 拖拽环顾(Pointer Events,`touch-action:pan-y` 保留页面滚动)· 悬停房间抬升 · 点击正房/东厢/留白分别进文章/日报/关于 · HUD「复位视角」。
- 降级链:无 WebGL 或模块加载失败 → 静态 poster(昼夜各一,随主题切换);`prefers-reduced-motion` → 直跳完成态 + 按需渲染;`visibilitychange`/`IntersectionObserver` 离屏暂停;等价 HTML 入口永远在场景之外(导航与首屏链接)。

## 测试条件与缺测项

已实测(Chromium/Playwright,Windows 桌面):入场分镜、拖拽、点击导航、复位、昼夜切换、reduced-motion 完成态、无 JS 海报降级、移动 390 视口布局。
缺测:**真机**(iOS Safari / Android Chrome 的 WebGL 与触控拖拽)、离屏暂停的电量收益、低 GPU 机型帧率——接入正式站前建议补一轮真机走查。
