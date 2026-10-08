# 字体资产说明

本目录为视觉原型自托管字体。策略:**固定分片覆盖**——按 Google Fonts 官方 unicode-range 分片表,
把整包 TTF 一次性切成与码位绑定的静态 woff2 分片。文章/日报新增汉字自动命中既有分片,
与内容增长解耦;生成是构建期一次性动作,产物是纯静态资产,运行时零依赖。

## 来源与版本

| 字体 | 字重 | 来源 | 版本基线 | 许可证 |
|------|------|------|----------|--------|
| Noto Serif SC | 400 / 600 / 900 | Google Fonts css2 API(整包 TTF) | 抓取于 2026-10-07,官方分片表 101 段 | SIL OFL 1.1([OFL-noto.txt](OFL-noto.txt)) |
| Noto Sans SC | 400 / 500 / 700 | 同上 | 同上 | SIL OFL 1.1([OFL-noto.txt](OFL-noto.txt)) |
| IBM Plex Mono | 400 / 500 | 同上(整字体转 woff2,不分片) | 抓取于 2026-10-07 | SIL OFL 1.1([OFL-ibm-plex.txt](OFL-ibm-plex.txt)) |

两份许可证文本随字体一并分发,满足 OFL 再分发条款。OFL 允许子集化与 woff2 转换
(属 "Modified Version")。RFN(Reserved Font Name)情况:Plex 的许可证声明了
Reserved Font Name "Plex",严格合规要求子集化产物改写 name 表另起名字;Noto 随附的
LICENSE 文本未声明 RFN(但 "Noto" 是 Google 商标,对外宣传时仍需注意)。
当前为设计原型阶段,字体名未改;若进入生产自托管,需在生成脚本中改写 Plex 子集的字体名。

## 目录

- `shards/` — 606 个分片(101 段 × 6 个中文字重),仓库体积约 18MB;**磁盘体积 ≠ 传输体积**:
  浏览器只下载页面实际用到的码位分片。实测首页首载 28 个文件约 1MB,同站后续页面命中缓存。
- `plex-mono-400/500.woff2` — 拉丁等宽整字体,各约 36KB。
- `../fonts.css` — 由生成脚本输出,608 条 @font-face,带 unicode-range。

## 重新生成

```bash
pip install fonttools brotli   # 仅生成时需要,不进 site 运行时白名单
python -I docs/design/2026-10-07-visual-redesign/tools/build-font-shards.py
```

脚本:`tools/build-font-shards.py`(已入库,可复现)。整包 TTF 缓存在 `tools/_font-cache/`(已 gitignore),
删除后自动重新下载;分片已存在则跳过,删 shards/ 可全量重建。

## 与自动发布流的关系

分片是提交进仓库的静态文件,构建/发布流程不需要任何字体步骤;Astro 构建只做文件拷贝。
日报每日自动发布新增汉字时,浏览器按 unicode-range 自动拉取对应分片,无需重新生成字体。
