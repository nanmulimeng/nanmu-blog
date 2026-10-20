/* ═══════════════════════════════════════════════════════════
   R6 首页场景「字场 · 换页碑」· scene6.js(生产版,源资产)
   概念深化(R5「碑页」→ R6):一叠三张内容页立在虚空——
   文章页(真实首段排印)/ 日报页(空态稿纸)/ 站点页(三层简图);
   页签选择 → 对应页弧出换到前景,3D 参与内容组织。
   夜览:背光透纸,纸暖字沉。
   接口:createScene(host, opts) → Promise<{setTheme, resetView, replay,
     setAmbient, isAmbientOn, start, stop, texReady, select, current, stats,
     projectBindingBottom}>
   生产适配(批次 2):文章页内容参数化——opts.article 由 boot6 从
   #scene3d data-article(构建期生成)解析传入,场景侧零内容副本
   (内容同源契约);null = 无公开文章,文章页排空态。
   依赖:同目录 three.module.min.js(r180,本地固定)
   ═══════════════════════════════════════════════════════════ */
import * as THREE from './three.module.min.js';

/* ── 参数表(可编辑源;改这里即可重建/调整场景) ── */
export const PARAMS = {
  cam: {fov: 34, r: 16.4, az: 0.30, el: 0.17, azSpan: 0.18, elMin: 0.10, elMax: 0.38, ty: 3.55,
        txM: 1.55, zoomMax: 2.1},   /* txM:竖屏 lookAt 目标右移,保住右缘与装订线同框 */
  page: {w: 5.2, h: 7.4, curve: 0.14, x: 2.1, y: 0, z: 0, ry: -0.16},
  /* 槽位:0=前景中央;1/2=后左错层。换页=页面在槽位间迁移 */
  slots: [
    {dx: 0,     dy: 0,     dz: 0,     ry: 0,     tone: 1.00},
    {dx: -1.25, dy: -0.28, dz: -1.15, ry: -0.05, tone: 0.93},
    {dx: -2.3,  dy: -0.52, dz: -2.3,  ry: 0.05,  tone: 0.86},
  ],
  binding: {x: 0.075, holes: 4},            /* 订眼位置(页宽比例,左缘内) */
  ghost: {w: 2.0, h: 2.85, x: 5.1, y: 1.6, z: -0.7, ry: -0.5},
  entrance: 2.8, sweepAt: 1.0,
  swapDur: 0.95,                            /* 换页时长(s) */
};
export const LIGHT = {
  day:   {sky: 0xF0EDE5, fogD: 0.012, hemiS: 0xE9E5D9, hemiG: 0x8F8A7B, hemiI: 0.9,
          sunC: 0xFFEFD4, sunI: 2.5, sunPos: [-6, 13, 9], rimI: 0.0, backI: 0.0, fillI: 0.3,
          pageEmI: 0.04, shadowI: 0.18},
  night: {sky: 0x090C12, fogD: 0.016, hemiS: 0x18202F, hemiG: 0x04060A, hemiI: 0.34,
          sunC: 0x8FA8D8, sunI: 0.18, sunPos: [7, 10, -8], rimI: 2.3, backI: 1.6, fillI: 0.15,
          pageEmI: 0.55, shadowI: 0.5},
};

function rng(seed){ let s = seed >>> 0; return () => (s = s * 1664525 + 1013904223 >>> 0) / 4294967296; }

/* ── 页面纹理(1024×1460),字体就绪后绘制;三页共用纸底 ──
   注意:fonts.load 必须带上实际要排印的汉字样本——默认文本是空格,
   空格不需字形,load 会立即 resolve,纹理将用系统回退字体排印 */
/* 固定文案全集:三页纹理(articleTex/digestTex/aboutTex)、pageHead
   与 wrapLines 兜底('无题'/'…')的全部字面量字符。由
   site/scripts/check_scene_sample.mjs 从函数体提取对账生成——
   fonts.load 样本缺字不会报错,只会让该字静默回退系统字体,
   故改任何排印文案后必须跑该脚本同步本串 */
const FIXED_SAMPLE =
  '#(),.0123456789:ABCEFIMNSUabcdefgilmnoprstuxyz·…。' +
  '一不与个人会体全共写出分划到加博印发同后在型字审客尚工已布开引往成手报擎文新无日时明是暂最期未本机条栏检模正每注添渐现生由目站章第篇索约线见计评达过这进通里题';
