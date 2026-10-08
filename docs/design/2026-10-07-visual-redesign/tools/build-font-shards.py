# 字体分片生成:Google Fonts 整包 TTF -> 按其官方 unicode-range 分片子集 -> 本地 woff2 分片 + fonts.css
# 目的:中文子集与内容增长解耦——分片按码位固定覆盖全库,日报/文章新增汉字自动命中既有分片,
#       不需要每次重新生成。生成是构建期一次性动作,产物为静态资产;运行时零依赖。
# 用法(仓库根或任意目录): python -I docs/design/2026-10-07-visual-redesign/tools/build-font-shards.py
# 依赖: fonttools(仅生成时需要,不进 site 运行时白名单)
# 来源与许可证见 prototypes/fonts/FONTS.md
import re, sys, pathlib, urllib.request
from fontTools.subset import Subsetter, Options
from fontTools.ttLib import TTFont

HERE = pathlib.Path(__file__).resolve().parent
PROTO = HERE.parent / "prototypes"
OUT = PROTO / "fonts"
SHARDS = OUT / "shards"
CACHE = HERE / "_font-cache"          # 整包 TTF 缓存,删除后自动重新下载
CACHE.mkdir(exist_ok=True)
SHARDS.mkdir(exist_ok=True)

UA_FULL = "Mozilla/5.0"               # 短 UA:返回整包 TTF
UA_SPLIT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")  # 返回 woff2 分片(取 unicode-range)

def fetch(url, ua):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    return urllib.request.urlopen(req, timeout=120).read()

def parse_unicodes(rg):
    """'U+0020-007E, U+4E00-9FFF' -> [0x20..0x7E, 0x4E00..0x9FFF]"""
    out = []
    for part in rg.split(","):
        part = part.strip().lstrip("U+").lstrip("u+")
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a, 16), int(b, 16) + 1))
        else:
            out.append(int(part, 16))
    return out

def full_ttf(css_url, prefix, weight):
    css = fetch(css_url, UA_FULL).decode("utf-8")
    faces = re.findall(r"font-weight: (\d+);\s*font-display: swap;\s*src: url\((\S+)\)", css)
    url = next(u for wt, u in faces if int(wt) == weight)
    p = CACHE / f"{prefix}-{weight}.ttf"
    if not p.exists():
        print(f"  download {p.name} {len(url)}", file=sys.stderr)
        p.write_bytes(fetch(url, UA_FULL))
    return p

def split_ranges(css_url, weight):
    """取官方 woff2 分片表中该字重的 unicode-range 列表(全库固定覆盖)"""
    css = fetch(css_url, UA_SPLIT).decode("utf-8")
    faces = re.findall(
        r"font-weight: (\d+);.*?src: url\((\S+)\) format\('woff2'\);\s*unicode-range: ([^;]+);",
        css, re.S)
    ranges = [r for wt, _, r in faces if int(wt) == weight]
    print(f"  {len(ranges)} official ranges", file=sys.stderr)
    return ranges

SERIF_CSS = "https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;900&display=swap"
PLEX_CSS = "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&display=swap"
SANS_CSS = "https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&display=swap"

css_out = []

def shard_family(name, css_url, prefix, weights):
    ranges = None
    for w in weights:
        ttf = full_ttf(css_url, prefix, w)
        if ranges is None:
            ranges = split_ranges(css_url, w)
        assert ranges is not None
        for i, rg in enumerate(ranges):
            out = SHARDS / f"{prefix}-{w}-{i:03d}.woff2"
            if out.exists():
                continue
            font = TTFont(str(ttf), lazy=True)
            ss = Subsetter(Options(layout_features="*", name_IDs="*", hinting=True))
            ss.populate(unicodes=parse_unicodes(rg))
            ss.subset(font)
            font.flavor = "woff2"
            font.save(out)
            font.close()
        print(f"  {prefix}-{w}: {len(ranges)} shards", file=sys.stderr)
    assert ranges is not None
    for w in weights:
        for i, rg in enumerate(ranges):
            css_out.append(
                f"@font-face{{font-family:'{name}';font-style:normal;font-weight:{w};"
                f"font-display:swap;src:url('fonts/shards/{prefix}-{w}-{i:03d}.woff2') format('woff2');"
                f"unicode-range:{rg}}}")

def whole_family(name, css_url, prefix, weights):
    """拉丁等宽:整字体直接转 woff2,不分片"""
    for w in weights:
        ttf = full_ttf(css_url, prefix, w)
        out = OUT / f"{prefix}-{w}.woff2"
        font = TTFont(str(ttf), lazy=True)
        font.flavor = "woff2"
        font.save(out)
        font.close()
        css_out.append(
            f"@font-face{{font-family:'{name}';font-style:normal;font-weight:{w};"
            f"font-display:swap;src:url('fonts/{prefix}-{w}.woff2') format('woff2')}}")
        print(f"  {prefix}-{w}: whole {out.stat().st_size//1024}KB", file=sys.stderr)

print("Noto Serif SC shards...", file=sys.stderr)
shard_family("Noto Serif SC", SERIF_CSS, "noto-serif-sc", [400, 600, 900])
print("Noto Sans SC shards...", file=sys.stderr)
shard_family("Noto Sans SC", SANS_CSS, "noto-sans-sc", [400, 500, 700])
print("IBM Plex Mono whole...", file=sys.stderr)
whole_family("IBM Plex Mono", PLEX_CSS, "plex-mono", [400, 500])

(PROTO / "fonts.css").write_text("\n".join(css_out) + "\n", encoding="utf-8")
print(f"fonts.css: {len(css_out)} faces", file=sys.stderr)
