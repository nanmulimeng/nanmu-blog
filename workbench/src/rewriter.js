/* ── 预览产物改写器(DESIGN §4.3,任务 2.2)──
   根路径资源引用 → /preview/<op-id>/ 前缀;css/font/img 注入资源 token(?t=);
   站内/外部 <a> 去 href 留 data-wb-target(校对可查目标),页内锚点保留;
   /api/ 永不被指进预览命名空间;script src 前缀改写但不注 token
   (token 类别=css/font/img;CSP sandbox 无 allow-scripts,脚本零执行)。
   相对路径与 data: 不改写(相对解析以预览内文件位置为准)。
   构建产物为 Astro 小写属性输出,不做大写属性兼容。 */

const TOKEN_KINDS = new Set([
  'css', 'woff', 'woff2', 'ttf', 'otf', 'eot',
  'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'avif', 'ico',
]);

function kindOf(u) {
  const m = /\.([a-z0-9]+)$/i.exec(u.split(/[?#]/)[0]);
  return m ? m[1].toLowerCase() : '';
}

function withToken(u, token) {
  return u.includes('?') ? `${u}&t=${token}` : `${u}?t=${token}`;
}

/** 单个资源 URL 变换:根路径→前缀;css/font/img 附 token;其余原样。 */
function transformUrl(u, { prefix, token }) {
  if (!u.startsWith('/') || u.startsWith('//') || u.startsWith('/api/')) return u;
  const abs = prefix + u;
  return TOKEN_KINDS.has(kindOf(u)) ? withToken(abs, token) : abs;
}

function transformSrcset(v, opts) {
  return v.split(',').map((part) => {
    const seg = part.trim().split(/\s+/);
    if (!seg[0]) return part.trim();
    return [transformUrl(seg[0], opts), ...seg.slice(1)].join(' ');
  }).join(', ');
}

export function rewriteHtml(html, opts) {
  /* 1) <a>:非锚点一律去 href → data-wb-target(导航收敛,§4.3 定案) */
  let out = html.replace(
    /(<a\b[^>]*?)\shref=(["'])(.*?)\2([^>]*)>/g,
    (m, pre, q, href, post) => (href.startsWith('#') ? m : `${pre} data-wb-target=${q}${href}${q}${post}>`),
  );
  /* 2) 资源属性:href(锚点已保留,此处只剩 link 等资源)/src/srcset/poster */
  out = out.replace(
    /\s(src|href|srcset|poster)\s*=\s*("([^"]*)"|'([^']*)')/g,
    (m, attr, _raw, dq, sq) => {
      const q = dq !== undefined ? '"' : "'";
      const v = dq !== undefined ? dq : sq;
      const nv = attr === 'srcset' ? transformSrcset(v, opts) : transformUrl(v, opts);
      return nv === v ? m : ` ${attr}=${q}${nv}${q}`;
    },
  );
  return out;
}

export function rewriteCss(css, opts) {
  return css.replace(
    /url\(\s*(['"]?)([^'")]+)\1\s*\)/g,
    (m, q, u) => {
      const nv = transformUrl(u, opts);
      return nv === u ? m : `url(${q}${nv}${q})`;
    },
  );
}