async function fontsReady(article, digest, site){
  /* 样本 = 动态文本(文章四要素 + 日报最新期 + 三层名/状态)
     + 固定文案,覆盖三张纹理实际排印的全部字符 */
  const dyn = article
    ? (String(article.title || '') + String(article.date || '') +
       String(article.tags || '') + String(article.excerpt || '') +
       '第' + article.no + '篇全文约' + article.words + '字')
    : '暂无文章第一篇正在写。';
  const dynDig = digest && digest.latest
    ? (String(digest.latest.date) + String(digest.latest.count) +
       '最新一期已发布引擎每日发出后注明生成往期与正文见栏目在线每')
    : '';
  const dynSite = site && site.length
    ? site.map(x => String(x.name || '') + String(x.state || '')).join('')
    : '';
  const SAMPLE = dyn + dynDig + dynSite + FIXED_SAMPLE;
  try { await Promise.all([
    document.fonts.load('900 88px "Noto Serif SC"', SAMPLE),
    document.fonts.load('400 35px "Noto Serif SC"', SAMPLE),
    document.fonts.load('600 26px "Noto Serif SC"', SAMPLE),
    document.fonts.load('700 44px "Noto Serif SC"', SAMPLE),
    document.fonts.load('400 27px "Noto Serif SC"', SAMPLE),
    document.fonts.load('400 24px "Noto Serif SC"', SAMPLE),
    document.fonts.load('400 28px "Noto Serif SC"', SAMPLE),
    document.fonts.load('600 40px "Noto Serif SC"', SAMPLE),
  ]); } catch(e){ /* 字体缺失回退系统衬线,仍可读 */ }
}
const TW = 1024, TH = 1460, TM = 152;   /* 文字左边距:装订线在 0.075W≈77px */
function paperBase(seed){
  const c = document.createElement('canvas'); c.width = TW; c.height = TH;
  const g = c.getContext('2d'), r = rng(seed);
  g.fillStyle = '#F7F4EB'; g.fillRect(0, 0, TW, TH);
  for (let i = 0; i < 11000; i++){ g.fillStyle = `rgba(96,88,64,${r() * 0.05})`; g.fillRect(r() * TW, r() * TH, 1 + r() * 1.6, 1); }
  for (let i = 0; i < 130; i++){
    g.strokeStyle = `rgba(130,118,90,${0.02 + r() * 0.03})`; g.lineWidth = 0.8;
    const x = r() * TW, y = r() * TH;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + (r() - .5) * 46, y + (r() - .5) * 7); g.stroke();
  }
  return [c, g];
}
function paperFinish(g){
  /* 弓面明暗:页面两边向 +z 弯出,横向明带让曲面可读。
     夜间透光以 emissiveMap 为主,纸面层次全部来自这张纹理;
     装订线侧(左)亮、向右渐暗,模拟背光自左后透出 */
  const bow = g.createLinearGradient(0, 0, TW, 0);
  bow.addColorStop(0, 'rgba(58,48,34,0.20)'); bow.addColorStop(0.10, 'rgba(255,246,226,0.13)');
  bow.addColorStop(0.22, 'rgba(58,48,34,0.05)'); bow.addColorStop(0.42, 'rgba(255,252,244,0.10)');
  bow.addColorStop(0.62, 'rgba(255,252,244,0.03)'); bow.addColorStop(0.85, 'rgba(58,48,34,0.14)');
  bow.addColorStop(1, 'rgba(58,48,34,0.26)');
  g.fillStyle = bow; g.fillRect(0, 0, TW, TH);
  const wash = g.createLinearGradient(0, 0, TW, 0);
  wash.addColorStop(0, 'rgba(255,244,218,0.16)'); wash.addColorStop(0.45, 'rgba(255,244,218,0.05)');
  wash.addColorStop(1, 'rgba(46,36,24,0.20)');
  g.fillStyle = wash; g.fillRect(0, 0, TW, TH);
  /* 页缘切面:右缘受光边 + 左缘装订侧厚度 */
  const eg = g.createLinearGradient(TW - 34, 0, TW, 0);
  eg.addColorStop(0, 'rgba(90,80,60,0)'); eg.addColorStop(1, 'rgba(90,80,60,0.42)');
  g.fillStyle = eg; g.fillRect(TW - 34, 0, 34, TH);
  const lg = g.createLinearGradient(0, 0, 26, 0);
  lg.addColorStop(0, 'rgba(70,60,44,0.34)'); lg.addColorStop(1, 'rgba(70,60,44,0)');
  g.fillStyle = lg; g.fillRect(0, 0, 26, TH);
  /* 订眼:孔内径向渐变 + 纸壁亮边,做出穿透纸面的厚度 */
  const holeX = TW * PARAMS.binding.x;
  for (let i = 0; i < PARAMS.binding.holes; i++){
    const hy = TH * (0.18 + i * 0.213);
    const hg = g.createRadialGradient(holeX - 3, hy - 3, 2, holeX, hy, 13);
    hg.addColorStop(0, 'rgba(8,7,5,0.62)'); hg.addColorStop(0.62, 'rgba(20,18,14,0.48)');
    hg.addColorStop(1, 'rgba(20,18,14,0)');
    g.fillStyle = hg;
    g.beginPath(); g.arc(holeX, hy, 13, 0, Math.PI * 2); g.fill();
    g.strokeStyle = 'rgba(247,244,235,0.9)'; g.lineWidth = 2.5;
    g.beginPath(); g.arc(holeX, hy, 14.5, -0.5, 1.8); g.stroke();
    g.strokeStyle = 'rgba(70,60,44,0.5)'; g.lineWidth = 2;
    g.beginPath(); g.arc(holeX, hy, 16, 2.2, 4.6); g.stroke();
  }
  const t = new THREE.CanvasTexture(g.canvas);
  t.anisotropy = 8;
  return t;
}
/* 页头:朱砂印 + 栏目名(三页统一) */
function pageHead(g, sealCh, label){
  g.fillStyle = '#C2402A'; g.fillRect(TM, 76, 40, 40);
  g.fillStyle = '#F7F4EB'; g.font = '900 28px "Noto Serif SC", serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(sealCh, TM + 20, 98);
  g.textAlign = 'left';
  g.fillStyle = 'rgba(29,31,36,0.55)'; g.font = '600 26px "Noto Serif SC", serif';
  g.fillText(label, TM + 58, 98);
}
/* 通用逐字换行:超 maxLines 行截「…」(长标题的有界终态);
   按 code point 迭代,组合字符/emoji 计一个度量单元 */
function wrapLines(g, text, maxW, maxLines){
  const src = String(text || '').trim() || '无题';
  const lines = []; let cur = '';
  for (const ch of src){
    if (cur && g.measureText(cur + ch).width > maxW){
      lines.push(cur); cur = ch;
      if (lines.length >= maxLines) break;
    } else cur += ch;
  }
  if (cur && lines.length < maxLines) lines.push(cur);
  if (lines.join('').length < src.length && lines.length){
    const i = lines.length - 1;
    lines[i] = (lines[i].length > 1 ? lines[i].slice(0, -1) : lines[i]) + '…';
  }
  return lines;
}
/* 文章页:内容同源——标题/日期/标签/摘要/落款全部来自 opts.article
   (构建期 #scene3d data-article),场景侧零内容副本。
   null = 无公开文章:排「暂无文章」空态;空摘要:跳过正文段,
   稿纸虚线行补白(装饰语言,与日报页一致,非内容) */
