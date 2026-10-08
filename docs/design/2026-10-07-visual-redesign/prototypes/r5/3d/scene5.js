/* ═══════════════════════════════════════════════════════════
   R5 首页场景「字场 · 碑页」· scene5.js — 程序化建模源资产
   概念深化(R4「纸筑」→ R5):一页印着真实文章首段的稿纸立成碑,
   微弯;背后错层暗影页;左缘线装订眼走朱砂线。
   夜览:背光透纸,纸暖字沉。碑页即精选文章的封面。
   接口:createScene(host, opts) → Promise<{setTheme, resetView, replay, setAmbient, isAmbientOn, start, stop, stats}>
   (Promise 化:碑页纹理需等分片字体就绪后才排印真实文字)
   依赖:同目录 three.module.min.js(r180,本地固定)
   ═══════════════════════════════════════════════════════════ */
import * as THREE from './three.module.min.js';

/* ── 参数表(可编辑源;改这里即可重建/调整场景) ── */
export const PARAMS = {
  cam: {fov: 34, r: 16.4, az: 0.30, el: 0.17, azSpan: 0.18, elMin: 0.10, elMax: 0.38, ty: 3.55,
        txM: 1.55, zoomMax: 2.1},   /* txM:竖屏 lookAt 目标右移,保住碑页右缘与装订线同框 */
  stele: {w: 5.2, h: 7.4, curve: 0.14, x: 2.1, y: 0, z: 0, ry: -0.16},
  backs: [                                  /* 后衬错层页:深一阶、错位、略转 */
    {dx: -1.25, dy: -0.28, dz: -1.15, ry: -0.05, tone: 0.80},
    {dx: -2.3,  dy: -0.52, dz: -2.3,  ry: 0.05,  tone: 0.58},
  ],
  binding: {x: 0.075, holes: 4},            /* 订眼位置(页宽比例,左缘内) */
  ghost: {w: 2.0, h: 2.85, x: 5.1, y: 1.6, z: -0.7, ry: -0.5},
  entrance: 2.8, sweepAt: 1.0,
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

/* 真实文章摘录(《你好,nanmu-blog》首段全文,站点真实文本,非虚构填充;
   含 topic-digest 两句,使"这两段历史"承接成立) */
const ARTICLE_DATE = '2026-10-02 · 随笔 / 建站';
const ARTICLE_PARA = '今年上半年,我做过一个功能很多的博客:文章、采集、日报、自动优化,设计越铺越大,十二周半之后写不动,烂尾收场。它留下的教训很具体:先把最小的东西做完、上线、能用,再谈别的。八月末,我又搭了个小爬取试点 topic-digest,并在八月三十一日完成上线。它用定时采集和静态页面,把收集信息到展示内容这条流程串了起来,规模比前一个项目小得多。这次重开博客,就从这两段历史里长出来——前一段告诉我别做什么,后一段告诉我最小闭环长什么样。设计时还参考了两个外部项目 AIHOT 和 PowerContext,各借了一点模式,都没有整体照搬。';

/* 碑页纹理:真实排印(1024×1460),字体就绪后绘制 */
async function steleTex(){
  try { await Promise.all([
    document.fonts.load('900 88px "Noto Serif SC"'),
    document.fonts.load('400 35px "Noto Serif SC"'),
    document.fonts.load('600 26px "Noto Serif SC"'),
  ]); } catch(e){ /* 字体缺失回退系统衬线,仍可读 */ }
  const W = 1024, H = 1460;
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d'), r = rng(97);
  g.fillStyle = '#F7F4EB'; g.fillRect(0, 0, W, H);
  for (let i = 0; i < 11000; i++){ g.fillStyle = `rgba(96,88,64,${r() * 0.05})`; g.fillRect(r() * W, r() * H, 1 + r() * 1.6, 1); }
  for (let i = 0; i < 130; i++){
    g.strokeStyle = `rgba(130,118,90,${0.02 + r() * 0.03})`; g.lineWidth = 0.8;
    const x = r() * W, y = r() * H;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + (r() - .5) * 46, y + (r() - .5) * 7); g.stroke();
  }
  /* 顶部栏目标记:朱砂印「文」+ 栏目名(文字区让开左缘装订线) */
  const TM = 152;                              /* 文字左边距:装订线在 0.075W≈77px */
  g.fillStyle = '#C2402A'; g.fillRect(TM, 76, 40, 40);
  g.fillStyle = '#F7F4EB'; g.font = '900 28px "Noto Serif SC", serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText('文', TM + 20, 98);
  g.textAlign = 'left';
  g.fillStyle = 'rgba(29,31,36,0.55)'; g.font = '600 26px "Noto Serif SC", serif';
  g.fillText('NANMU · 手写文章', TM + 58, 98);
  /* 真实标题 */
  g.fillStyle = '#14161A'; g.font = '900 88px "Noto Serif SC", serif';
  g.fillText('你好,', TM, 226);
  g.fillText('nanmu-blog', TM, 330);
  g.fillStyle = 'rgba(29,31,36,0.5)'; g.font = '400 27px "Noto Serif SC", serif';
  g.fillText(ARTICLE_DATE, TM, 396);
  g.strokeStyle = 'rgba(29,31,36,0.4)'; g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(TM, 436); g.lineTo(W - 84, 436); g.stroke();
  /* 真实正文首段:逐字排印 */
  g.font = '400 35px "Noto Serif SC", serif'; g.fillStyle = '#22242A';
  const maxW = W - TM - 72, lineH = 62; let x = TM, y = 506;
  for (const ch of ARTICLE_PARA){
    const w = g.measureText(ch).width;
    if (x + w > TM + maxW){ x = TM; y += lineH; }
    g.fillText(ch, x, y); x += w;
  }
  g.fillStyle = 'rgba(29,31,36,0.45)'; g.font = '400 24px "Noto Serif SC", serif';
  g.fillText('第 1 篇 · 全文约 600 字 · nanmu.xyz', TM, H - 92);
  /* 订眼:孔在左缘内,3D 朱砂线从此穿过;孔内径向渐变 + 投影环,做出穿透纸面的厚度 */
  const holeX = W * PARAMS.binding.x;
  for (let i = 0; i < PARAMS.binding.holes; i++){
    const hy = H * (0.18 + i * 0.213);
    const hg = g.createRadialGradient(holeX - 3, hy - 3, 2, holeX, hy, 17);
    hg.addColorStop(0, 'rgba(8,7,5,0.95)'); hg.addColorStop(0.62, 'rgba(20,18,14,0.85)');
    hg.addColorStop(1, 'rgba(20,18,14,0)');
    g.fillStyle = hg;
    g.beginPath(); g.arc(holeX, hy, 17, 0, Math.PI * 2); g.fill();
    /* 孔的纸壁亮边(右下受光) */
    g.strokeStyle = 'rgba(247,244,235,0.9)'; g.lineWidth = 2.5;
    g.beginPath(); g.arc(holeX, hy, 14.5, -0.5, 1.8); g.stroke();
    g.strokeStyle = 'rgba(70,60,44,0.5)'; g.lineWidth = 2;
    g.beginPath(); g.arc(holeX, hy, 16, 2.2, 4.6); g.stroke();
  }
  /* 弓面明暗:页面两边向 +z 弯出,横向明带让曲面可读。
     对比要足够强——夜间透光以 emissiveMap 为主,纸面层次全部来自这张纹理;
     装订线侧(左)亮、向右渐暗,模拟背光自左后透出 */
  const bow = g.createLinearGradient(0, 0, W, 0);
  bow.addColorStop(0, 'rgba(58,48,34,0.20)'); bow.addColorStop(0.10, 'rgba(255,246,226,0.13)');
  bow.addColorStop(0.22, 'rgba(58,48,34,0.05)'); bow.addColorStop(0.42, 'rgba(255,252,244,0.10)');
  bow.addColorStop(0.62, 'rgba(255,252,244,0.03)'); bow.addColorStop(0.85, 'rgba(58,48,34,0.14)');
  bow.addColorStop(1, 'rgba(58,48,34,0.26)');
  g.fillStyle = bow; g.fillRect(0, 0, W, H);
  /* 大梯度:左(装订侧)亮 → 右渐暗,夜间透光的主层次 */
  const wash = g.createLinearGradient(0, 0, W, 0);
  wash.addColorStop(0, 'rgba(255,244,218,0.16)'); wash.addColorStop(0.45, 'rgba(255,244,218,0.05)');
  wash.addColorStop(1, 'rgba(46,36,24,0.20)');
  g.fillStyle = wash; g.fillRect(0, 0, W, H);
  /* 页缘切面:右缘受光边 + 左缘装订侧厚度 */
  const eg = g.createLinearGradient(W - 34, 0, W, 0);
  eg.addColorStop(0, 'rgba(90,80,60,0)'); eg.addColorStop(1, 'rgba(90,80,60,0.42)');
  g.fillStyle = eg; g.fillRect(W - 34, 0, 34, H);
  const lg = g.createLinearGradient(0, 0, 26, 0);
  lg.addColorStop(0, 'rgba(70,60,44,0.34)'); lg.addColorStop(1, 'rgba(70,60,44,0)');
  g.fillStyle = lg; g.fillRect(0, 0, 26, H);
  const t = new THREE.CanvasTexture(c);
  t.anisotropy = 8;
  return t;
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
  const links = Object.assign({post: 'post-hello.html', digest: 'digest.html'}, opts.links || {});

  const renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, innerWidth < 760 ? 1.5 : 2));
  renderer.shadowMap.enabled = innerWidth >= 760;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.06;
  renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;touch-action:pan-y;cursor:grab';
  renderer.domElement.setAttribute('aria-label', '三维场景:一页立着的发光稿纸,印着最新文章;可拖拽环顾,点击页面进入文章');
  host.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0xF0EDE5, 0.012);
  const camera = new THREE.PerspectiveCamera(P.cam.fov, 1, 0.1, 120);
  let az = P.cam.az, el = P.cam.el;
  function placeCam(){
    const r = P.cam.r * (camera.userData.zoom || 1);
    camera.position.set(Math.sin(az) * Math.cos(el) * r, Math.sin(el) * r + P.cam.ty, Math.cos(az) * Math.cos(el) * r);
    /* 竖屏:lookAt 目标向碑页一侧移,构图居中而非把碑页右缘切出画外 */
    const tx = (camera.userData.txK || 0) * P.cam.txM;
    camera.lookAt(tx, P.cam.ty, 0);
  }
  function resize(){
    const w = host.clientWidth || 1, h = host.clientHeight || 1;
    renderer.setSize(w, h); camera.aspect = w / h;
    /* 竖屏构图:横向视角不足时按比例拉远,保住碑页与装订线 */
    camera.userData.zoom = Math.min(P.cam.zoomMax, Math.max(1, 1.02 / Math.max(camera.aspect, 0.01)));
    /* txK 0(横屏)→1(竖屏)平滑过渡 */
    camera.userData.txK = Math.min(Math.max((1.05 - camera.aspect) / 0.45, 0), 1);
    camera.updateProjectionMatrix();
    placeCam();
    if (!running) renderOnce();   /* 循环停止(暂停/reduced-motion)时,窗口变化也要重绘 */
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

  /* 碑页:先素纸占位,字体就绪后换正式文字纹理 */
  const s = P.stele;
  const steleMat = new THREE.MeshStandardMaterial({
    map: plainPaperTex(3, 1.0), roughness: 0.88, side: THREE.DoubleSide,
    emissive: 0xFFC887, emissiveIntensity: 0.04});
  const stele = new THREE.Mesh(steleGeometry(s.w, s.h, s.curve), steleMat);
  stele.castShadow = stele.receiveShadow = true;
  stele.position.set(s.x, s.h / 2 + s.y, s.z); stele.rotation.y = s.ry;
  stele.userData.link = links.post; stele.userData.lift = true; stele.userData.baseY = stele.position.y;
  root.add(stele); reg(stele, 0.35, 1.9, 'rise');
  const texReady = steleTex().then(t => {
    steleMat.map = t; steleMat.emissiveMap = t; steleMat.needsUpdate = true;
    if (reduced()) renderOnce(); else start();
  });

  /* 后衬错层页 */
  const backMats = [];
  P.backs.forEach((b, i) => {
    const mat = new THREE.MeshStandardMaterial({map: plainPaperTex(11 + i, b.tone),
      roughness: 0.92, side: THREE.DoubleSide, emissive: 0x8A7B5E, emissiveIntensity: 0.0});
    backMats.push(mat);
    const m = new THREE.Mesh(steleGeometry(s.w, s.h, s.curve), mat);
    m.castShadow = true;
    m.position.set(s.x + b.dx, s.h / 2 + s.y + b.dy, s.z + b.dz); m.rotation.y = s.ry + b.ry;
    root.add(m); reg(m, 0.2 + i * 0.15, 1.6 + i * 0.15, 'rise');
  });

  /* 线装:朱砂线环穿过订眼,沿左缘走线 */
  {
    const holeU = P.binding.x, R2 = s.w / s.curve;
    const lx = (holeU - 0.5) * s.w;
    const a = lx / R2;
    const px = Math.sin(a) * R2, pz = (1 - Math.cos(a)) * R2 - (1 - Math.cos(s.w / 2 / R2)) * R2 * 0.5;
    const threadGrp = new THREE.Group();
    for (let i = 0; i < P.binding.holes; i++){
      const v = 0.18 + i * 0.213;
      const hy = (v - 0.5) * s.h;
      const loop = new THREE.Mesh(new THREE.TorusGeometry(0.085, 0.026, 8, 20), M.seal);
      loop.position.set(px, hy, pz + 0.045);
      threadGrp.add(loop);
      if (i < P.binding.holes - 1){
        const nv = 0.18 + (i + 1) * 0.213;
        const segLen = (nv - v) * s.h - 0.11;
        const seg = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, segLen, 6), M.seal);
        seg.position.set(px, (hy + (nv - 0.5) * s.h) / 2, pz + 0.045);
        threadGrp.add(seg);
      }
    }
    stele.add(threadGrp);
  }

  /* 虚线页(日报计划),远处低调 */
  const ghost = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.PlaneGeometry(P.ghost.w, P.ghost.h)),
    new THREE.LineDashedMaterial({color: 0x8A8F99, dashSize: 0.15, gapSize: 0.11, transparent: true}));
  ghost.computeLineDistances();
  ghost.position.set(P.ghost.x, P.ghost.y, P.ghost.z); ghost.rotation.y = P.ghost.ry;
  ghost.userData.link = links.digest; ghost.userData.lift = true; ghost.userData.baseY = P.ghost.y;
  root.add(ghost); reg(ghost, 2.1, 2.6, 'fade');

  /* 虚空接触影(替代 R4 的网格地面) + 真实投影承接 */
  const shadowCatcher = new THREE.Mesh(new THREE.PlaneGeometry(24, 24), M.shadow);
  shadowCatcher.rotation.x = -Math.PI / 2; shadowCatcher.position.set(s.x - 0.6, 0.01, s.z - 0.6);
  scene.add(shadowCatcher); reg(shadowCatcher, 0, 0.6, 'fade');
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(60, 60), new THREE.ShadowMaterial({opacity: 0.2}));
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);

  /* 灯光:夜览背光点在碑页后方,纸透光 */
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
  /* 夜间背光点偏向装订线一侧:左缘(线装)最亮,向右渐暗,弓面明暗成形 */
  const back = new THREE.PointLight(0xFFBE6E, 0, 10, 1.8); back.position.set(s.x - 1.1, 3.6, s.z - 1.6); scene.add(back);
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
    steleMat.emissiveIntensity = D.pageEmI + (N.pageEmI - D.pageEmI) * t;
    backMats.forEach((m, i) => { m.emissiveIntensity = (0.20 - i * 0.07) * t; });
  }

  /* 入场:碑页立起 + 扫光 */
  track.forEach(o => {
    const e = o.userData.ent;
    if (e.kind === 'rise'){ e.from.y = o.position.y - 3.2; e.to.y = o.position.y; e.from.rz = 0.10; }
    if (e.kind === 'fade'){ e.from.op = 0; e.to.op = o.material.opacity ?? 1; }
  });
  const easeOut = x => 1 - Math.pow(1 - x, 3);
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

  /* 交互:拖拽环顾(有限),点击碑页/虚线页导航 */
  const ray = new THREE.Raycaster(), ptr = new THREE.Vector2();
  let dragging = false, moved = 0, px = 0, py = 0, hovered = null, liftT = new Map();
  const el2 = renderer.domElement;
  function pick(e){
    const r = el2.getBoundingClientRect();
    ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, camera);
    const hit = ray.intersectObjects([stele, ghost], false)[0];
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
    if (moved < 6){ const hit = pick(e); if (hit && hit.userData.link) location.href = hit.userData.link; }
  });
  el2.addEventListener('pointerleave', () => { hovered = null; });

  /* 循环管理:按需渲染 */
  let running = false, ambientOn = true, inView = true, pageVisible = !document.hidden, amb = 0;
  const clock = new THREE.Clock();
  function needsLoop(){
    if (reduced()) return entT >= 0;
    return entT >= 0 || Math.abs(themeTarget - themeT) > 0.002 || (ambientOn && inView && pageVisible);
  }
  function tick(){
    const dt = Math.min(clock.getDelta(), 0.05);
    amb += dt;
    if (Math.abs(themeTarget - themeT) > 0.0005){
      themeT += (themeTarget - themeT) * Math.min(dt * 2.2, 1);
      applyTheme(themeT);
    }
    stepEntrance(dt);
    if (ambientOn && !reduced()){
      ghost.rotation.y = P.ghost.ry + Math.sin(amb * 0.4) * 0.05;
    }
    /* 悬停:抬升 + 页缘微光。入场进行中时 stepEntrance 已写入 y,
       在其偏移上叠加悬停与环境位移,不再同帧覆盖入场。 */
    [stele, ghost].forEach(o => {
      const cur = liftT.get(o) || 0, tgt = (o === hovered) ? 1 : 0;
      const nv = cur + (tgt - cur) * Math.min(dt * 8, 1);
      liftT.set(o, nv);
      if (o.userData.baseY !== undefined){
        const entOff = (entT >= 0) ? o.position.y - o.userData.baseY : 0;
        o.position.y = o.userData.baseY + entOff + nv * 0.3 +
          (ambientOn && !reduced() && o !== hovered ? Math.sin(amb * 0.75 + o.id) * 0.045 : 0);
      }
    });
    const hov = liftT.get(stele) || 0;
    if (hov > 0.01 || hovered === stele){
      const base = LIGHT.day.pageEmI + (LIGHT.night.pageEmI - LIGHT.day.pageEmI) * themeT;
      steleMat.emissiveIntensity = base * (1 + hov * 0.35);
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

  resize(); placeCam();
  if (reduced()){ finishEntrance(); } else { playEntrance(); }
  applyTheme(0);

  const api = {
    /* 与 R4 同约定:任何主题变化立即 applyTheme+renderOnce(reduced-motion 也重绘) */
    setTheme(dark, immediate){
      themeTarget = dark ? 1 : 0;
      if (immediate || reduced()){ themeT = themeTarget; applyTheme(themeT); renderOnce(); }
      else start();
    },
    resetView(){ az = PARAMS.cam.az; el = PARAMS.cam.el; if (reduced()) renderOnce(); else start(); },
    replay(){ if (reduced()){ finishEntrance(); renderOnce(); } else { playEntrance(); start(); } },
    setAmbient(on){ ambientOn = on; if (on) start(); else if (!needsLoop()) stop(); },
    isAmbientOn(){ return ambientOn; },
    start, stop,
    texReady,
    /* 装订线底部孔投影为 host 内 CSS 像素,供 2D「落线」衔接正文 thread;
       相机/布局变化后需重新取值(由调用方驱动) */
    projectBindingBottom(){
      const R2 = s.w / s.curve, lx = (P.binding.x - 0.5) * s.w, a = lx / R2;
      /* 纹理 canvas y 向下 → 视觉最下方的孔是 v=0.18(局部 y 最小) */
      const vBottom = 0.18;
      const local = new THREE.Vector3(Math.sin(a) * R2, (vBottom - 0.5) * s.h,
        (1 - Math.cos(a)) * R2 - (1 - Math.cos(s.w / 2 / R2)) * R2 * 0.5);
      const ndc = stele.localToWorld(local).project(camera);
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
  return api;
}
