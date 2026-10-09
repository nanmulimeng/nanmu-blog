# 会话交接:R6 批次 3 兼容验收与现网基线——Firefox/WebKit/Caddy(2026-10-10)

- **recorded_at**: 2026-10-10 00:40 Asia/Shanghai
- **continues**: [2026-10-09 批次 3 性能与兼容测量(第一部分)](2026-10-09-r6-batch03-perf.md)(Lighthouse+CLS 修复,424f22a)
- **repository**: 起点 HEAD = 424f22a;分支 `codex/r6-interaction`(仅本地,未推送/未合并/未部署)
- **objective**: 按用户批次 3 指令完成剩余兼容与基线项:Firefox 验收(内容/导航/主题/3D 降级/暂停/reduced-motion)、Safari 有条件就实测否则登记待验、生产 Caddy 现网只读基线(用户已授权只读检查)。停止边界同前:不合并 main、不推送、不部署、不操作服务器(只读 curl 除外)

- **firefox**(`scripts/verify_browser_firefox.py` 入库,可复跑):
  - 覆盖 14 项:内容矩阵五页+404+console 零 pageerror、导航(4 链接+点击+aria-current)、主题三态(light→dark 序列+localStorage 持久+重载保持)、3D boot(tris 4351)/页签联动/暂停组合(暂停→select→拖拽→resize→复位→恢复)、**WebGL 禁用降级**(launch `firefox_user_prefs={'webgl.disabled': True}`→no-webgl 类+poster 常显+无 HUD+页签仍切+零 3D 请求)、reduced-motion(scrollBehavior auto+transitionDuration≈0+404 animationName none)
  - 结果:**14/14 PASS**,firefox 146.0.1;首轮 13/14——唯一 FAIL 是 fx/index 的 tabs 断言选择器笔误(`.tpanel-tabs` 不存在,实为 `.page-tabs`,验收脚本缺陷非产品缺陷),修正后全绿;两轮完整输出均归档
- **webkit**(`scripts/verify_browser_webkit.py` 入库,可复跑):
  - **口径声明(docstring 首行):Playwright WebKit 26.0,非真机 Safari**——只作补充信号,不代替 Safari 结论;真机无设备,登记待验不用模拟代替
  - 覆盖 13 项(同 Firefox 结构去掉 WebGL 降级段:WebKit 无 `webgl.disabled` 等价启动通道,该路径 Chromium 启动参数+Firefox pref 双覆盖)
  - 结果:**13/13 PASS** 一次通过;运行时本轮 `playwright install webkit` 新装(webkit-2248,58.7MB)
- **caddy_baseline**(现网只读,用户已授权):
  - curl GET/HEAD × 压缩/未压缩,直连与经代理各验(代理多一跳 CONNECT,响应头不变);归档 logs/r6-b3-caddy-baseline.log
  - 事实:旧版(M0 上线版)为**单文件 HTML**(CSS 全内联,零外部 CSS/JS/字体请求);首页 gzip 1183B/原始 2371B,文章页 gzip 2101B(chunked)/原始 3627B;Etag 强校验+`Vary: Accept-Encoding`+`Alt-Svc: h3`+`Server: Caddy`;Last-Modified 2026-10-07
  - 口径发现:HEAD+Accept-Encoding 时 Caddy 回 `Content-Length: 20`(空压缩流占位),与 GET 实际 gzip 长度不符——**长度口径以 GET 为准**;未压缩时 HEAD/GET 长度一致且多 `Accept-Ranges: bytes`
  - 边界:这是旧版基线;候选 R6 的真实生产传输(woff2/fonts.css/3D)须在获得部署授权、实际部署后验证,本批未部署
- **change_scope**:
  - `site/scripts/verify_browser_firefox.py`:新增(262 行,含选择器修正)
  - `site/scripts/verify_browser_webkit.py`:新增(口径声明+13 断言)
  - `INTEGRATION-PLAN.md`:状态行、§7 批次表新增 3b 行、§8 Safari/Firefox 与 Caddy 口径两处风险行
  - `AGENTS.md`:第七轮段补兼容验收+基线完成
  - `logs/`:r6-b3-firefox.log(两轮)、r6-b3-webkit.log、r6-b3-caddy-baseline.log
  - 本机:`playwright install webkit` 装运行时;清理 8981/8982 后台服务与 C:\tmp\r6-revert-check
  - 外部操作:https://nanmu.xyz 只读 curl(已授权范围);其余无

- **verification**:

  | 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
  |--------------|----------------|--------------|
  | site/ | `python -I scripts/verify_browser_firefox.py` | 首轮 13/14(选择器笔误)→ 修正轮 **14/14**(logs/r6-b3-firefox.log) |
  | site/ | `python -I scripts/verify_browser_webkit.py` | **13/13**(logs/r6-b3-webkit.log;Playwright WebKit 非真机 Safari) |
  | 本机 curl | GET/HEAD × --compressed/未压缩 × 直连/代理 | 旧版基线归档(logs/r6-b3-caddy-baseline.log) |
  | 仓库根 | `python scripts/check_docs.py` | 提交前跑,见 Git 实况 |

- **pending_runtime**: C:/tmp/b3-lh 报告目录与 b3-* 测量脚本留本地不入库(口径已在第一部分 session 记录)
- **decisions_needed**: 批次 3 至此测量/兼容/基线全部完成或登记;合并 main/推送/部署/真机补测待用户裁决
- **disposition**: complete(批次 3 指令范围内的本机可执行项全部完成;真机与 R6 生产传输验证按指令登记待验)
- **next_action**: 1) 本轮提交落盘(见 Git 实况);2) 交审计;3) 后续(均需用户明确授权):真机补测、R6 部署后 Caddy 复测、合并/推送。本文档不自动授予任何提交外权限
- **omissions**:
  - Safari 真机、移动端真机触摸/帧率:无设备,登记待验(不以 Playwright WebKit 结果代替)
  - Firefox/WebKit 的 Lighthouse 级性能数字未测(用户指令的性能测量对象是 Lighthouse+Chromium 口径,已完成;浏览器兼容与性能测量两个维度不混)
  - hadRecentInput=True 的纯浏览器(非 CDP)场景未知,沿第一部分 omission 口径