function articleTex(art){
  const [, g] = paperBase(97);
  pageHead(g, '文', 'NANMU · 手写文章');
  const maxW = TW - TM - 72;
  g.fillStyle = '#14161A'; g.font = '900 88px "Noto Serif SC", serif';
  const lines = wrapLines(g, art ? art.title : '暂无文章', maxW, 3);
  let y = 226;
  for (const ln of lines){ g.fillText(ln, TM, y); y += 104; }
  y -= 104;
  /* 日期/标签行:字段缺省(如 poster 资产的中性数据)时整行跳过,
     不拼出悬空分隔符 */
  g.fillStyle = 'rgba(29,31,36,0.5)'; g.font = '400 27px "Noto Serif SC", serif';
  const meta = art ? [art.date, art.tags].filter(Boolean).join(' · ')
                   : '第一篇正在写。';
  if (meta) g.fillText(meta, TM, y + 70);
  g.strokeStyle = 'rgba(29,31,36,0.4)'; g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(TM, y + 110); g.lineTo(TW - 84, y + 110); g.stroke();
  /* 正文:摘要逐字排印,行数以落款上方为界(异常超长在此截断,
     页面侧摘要有 90 字截断,正常不会触界) */
  g.font = '400 35px "Noto Serif SC", serif'; g.fillStyle = '#22242A';
  const lineH = 62; let x = TM, yy = y + 180;
  const body = art && art.excerpt ? String(art.excerpt) : '';
  const maxLines = Math.max(1, Math.floor((TH - 210 - yy) / lineH));
  let wrote = 1;
  for (const ch of body){
    const w = g.measureText(ch).width;
    if (x + w > TM + maxW){
      if (wrote >= maxLines) break;
      wrote++; x = TM; yy += lineH;
    }
    g.fillText(ch, x, yy); x += w;
  }
  /* 虚线补白行:正文结束后延续稿纸语言到落款上方 */
  g.strokeStyle = 'rgba(29,31,36,0.22)'; g.lineWidth = 2; g.setLineDash([10, 9]);
  let dy = yy + (x > TM + 20 ? lineH + 16 : 26);
  while (dy < TH - 160){ g.beginPath(); g.moveTo(TM, dy); g.lineTo(TW - 84, dy); g.stroke(); dy += 88; }
  g.setLineDash([]);
  g.fillStyle = 'rgba(29,31,36,0.45)'; g.font = '400 24px "Noto Serif SC", serif';
  g.fillText(art && art.no != null
    ? ('第 ' + art.no + ' 篇 · 全文约 ' + art.words + ' 字 · nanmu.xyz')
    : '文章 · nanmu.xyz', TM, TH - 92);
  return paperFinish(g);
}
/* 日报页:稿纸——栏目抬头 + 虚线行 + 状态(内容同源:dig 最新期来自
   data-digest,零期排空态,不虚构内容) */
function digestTex(dig){
  const live = !!(dig && dig.latest);
  /* intro:资产生产(poster 拍摄)用的栏目级介绍态——排稳定栏目
     说明,不排期数状态,静态图不随「暂无/已有」过期;运行时
     (boot6)不会传 intro */
  const intro = !!(dig && dig.intro);
  const [, g] = paperBase(41);
  pageHead(g, '机', 'NANMU · AI 日报');
  g.fillStyle = '#14161A'; g.font = '900 88px "Noto Serif SC", serif';
  g.fillText('AI 日报', TM, 240);
  g.fillStyle = 'rgba(29,31,36,0.5)'; g.font = '400 27px "Noto Serif SC", serif';
  g.fillText(live
    ? (dig.latest.date + ' 已发布 · 共 ' + dig.latest.count + ' 条 · AI 生成')
    : '计划每日一期 · 发出后注明 AI 生成', TM, 330);
  g.strokeStyle = 'rgba(29,31,36,0.4)'; g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(TM, 376); g.lineTo(TW - 84, 376); g.stroke();
  /* 虚线行:待填的稿纸 */
  g.strokeStyle = 'rgba(29,31,36,0.28)'; g.lineWidth = 2; g.setLineDash([10, 9]);
  for (let i = 0; i < 4; i++){
    const yy = 470 + i * 88;
    g.beginPath(); g.moveTo(TM, yy); g.lineTo(TW - 84 - (i === 3 ? 260 : 0), yy); g.stroke();
  }
  g.setLineDash([]);
  /* 状态说明:与页面层列表同源 */
  if (live){
    g.fillStyle = 'rgba(29,31,36,0.72)'; g.font = '600 40px "Noto Serif SC", serif';
    g.fillText('最新一期:' + dig.latest.date, TM, 920);
    g.fillStyle = 'rgba(29,31,36,0.5)'; g.font = '400 28px "Noto Serif SC", serif';
    g.fillText('日报由 AI 生成,每期注明模型与成本。', TM, 986);
    g.fillText('往期与正文见日报栏目。', TM, 1040);
  } else if (intro){
    g.fillStyle = 'rgba(29,31,36,0.72)'; g.font = '600 40px "Noto Serif SC", serif';
    g.fillText('每期日报发布后出现在这里', TM, 920);
    g.fillStyle = 'rgba(29,31,36,0.5)'; g.font = '400 28px "Noto Serif SC", serif';
    g.fillText('日报由 AI 生成,每期注明模型与成本。', TM, 986);
    g.fillText('与手写文章分开,栏目印章不同。', TM, 1040);
  } else {
    g.fillStyle = 'rgba(29,31,36,0.72)'; g.font = '600 40px "Noto Serif SC", serif';
    g.fillText('暂无已发布日报', TM, 920);
    g.fillStyle = 'rgba(29,31,36,0.5)'; g.font = '400 28px "Noto Serif SC", serif';
    g.fillText('日报由 AI 生成,每期注明模型与成本。', TM, 986);
    g.fillText('第一期到达时会出现在这个栏目。', TM, 1040);
  }
  g.fillStyle = 'rgba(29,31,36,0.45)'; g.font = '400 24px "Noto Serif SC", serif';
  g.fillText('栏目: digest · nanmu.xyz', TM, TH - 92);
  return paperFinish(g);
}
/* 站点页:三层结构简图——博客本体 / AI 日报 / 个人检索,层间分离表达独立;
   层名与状态来自 data-site(页面层列表同源),缺省退内置默认 */
