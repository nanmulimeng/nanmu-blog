# 2026-10-09 R6 批次 0–1 审计收口:预算口径勘误 + 测量工具修正 + fonts.css 无损优化

> HEAD(本文写入时):1f25d9a;分支 codex/r6-interaction(仅本地,未推送/未合并/未部署)。

## objective

执行用户 2026-10-09 审计裁决的三项定点收口(不重做设计、不减字重、不改正文):

1. **纠正预算口径**:500KB 线自方案起即「HTML+CSS+JS,首访字体分片另列 ≤1.2MB」;撤回批次 0–1 交付中「约 920KB 超线」「与 CJK webfont 物理现实矛盾」的错误结论,在新交接记录勘误,历史记录不伪装未发生。
2. **无损优化 fonts.css**:生成器实现「各字重对应分片交错排列」,声明内容/每族每字重内部顺序/字体文件不变;固定压缩参数验证;不新增依赖。
3. **修正测量工具**:区分冷缓存分类体积、跨页唯一资源增量、真实暖缓存网络传输;失败响应单列;字体装载检查用中文样本与实际字重;浏览器路径可配置。

## state

- 勘误背景(用户审计复核确认):早前交付报告把 woff2 并入 HTML+CSS+JS 后折算 920KB 与 500KB 线比较——比较口径错误;`no-store + seen 去重`只能证明「页面引入了哪些新 URL」,不能证明缓存命中;`document.fonts.check()` 未传中文样本,只验证到不相关字形。错误结论与错误证据链保留在 [批次 0–1 session](2026-10-09-r6-batch01-integration.md) 与其 INTEGRATION-PLAN 历史版本,不删改。
- **2c52c34 测量工具修正**:
  - `measure_budget.py`:A 冷缓存仅计 2xx、失败单列;B 更名「跨页唯一资源增量」并注明非缓存证据;新增 C 真实暖缓存(可缓存服务 max-age=3600 + CDP Network 的 encodedDataLength,「零传输且 2xx」=命中——实测该 Chromium build 对缓存命中不置 fromDiskCache/fromMemoryCache 标志,document 例外);D 固定 gzip level 6/mtime=0(Python zlib,注明工具;早前 92707 B 系默认 level 9,与审计 Node level 6 的 94379 B 差异即工具/等级不同)。
  - `verify_browser.py`:字体断言加严为中文样本「你好,世界——纸与印。」逐字重(400/600/900)load+check 实测,补 NM Plex Mono 改名实测(此前从未断言);两脚本浏览器路径三级探测(NM_VERIFY_CHROME 显式 > ms-playwright 已装扫描取最大 build > Playwright 默认),不再绑定固定用户目录/build 号。
- **1f25d9a fonts.css 交错排列**:`build-site-fonts.py` serif 段从字重大组改为「分片号主序 × 字重内序(400/600/900)」;write_bytes 显式 LF(此前 Windows 文本模式写 CRLF,磁盘 304490 B 与 git/生产 LF 304185 B 口径不一);rename_plex 钉死 head.modified(`TTFont(recalcTimestamp=False)`——此前每次重跑 plex 两件字节漂移,「重跑幂等」承诺失实,本次一并修复)。TDD:交错断言先对旧 CSS FAIL(RED)再实现转 GREEN。[verified: 等价断言 305 条多重集合一致+每族每字重内部顺序一致;303 分片 sha256 前后全等;连续重跑两次 plex 输出字节一致]
- 视觉一致性:文章页 + about × 昼/夜 4 组整页截图(交错前后)逐像素零差异(PIL ImageChops)。[verified: 差异像素 0, bbox=None]
- 验收:`npm run verify` 绿;`verify_browser.py` **34/34 PASS**(含 `fontck={w400:True,w600:True,w900:True,mono:True}` 昼夜两态)。
- 实测(修正版工具 + 交错后,本地无压缩服务,单位 B/KiB=1024):
  - 冷缓存文章页(仅 2xx 原始字节):HTML 3954 + CSS 321303(含 fonts.css 304185)+ JS 7344 = **332601 B(324.8 KiB)≤ 500KB ✓**;woff2 另列 819232 B(800.2 KiB)
  - fonts.css:原始 304185 B,**gzip-6 34013 B(33.2 KiB)≤ 60KB ✓**(交错前 92969 B,-63%;审计 Node level 6 探针 94379→34350 B 为复现线索,不同工具数字不混比)
  - 字体首访四页累计:819232+42520+89784+74440 = **1025976 B(1002.0 KiB)≤ 1.2MB** ✓(贴线)
  - 真实暖缓存(CDP):重访文章页 26/26 零传输命中、网络 0 B;暖访三页仅传新增资源(45608/92991/84592 B,含响应头)——跨页复用取得网络层证据
  - 冷访有 favicon.ico 404(浏览器自动请求,站点无该文件;失败响应单列功能由此捕获;观察项,未处理)
- 文档:INTEGRATION-PLAN 状态行/§2/§5(口径+勘误段+新实测)/§7/§8 已更新;AGENTS.md 入口改第四轮。

## disposition

continuable(三项收口完成;批次 2 首页 3D 未开始)。

## next_action

1. **批次 2(首页 3D)**:home.css + public/3d(three r180 本地自托管 + poster 两张)+ W5-W8(§4 页签联动/§4b 封面挂名、来源正则改 `/posts/<id>/`/§5 装订线/§6 三层展开)+ 封面卡;验收=同矩阵 + WebGL 降级零请求零报错 + 预算实测(poster ≤450KB 先于 3D 字节、3D gzip ≤220KB idle import)。
2. 批次 3:Lighthouse 移动档、真机/Firefox/Safari、生产 Caddy 实压缩口径复核。

## omissions

- 浏览器验收与测量仍仅 Chromium(1248);Firefox/Safari/真机未测(批次 3)。
- C 段暖缓存的「零传输命中」口径依赖该 Chromium build 行为(不置 from*Cache 标志);换浏览器/版本需复核判定逻辑。
- 生产 Caddy 实压缩与协商缓存(ETag/304)未实测;本地 gzip-6 为固定工具口径,非部署层实测。
- favicon.ico 404:浏览器自动请求所致,属站点现状观察项,超出本轮授权未处理(如需 favicon 属新增资产,另行授权)。
- VT 跨页过渡效果仍为人工判断项(与批次 0–1 相同,未变)。
