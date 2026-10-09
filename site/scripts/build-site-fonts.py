# -*- coding: utf-8 -*-
"""从设计目录原型字体资产生成生产字体包(site/public/fonts/)。

来源与版本见 docs/design/2026-10-07-visual-redesign/prototypes/fonts/FONTS.md。
本脚本做的三件事(幂等,重跑覆盖):
  1. 仅复制 Noto Serif SC 三字重(400/600/900)分片——R6 版式只用
     serif/mono/kai(tokens.css),Noto Sans 三字重不入生产;
  2. IBM Plex Mono 两文件用 fontTools 改写 name 表为「NM Plex Mono」
     (OFL RFN 义务:修改版不得保留保留名),输出 nm-plex-mono-*.woff2;
  3. 生成 fonts.css:仅 serif 与改名 Plex 的 @font-face(带 unicode-range),
     作为 public 静态文件由 <link> 引入,不走 Astro 打包(分片相对 url
     由浏览器按 unicode-range 按需取)。serif 段按「分片号 × 字重」
     交错排列以利于 gzip 复用重复 unicode-range(声明内容与字重内
     部顺序零改动);行尾固定 LF。
用法:python -I site/scripts/build-site-fonts.py   (依赖 fontTools+brotli)
"""
import re
import shutil
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "docs/design/2026-10-07-visual-redesign/prototypes/fonts"
DST = REPO / "site/public/fonts"

SERIF_WEIGHTS = ("400", "600", "900")
PLEX_NEW_FAMILY = "NM Plex Mono"


def rename_plex(src: Path, weight: str) -> None:
    """改写 name 表另起字体名(OFL RFN),typographic + legacy 两套都写。

    head.modified 钉死为源文件值:TTFont 默认 recalcTimestamp=True 会在
    编译时把 head.modified 写成当前时间,导致每次重跑输出字节漂移(其余
    表均确定)——关掉后重跑字节级幂等。
    """
    font = TTFont(str(src), recalcTimestamp=False)
    sub = "Regular" if weight == "400" else "Medium"
    legacy_family = PLEX_NEW_FAMILY if weight == "400" else f"{PLEX_NEW_FAMILY} {sub}"
    ps = f"{PLEX_NEW_FAMILY.replace(' ', '')}-{sub}"
    table = font["name"]
    for nid, val in ((1, legacy_family), (2, "Regular"), (3, f"{ps};OFL-renamed"),
                     (4, f"{PLEX_NEW_FAMILY} {sub}"), (6, ps),
                     (16, PLEX_NEW_FAMILY), (17, sub)):
        table.setName(val, nid, 3, 1, 0x409)  # windows/en-US
    out = DST / f"nm-plex-mono-{weight}.woff2"
    font.save(str(out))
    font.close()


def main() -> int:
    src_css = (SRC / ".." / "fonts.css").resolve().read_text(encoding="utf-8")
    faces = re.findall(r"@font-face\{[^}]*\}", src_css)
    shards_src = SRC / "shards"
    shards_dst = DST / "shards"
    shards_dst.mkdir(parents=True, exist_ok=True)

    kept = 0
    serif_buckets = {w: [] for w in SERIF_WEIGHTS}  # 各字重保持原型顺序
    plex_faces = []
    # 原型 fonts.css 位于 prototypes/ 根,url 前缀为 fonts/…;生产
    # fonts.css 与分片同在 public/fonts/ 下,url 前缀需剥掉 fonts/
    for face in faces:
        if "'Noto Serif SC'" in face:
            m = re.search(r"noto-serif-sc-(\d{3})-\d+\.woff2", face)
            if not m or m.group(1) not in SERIF_WEIGHTS:
                continue
            shutil.copy2(shards_src / m.group(0), shards_dst / m.group(0))
            serif_buckets[m.group(1)].append(
                face.replace("url('fonts/", "url('"))
            kept += 1
        elif "'IBM Plex Mono'" in face:
            m = re.search(r"plex-mono-(\d{3})\.woff2", face)
            weight = m.group(1)
            rename_plex(SRC / m.group(0), weight)
            new_face = face.replace("'IBM Plex Mono'", f"'{PLEX_NEW_FAMILY}'") \
                           .replace(m.group(0), f"nm-plex-mono-{weight}.woff2") \
                           .replace("url('fonts/", "url('")
            plex_faces.append(new_face)

    # serif 交错排列:原型按字重分大组(400×101→600×101→900×101),同一
    # 分片的 unicode-range 在三组里重复却相隔 ~100KB,gzip 窗口用不上。
    # 改为分片号主序 × 字重内序(400/600/900)——同片声明相邻,重复
    # unicode-range 贴近可被 deflate 复用(实测 gzip-6 约缩小 2/3)。
    # 声明内容与每个字重内部顺序零改动,woff2 文件不动。
    def shard_no(face):
        return int(re.search(r"noto-serif-sc-\d{3}-(\d+)\.woff2", face).group(1))

    orders = [[shard_no(f) for f in serif_buckets[w]] for w in SERIF_WEIGHTS]
    if not (orders[0] == orders[1] == orders[2]):
        print("shard order mismatch across weights", file=sys.stderr)
        return 1
    out_css = [serif_buckets[w][i]
               for i in range(len(orders[0]))
               for w in SERIF_WEIGHTS] + plex_faces

    for lic in ("OFL-noto.txt", "OFL-ibm-plex.txt"):
        shutil.copy2(SRC / lic, DST / lic)
    # write_bytes + 显式 \n:避免 Windows 文本模式把行尾写成 CRLF,
    # 保证磁盘、git 入库与生产部署三处字节一致
    (DST / "fonts.css").write_bytes(
        ("\n".join(out_css) + "\n").encode("utf-8"))

    n_shards = len(list(shards_dst.glob("*.woff2")))
    print(f"serif faces: {kept} | shards copied: {n_shards} | plex: 2 | "
          f"fonts.css: {len(out_css)} faces, "
          f"{(DST / 'fonts.css').stat().st_size} bytes")
    if kept != 303 or n_shards != 303 or len(out_css) != 305:
        print("UNEXPECTED counts (expect 303 serif + 2 plex)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