function aboutTex(layers){
  const L = (layers && layers.length === 3)
    ? layers
    : [{name: '手写文章', state: '在线 · 博客本体', solid: true},
       {name: 'AI 日报',  state: '计划 · 引擎评审通过', solid: false},
       {name: '个人检索', state: '计划 · 尚未开工', solid: false}];
  const [, g] = paperBase(63);
  pageHead(g, '站', 'NANMU · 这个站');
  g.fillStyle = '#14161A'; g.font = '900 88px "Noto Serif SC", serif';
  g.fillText('这个站', TM, 240);
  g.fillStyle = 'rgba(29,31,36,0.5)'; g.font = '400 27px "Noto Serif SC", serif';
  g.fillText('文章是本体,AI 栏目渐进添加', TM, 330);
  g.strokeStyle = 'rgba(29,31,36,0.4)'; g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(TM, 376); g.lineTo(TW - 84, 376); g.stroke();
  const ys = [470, 680, 890];
  for (let i = 0; i < 3; i++){
    const name = String(L[i].name || ''), state = String(L[i].state || '');
    const solid = !!L[i].solid, y = ys[i];
    /* 纸层:矩形带厚度(下缘暗线),计划层用虚线框 */
    g.fillStyle = solid ? 'rgba(194,64,42,0.07)' : 'rgba(29,31,36,0.03)';
    g.fillRect(TM, y, TW - TM - 84, 120);
    if (solid){ g.strokeStyle = 'rgba(194,64,42,0.65)'; g.setLineDash([]); }
    else { g.strokeStyle = 'rgba(29,31,36,0.4)'; g.setLineDash([9, 8]); }
    g.lineWidth = 2; g.strokeRect(TM, y, TW - TM - 84, 120);
    g.setLineDash([]);
    g.fillStyle = 'rgba(20,18,14,0.16)'; g.fillRect(TM, y + 120, TW - TM - 84, 10);
    g.fillStyle = '#14161A'; g.font = '700 44px "Noto Serif SC", serif';
    g.fillText(name, TM + 34, y + 58);
    g.fillStyle = solid ? '#A83622' : 'rgba(29,31,36,0.55)'; g.font = '400 27px "Noto Serif SC", serif';
    g.fillText(state, TM + 34, y + 100);
  }
  g.fillStyle = 'rgba(29,31,36,0.45)'; g.font = '400 24px "Noto Serif SC", serif';
  g.fillText('nanmu.xyz · 个人博客', TM, TH - 92);
  return paperFinish(g);
}
function plainPaperTex(seed, tone){
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'), r = rng(seed);
  const base = Math.round(235 * tone);
  g.fillStyle = `rgb(${base},${Math.round(base * 0.985)},${Math.round(base * 0.94)})`;
  g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 1800; i++){ g.fillStyle = `rgba(80,74,56,${r() * 0.05})`; g.fillRect(r() * 256, r() * 256, 1.4, 1); }
  return new THREE.CanvasTexture(c);
}
function shadowTex(){
  const c = document.createElement('canvas'); c.width = c.height = 512;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(256, 256, 30, 256, 256, 250);
  grad.addColorStop(0, 'rgba(20,18,14,1)'); grad.addColorStop(0.55, 'rgba(20,18,14,0.5)');
  grad.addColorStop(1, 'rgba(20,18,14,0)');
  g.fillStyle = grad; g.fillRect(0, 0, 512, 512);
  return new THREE.CanvasTexture(c);
}
export function steleGeometry(w, h, curve){
  /* 弓形微弯:页面中心为弦,两边向 +z 弯出 */
  const geo = new THREE.PlaneGeometry(w, h, 48, 1);
  const pos = geo.attributes.position, R = w / curve;
  for (let i = 0; i < pos.count; i++){
    const a = pos.getX(i) / R;
    pos.setX(i, Math.sin(a) * R);
    pos.setZ(i, (1 - Math.cos(a)) * R - (1 - Math.cos(w / 2 / R)) * R * 0.5);
  }
  geo.computeVertexNormals();
  return geo;
}

export async function createScene(host, opts = {}){
  const P = PARAMS;
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  const links = Object.assign({post: '/posts/', digest: '/digest/', about: '/about/'}, opts.links || {});
  const onSelect = typeof opts.onSelect === 'function' ? opts.onSelect : null;
  /* 内容同源:article = {title,date,tags,excerpt,url,no,words} | null、
     digest = {latest:{date,count}} | null、site = [{name,state,solid}] | null,
     均由 boot6 从 #scene3d data-* JSON(构建期生成)解析传入 */
  const article = opts.article || null;
  const digest = opts.digest || null;
  const site = opts.site || null;

  const renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, innerWidth < 760 ? 1.5 : 2));
  renderer.shadowMap.enabled = innerWidth >= 760;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.06;
  renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;touch-action:pan-y;cursor:grab';
  renderer.domElement.setAttribute('aria-label', '三维场景:一叠立着的稿纸,含文章、日报、站点三页;可拖拽环顾,点击后排稿纸换到前景,点击前景稿纸进入对应栏目');
  host.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0xF0EDE5, 0.012);
  const camera = new THREE.PerspectiveCamera(P.cam.fov, 1, 0.1, 120);
  let az = P.cam.az, el = P.cam.el;
  function placeCam(){
    const r = P.cam.r * (camera.userData.zoom || 1);
    camera.position.set(Math.sin(az) * Math.cos(el) * r, Math.sin(el) * r + P.cam.ty, Math.cos(az) * Math.cos(el) * r);
    /* 竖屏:lookAt 目标向页面一侧移,构图居中而非把右缘切出画外 */
    const tx = (camera.userData.txK || 0) * P.cam.txM;
    camera.lookAt(tx, P.cam.ty, 0);
  }
  function resize(){
    /* clientWidth 是四舍五入整数:宿主实宽 374.67 时会读出 375,画布比容器宽 0.33px,
       经典滚动条系统(Windows 桌面窄窗)因此冒出页面级横向滚动条。
       用 getBoundingClientRect 取小数宽并向下取整,保证画布永不超出宿主。 */
    const rect = host.getBoundingClientRect();
    const w = Math.max(1, Math.floor(rect.width)), h = Math.max(1, Math.floor(rect.height));
    renderer.setSize(w, h); camera.aspect = w / h;
    /* 竖屏构图:横向视角不足时按比例拉远 */
    camera.userData.zoom = Math.min(P.cam.zoomMax, Math.max(1, 1.02 / Math.max(camera.aspect, 0.01)));
    /* txK 0(横屏)→1(竖屏)平滑过渡 */
    camera.userData.txK = Math.min(Math.max((1.05 - camera.aspect) / 0.45, 0), 1);
    camera.updateProjectionMatrix();
    placeCam();
    /* 循环停止(暂停/reduced-motion)时,窗口变化也要重绘;初始化期
       (inited=false)跳过——首绘由下方 compile 段后的首次渲染承担,
       避免与启动后的首帧渲染重复做 shader 编译/纹理上传 */
    if (!running && inited) renderOnce();
  }
  addEventListener('resize', resize);

  const M = {
    seal: new THREE.MeshStandardMaterial({color: 0xC2402A, roughness: 0.5, metalness: 0.1}),
    shadow: new THREE.MeshBasicMaterial({map: shadowTex(), transparent: true, depthWrite: false,
      opacity: 0.18, color: 0x14120E}),
  };
  const root = new THREE.Group(); scene.add(root);
  const track = [];
  function reg(o, t0, t1, kind){ o.userData.ent = {t0, t1, kind, from: {}, to: {}}; track.push(o); }

  /* 槽位姿态:槽位 i → 世界位置/朝向 */
  function slotPose(i){
    const s = P.page, sl = P.slots[i];
    return {x: s.x + sl.dx, y: s.h / 2 + s.y + sl.dy, z: s.z + sl.dz, ry: s.ry + sl.ry, tone: sl.tone};
  }
  /* 线装:朱砂线环穿过订眼,沿左缘走线(每页一份,贴在弯曲页面局部坐标) */
  function addBinding(page){
    const s = P.page;
    const holeU = P.binding.x, R2 = s.w / s.curve;
    const lx = (holeU - 0.5) * s.w;
    const a = lx / R2;
    const px = Math.sin(a) * R2, pz = (1 - Math.cos(a)) * R2 - (1 - Math.cos(s.w / 2 / R2)) * R2 * 0.5;
    const grp = new THREE.Group();
    for (let i = 0; i < P.binding.holes; i++){
      const v = 0.18 + i * 0.213;
      const hy = (v - 0.5) * s.h;
      const loop = new THREE.Mesh(new THREE.TorusGeometry(0.085, 0.026, 8, 20), M.seal);
      loop.position.set(px, hy, pz + 0.045);
      grp.add(loop);
      if (i < P.binding.holes - 1){
        const nv = 0.18 + (i + 1) * 0.213;
        const segLen = (nv - v) * s.h - 0.11;
        const seg = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, segLen, 6), M.seal);
        seg.position.set(px, (hy + (nv - 0.5) * s.h) / 2, pz + 0.045);
        grp.add(seg);
      }
    }
    page.add(grp);
    return grp;
  }

  /* 三张内容页:先素纸占位,字体就绪后换正式纹理 */
  const PAGES = [
    {pid: 'posts',  label: '文章',   link: links.post,   tex: () => articleTex(article)},
    {pid: 'digest', label: '日报',   link: links.digest, tex: () => digestTex(digest)},
    {pid: 'about',  label: '这个站', link: links.about,  tex: () => aboutTex(site)},
  ];
  const pages = PAGES.map((def, i) => {
    const mat = new THREE.MeshStandardMaterial({
      map: plainPaperTex(3 + i * 7, P.slots[i].tone), roughness: 0.88, side: THREE.DoubleSide,
      emissive: 0xFFC887, emissiveIntensity: 0.04});
    const m = new THREE.Mesh(steleGeometry(P.page.w, P.page.h, P.page.curve), mat);
    m.castShadow = m.receiveShadow = true;
    const pose = slotPose(i);
    m.position.set(pose.x, pose.y, pose.z); m.rotation.y = pose.ry;
    m.userData.pid = def.pid; m.userData.slot = i; m.userData.lift = true; m.userData.baseY = pose.y;
    /* 一叠稿纸共用一组线装:只有前景页露得出装订面,后排页的线装藏起,
       否则三串订环悬在纸缘外;换页时随前景身份移交 */
    const binding = addBinding(m);
    binding.visible = (i === 0);
    m.userData.binding = binding;
    root.add(m); reg(m, 0.35 + i * 0.18, 1.9 + i * 0.18, 'rise');
    return m;
  });
  const pageMats = pages.map(m => m.material);
  /* 字体就绪后换正式纹理(每张纹理含纸底+内容+明暗带)。
     逐张生成/换贴/绘制,阶段之间让出主线程:三张 1024×1460 连续排印
     是单个 ~390ms 长任务(移动档实测),期间点击输入排队不可接受;
     分帧后单段最长 ~155ms,段间输入照常处理。首张带贴后立即 renderOnce
     把纹理上传也摊到各段,避免纹理全换后的首个动画帧集中上传。 */
  const texReady = fontsReady(article, digest, site).then(async () => {
    await new Promise(r => setTimeout(r, 0));   /* 与字体收尾 task 剥离 */
    for (let i = 0; i < PAGES.length; i++){
      const t = PAGES[i].tex();
      await new Promise(r => setTimeout(r, 0));
      pageMats[i].map = t; pageMats[i].emissiveMap = t; pageMats[i].needsUpdate = true;
      renderOnce();
      await new Promise(r => setTimeout(r, 0));
    }
    if (reduced()) renderOnce(); else start();
  });

  /* 虚线页(检索计划),远处低调 */
  const ghost = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.PlaneGeometry(P.ghost.w, P.ghost.h)),
    new THREE.LineDashedMaterial({color: 0x8A8F99, dashSize: 0.15, gapSize: 0.11, transparent: true}));
  ghost.computeLineDistances();
  ghost.position.set(P.ghost.x, P.ghost.y, P.ghost.z); ghost.rotation.y = P.ghost.ry;
  ghost.userData.link = links.about; ghost.userData.lift = true; ghost.userData.baseY = P.ghost.y;
  root.add(ghost); reg(ghost, 2.1, 2.6, 'fade');

  /* 虚空接触影 + 真实投影承接 */
  const shadowCatcher = new THREE.Mesh(new THREE.PlaneGeometry(24, 24), M.shadow);
  shadowCatcher.rotation.x = -Math.PI / 2; shadowCatcher.position.set(P.page.x - 0.6, 0.01, P.page.z - 0.6);
  scene.add(shadowCatcher); reg(shadowCatcher, 0, 0.6, 'fade');
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(60, 60), new THREE.ShadowMaterial({opacity: 0.2}));
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);

  /* 灯光:夜览背光点在页叠后方偏装订线侧,纸透光、左亮右暗 */
  const hemi = new THREE.HemisphereLight(0xE9E5D9, 0x8F8A7B, 0.9); scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xFFEFD4, 2.5);
  sun.castShadow = renderer.shadowMap.enabled;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = sun.shadow.camera.bottom = -12;
  sun.shadow.camera.right = sun.shadow.camera.top = 12;
  sun.shadow.bias = -0.0004;
  sun.position.set(-6, 13, 9);
  scene.add(sun);
  const rim = new THREE.DirectionalLight(0x6E9BFF, 0); rim.position.set(9, 6, -8); scene.add(rim);
  const fill = new THREE.DirectionalLight(0xC8D2E4, 0.3); fill.position.set(-8, 4, 11); scene.add(fill);
  const back = new THREE.PointLight(0xFFBE6E, 0, 10, 1.8); back.position.set(P.page.x - 1.1, 3.6, P.page.z - 1.6); scene.add(back);
  const sweep = new THREE.SpotLight(0xFFF6E2, 0, 40, 0.46, 0.6, 1.2);
  sweep.position.set(-12, 12, 10); scene.add(sweep, sweep.target);

  /* 主题 */
  let themeT = 0, themeTarget = 0;
  const cA = new THREE.Color(), cB = new THREE.Color();
  function lerpC(t, a, b, k){ cA.setHex(a); cB.setHex(b); t.copy(cA).lerp(cB, k); }
  function applyTheme(t){
    const D = LIGHT.day, N = LIGHT.night;
    lerpC(scene.background = scene.background || new THREE.Color(), D.sky, N.sky, t);
    lerpC(scene.fog.color, D.sky, N.sky, t);
    scene.fog.density = D.fogD + (N.fogD - D.fogD) * t;
    lerpC(hemi.color, D.hemiS, N.hemiS, t); lerpC(hemi.groundColor, D.hemiG, N.hemiG, t);
    hemi.intensity = D.hemiI + (N.hemiI - D.hemiI) * t;
    lerpC(sun.color, D.sunC, N.sunC, t);
    sun.intensity = D.sunI + (N.sunI - D.sunI) * t;
    sun.position.set(...D.sunPos.map((v, i) => v + (N.sunPos[i] - v) * t));
    rim.intensity = D.rimI + (N.rimI - D.rimI) * t;
    fill.intensity = D.fillI + (N.fillI - D.fillI) * t;
    back.intensity = D.backI + (N.backI - D.backI) * t;
    M.shadow.opacity = D.shadowI + (N.shadowI - D.shadowI) * t;
    lerpC(M.seal.emissive, 0x000000, 0x8A2E18, t);
    floor.material.opacity = 0.2 + 0.1 * t;
    /* 透光:emissiveMap 字处暗、纸处亮 → 夜间纸透暖光、字沉为剪影 */
    pageMats.forEach(m => { m.emissiveIntensity = D.pageEmI + (N.pageEmI - D.pageEmI) * t; });
  }

  /* 入场:三页错时立起 + 扫光 */
  track.forEach(o => {
    const e = o.userData.ent;
    if (e.kind === 'rise'){ e.from.y = o.position.y - 3.2; e.to.y = o.position.y; e.from.rz = 0.10; }
    if (e.kind === 'fade'){ e.from.op = 0; e.to.op = o.material.opacity ?? 1; }
  });
  const easeOut = x => 1 - Math.pow(1 - x, 3);
  const easeIO = x => x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
  let entT = -1;
  function playEntrance(){
    entT = 0;
    track.forEach(o => {
      const e = o.userData.ent;
      if (e.kind === 'rise'){ o.position.y = e.from.y; o.rotation.z = e.from.rz; }
      if (e.kind === 'fade'){ o.material.transparent = true; o.material.opacity = 0; }
    });
    sweep.intensity = 0;
  }
  function finishEntrance(){
    entT = -1; sweep.intensity = 0;
    track.forEach(o => {
      const e = o.userData.ent;
      if (e.kind === 'rise'){ o.position.y = e.to.y; o.rotation.z = 0; }
      if (e.kind === 'fade'){ o.material.opacity = e.to.op; }
    });
  }
  function stepEntrance(dt){
    if (entT < 0) return;
    entT += dt;
    track.forEach(o => {
      const e = o.userData.ent, k = easeOut(Math.min(Math.max((entT - e.t0) / (e.t1 - e.t0), 0), 1));
      if (e.kind === 'rise'){ o.position.y = e.from.y + (e.to.y - e.from.y) * k; o.rotation.z = e.from.rz * (1 - k); }
      if (e.kind === 'fade'){ o.material.opacity = e.to.op * k; }
    });
    const sk = Math.min(Math.max((entT - P.sweepAt) / 1.5, 0), 1);
    sweep.intensity = Math.sin(sk * Math.PI) * 55;
    sweep.target.position.set(-5 + sk * 12, 2.6, 0);
    if (entT > P.entrance + 0.4) finishEntrance();
  }

  /* 换页:目标页弧出到前景,原前景页退到腾出的槽位。
     动画中再次 select 不丢弃——排队最后一次选择,swap 完成时执行;
     否则页签面板(HTML 侧)已切换而 3D 未动,两侧状态分裂 */
  let swap = null, pendingSelect = null;
  function frontPage(){ return pages.find(p => p.userData.slot === 0); }
  function select(pid){
    const target = pages.find(p => p.userData.pid === pid);
    if (!target) return false;
    if (target.userData.slot === 0){
      /* 目标已是前景(槽位在换页开始时即交换,动画可能仍在进行):
         这是用户在动画期间把最后一次选择改回了正在换入的页——必须
         取消排队中的旧选择,否则动画完成后旧排队执行,终态≠最后选择;
         无动画时为重复选择,状态已一致,无动作。onSelect 把外部
         (可能被旧排队链拉走的)页签/面板同步回用户的最后一次选择 */
      if (swap){
        pendingSelect = null;
        if (onSelect) onSelect(pid);
        return true;
      }
      return true;
    }
    if (swap){ pendingSelect = pid; if (onSelect) onSelect(pid); return true; }
    const out = frontPage();
    const poseOut = slotPose(out.userData.slot), poseIn = slotPose(target.userData.slot);
    swap = {out, inn: target, k: 0,
      fromOut: {x: out.position.x, y: out.position.y, z: out.position.z, ry: out.rotation.y},
      toOut: {x: poseIn.x, y: poseIn.y, z: poseIn.z, ry: poseIn.ry},
      fromIn: {x: target.position.x, y: target.position.y, z: target.position.z, ry: target.rotation.y},
      toIn: {x: poseOut.x, y: poseOut.y, z: poseOut.z, ry: poseOut.ry}};
    const tSlot = target.userData.slot;   /* 交换槽位:目标进前景,原前景退到腾出的槽 */
    target.userData.slot = 0;
    out.userData.slot = tSlot;
    out.userData.baseY = poseIn.y; target.userData.baseY = poseOut.y;
    /* 线装随前景身份移交(后退页藏、前景页露) */
    out.userData.binding.visible = false;
    target.userData.binding.visible = true;
    if (onSelect) onSelect(pid);
    if (reduced()){ swap.k = 1; stepSwap(0); renderOnce(); }
    else start();
    return true;
  }
  function stepSwap(dt){
    if (!swap) return;
    swap.k = Math.min(swap.k + (swap.dur ? dt / swap.dur : 1), 1);
    const e = easeIO(swap.k);
    const o = swap.out, n = swap.inn;
    /* 退出页向相机方向鼓出弧线,避免两页路径中点相交 */
    const arc = Math.sin(e * Math.PI) * 1.0;
    o.position.set(
      swap.fromOut.x + (swap.toOut.x - swap.fromOut.x) * e,
      swap.fromOut.y + (swap.toOut.y - swap.fromOut.y) * e,
      swap.fromOut.z + (swap.toOut.z - swap.fromOut.z) * e + arc);
    o.rotation.y = swap.fromOut.ry + (swap.toOut.ry - swap.fromOut.ry) * e;
    n.position.set(
      swap.fromIn.x + (swap.toIn.x - swap.fromIn.x) * e,
      swap.fromIn.y + (swap.toIn.y - swap.fromIn.y) * e,
      swap.fromIn.z + (swap.toIn.z - swap.fromIn.z) * e);
    n.rotation.y = swap.fromIn.ry + (swap.toIn.ry - swap.fromIn.ry) * e;
    if (swap.k >= 1){
      swap = null;
      /* 执行排队的选择(快速连点只保留最后一次);select 内部会重新 start */
      if (pendingSelect){ const pid2 = pendingSelect; pendingSelect = null; select(pid2); }
    }
  }

  /* 交互:拖拽环顾(有限);点前景页进栏目,点后排页换页 */
  const ray = new THREE.Raycaster(), ptr = new THREE.Vector2();
  let dragging = false, moved = 0, px = 0, py = 0, hovered = null, liftT = new Map();
  const el2 = renderer.domElement;
  function pick(e){
    const r = el2.getBoundingClientRect();
    ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, camera);
    const hit = ray.intersectObjects([...pages, ghost], false)[0];
    return hit ? hit.object : null;
  }
  el2.addEventListener('pointerdown', e => { dragging = true; moved = 0; px = e.clientX; py = e.clientY; });
  el2.addEventListener('pointermove', e => {
    if (dragging){
      moved += Math.abs(e.clientX - px) + Math.abs(e.clientY - py);
      az = Math.min(Math.max(az - (e.clientX - px) * 0.0030, P.cam.az - P.cam.azSpan), P.cam.az + P.cam.azSpan);
      el = Math.min(Math.max(el + (e.clientY - py) * 0.0024, P.cam.elMin), P.cam.elMax);
      px = e.clientX; py = e.clientY;
      /* 用户主动操作不属于环境动画:循环停止(暂停动态/reduced-motion)时也立即重绘 */
      if (!running) renderOnce();
    } else {
      hovered = pick(e);
      el2.style.cursor = hovered ? 'pointer' : 'grab';
    }
  });
  el2.addEventListener('pointerup', e => {
    dragging = false;
    if (moved < 6){
      const hit = pick(e);
      if (!hit) return;
      if (hit === ghost){ location.href = hit.userData.link; return; }
      if (hit.userData.slot === 0){ location.href = PAGES.find(d => d.pid === hit.userData.pid).link; }
      else select(hit.userData.pid);
    }
  });
  el2.addEventListener('pointerleave', () => { hovered = null; });

  /* 循环管理:按需渲染 */
  let running = false, ambientOn = true, inView = true, pageVisible = !document.hidden, amb = 0;
  let inited = false;   /* 初始化收尾完成前 resize 不做首绘(见 resize 注) */
  const clock = new THREE.Clock();
  function needsLoop(){
    if (reduced()) return entT >= 0 || !!swap;
    return entT >= 0 || !!swap || Math.abs(themeTarget - themeT) > 0.002 || (ambientOn && inView && pageVisible);
  }
  function tick(){
    const dt = Math.min(clock.getDelta(), 0.05);
    amb += dt;
    if (Math.abs(themeTarget - themeT) > 0.0005){
      themeT += (themeTarget - themeT) * Math.min(dt * 2.2, 1);
      applyTheme(themeT);
    }
    stepEntrance(dt);
    if (swap){ swap.dur = reduced() ? 0 : P.swapDur; stepSwap(dt); }
    if (ambientOn && !reduced()){
      ghost.rotation.y = P.ghost.ry + Math.sin(amb * 0.4) * 0.05;
    }
    /* 悬停:抬升 + 页缘微光。入场进行中时 stepEntrance 已写入 y,
       在其偏移上叠加悬停与环境位移,不再同帧覆盖入场。换页中的页不叠加。 */
    [...pages, ghost].forEach(o => {
      const cur = liftT.get(o) || 0, tgt = (o === hovered) ? 1 : 0;
      const nv = cur + (tgt - cur) * Math.min(dt * 8, 1);
      liftT.set(o, nv);
      if (o.userData.baseY !== undefined && !(swap && (swap.out === o || swap.inn === o))){
        const entOff = (entT >= 0) ? o.position.y - o.userData.baseY : 0;
        o.position.y = o.userData.baseY + entOff + nv * 0.3 +
          (ambientOn && !reduced() && o !== hovered ? Math.sin(amb * 0.75 + o.id) * 0.045 : 0);
      }
    });
    const fp = frontPage();
    const hov = fp ? (liftT.get(fp) || 0) : 0;
    if (fp && (hov > 0.01 || hovered === fp)){
      const base = LIGHT.day.pageEmI + (LIGHT.night.pageEmI - LIGHT.day.pageEmI) * themeT;
      fp.material.emissiveIntensity = base * (1 + hov * 0.35);
    }
    placeCam();
    renderer.render(scene, camera);
    if (!needsLoop()){ running = false; renderer.setAnimationLoop(null); }
  }
  function start(){ if (!running){ running = true; clock.getDelta(); renderer.setAnimationLoop(tick); } }
  function stop(){ running = false; renderer.setAnimationLoop(null); }
  function renderOnce(){ applyTheme(themeT); placeCam(); renderer.render(scene, camera); }

  if ('IntersectionObserver' in window)
    new IntersectionObserver(en => { inView = en[0].isIntersecting; if (inView) start(); }, {threshold: 0.05}).observe(host);
  document.addEventListener('visibilitychange', () => { pageVisible = !document.hidden; if (pageVisible) start(); });

  /* 初始化分段让出:几何/线装主体与 program 编译、编译与首个渲染之间
     各让出一帧,移动档下 createScene 尾部原是单个 ~410ms 长任务(首绘
     内联在 resize 里做全部 shader 编译,~284ms),分帧后单段 <160ms,
     段间点击输入照常处理;场景宿主初始 opacity=0,中间多出的帧不可见 */
  await new Promise(r => setTimeout(r, 0));
  renderer.compile(scene, camera);
  await new Promise(r => setTimeout(r, 0));
  resize(); placeCam();
  if (reduced()){ finishEntrance(); } else { playEntrance(); }
  applyTheme(0);

  const api = {
    /* 与 R4/R5 同约定:任何主题变化立即 applyTheme+renderOnce(reduced-motion 也重绘) */
    setTheme(dark, immediate){
      themeTarget = dark ? 1 : 0;
      if (immediate || reduced()){ themeT = themeTarget; applyTheme(themeT); renderOnce(); }
      else start();
    },
    /* 目标主题只读(渐变中即目标值):验收脚本观测首帧是否采用最新主题 */
    themeDark(){ return themeTarget === 1; },
    resetView(){ az = PARAMS.cam.az; el = PARAMS.cam.el; if (reduced()) renderOnce(); else start(); },
    replay(){ if (reduced()){ finishEntrance(); renderOnce(); } else { playEntrance(); start(); } },
    setAmbient(on){ ambientOn = on; if (on) start(); else if (!needsLoop()) stop(); },
    isAmbientOn(){ return ambientOn; },
    start, stop,
    texReady,
    /* 换页:pid ∈ posts/digest/about;返回是否受理 */
    select,
    current(){ const f = frontPage(); return f ? f.userData.pid : null; },
    /* 前景页装订线底部孔投影为 host 内 CSS 像素,供 2D「落线」衔接正文 thread;
       相机/布局/换页后需重新取值(由调用方驱动) */
    projectBindingBottom(){
      const fp2 = frontPage();
      if (!fp2) return null;
      const s = P.page;
      const R2 = s.w / s.curve, lx = (P.binding.x - 0.5) * s.w, a = lx / R2;
      /* 纹理 canvas y 向下 → 视觉最下方的孔是 v=0.18(局部 y 最小) */
      const local = new THREE.Vector3(Math.sin(a) * R2, (0.18 - 0.5) * s.h,
        (1 - Math.cos(a)) * R2 - (1 - Math.cos(s.w / 2 / R2)) * R2 * 0.5);
      const ndc = fp2.localToWorld(local).project(camera);
      if (ndc.z > 1) return null;
      return {x: (ndc.x + 1) / 2 * host.clientWidth, y: (1 - ndc.y) / 2 * host.clientHeight};
    },
    stats(){
      let tris = 0, objs = 0;
      scene.traverse(o => { if (o.geometry){ objs++; const g = o.geometry; tris += (g.index ? g.index.count : g.attributes.position.count) / 3; }});
      return {triangles: Math.round(tris), objects: objs};
    },
  };
  start();
  inited = true;   /* 此后暂停态下的窗口变化恢复即时重绘 */
  return api;
}
