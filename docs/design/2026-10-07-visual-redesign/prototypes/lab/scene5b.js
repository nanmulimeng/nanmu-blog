/* R5-lab 方案 B「字场 · 碑页」场景实验
   与 A/R4 的空间逻辑不同:一页印着真实文章首段的稿纸立成碑,
   微弯,背后错层暗影页,左缘线装订眼走朱砂线;夜览背透光、字成剪影。 */
import * as THREE from '../r4/3d/three.module.min.js';

export const PARAMS = {
  cam: {fov: 34, r: 15.5, az: 0.34, el: 0.16, azSpan: 0.22, elMin: 0.10, elMax: 0.42, ty: 3.6},
  stele: {w: 5.2, h: 7.4, curve: 0.14, x: 2.1, y: 0, z: 0, ry: -0.10},
  backs: [                                  /* 后衬错层页:深一阶、错位、略转 */
    {dx: -0.9, dy: -0.25, dz: -1.1, ry: -0.02, tone: 0.82},
    {dx: -1.7, dy: -0.45, dz: -2.2, ry: 0.06, tone: 0.62},
  ],
  binding: {x: 0.42, holes: 4},             /* 订眼距左缘(x 占页宽比例) */
  entrance: 2.8, sweepAt: 1.0,
};
export const LIGHT = {
  day:   {sky: 0xF0EDE5, fogD: 0.012, hemiS: 0xE9E5D9, hemiG: 0x8F8A7B, hemiI: 0.9,
          sunC: 0xFFEFD4, sunI: 2.5, sunPos: [-6, 13, 9], rimI: 0.0, backI: 0.0, fillI: 0.3,
          pageEmI: 0.04, translucency: 0.0, shadowI: 0.18},
  night: {sky: 0x090C12, fogD: 0.016, hemiS: 0x18202F, hemiG: 0x04060A, hemiI: 0.42,
          sunC: 0x8FA8D8, sunI: 0.3, sunPos: [7, 10, -8], rimI: 2.3, backI: 3.2, fillI: 0.22,
          pageEmI: 0.12, translucency: 0.85, shadowI: 0.5},
};

function rng(seed){ let s = seed >>> 0; return () => (s = s * 1664525 + 1013904223 >>> 0) / 4294967296; }

/* 真实文章首段(《你好,nanmu-blog》真实文本,非虚构填充;标题直接排印) */
const ARTICLE_DATE = '2026-10-02 · 随笔 / 建站';
const ARTICLE_PARA = '今年上半年,我做过一个功能很多的博客:文章、采集、日报、自动优化,设计越铺越大,十二周半之后写不动,烂尾收场。它留下的教训很具体:先把最小的东西做完、上线、能用,再谈别的。这次重开博客,就从这两段历史里长出来——前一段告诉我别做什么,后一段告诉我最小闭环长什么样。';

/* 碑页纹理:真实排印。字号/行距按 1024×1460 画布手排 */
async function steleTex(){
  try { await Promise.all([
    document.fonts.load('900 92px "Noto Serif SC"'),
    document.fonts.load('400 34px "Noto Serif SC"'),
    document.fonts.load('600 30px "Noto Serif SC"'),
  ]); } catch(e){ /* 字体缺失时回退系统衬线,仍可读 */ }
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
  /* 顶部栏目标记 */
  g.fillStyle = '#C2402A'; g.fillRect(84, 76, 40, 40);
  g.fillStyle = '#F7F4EB'; g.font = '900 28px "Noto Serif SC", serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText('文', 104, 98);
  g.textAlign = 'left';
  g.fillStyle = 'rgba(29,31,36,0.55)'; g.font = '600 26px "Noto Serif SC", serif';
  g.fillText('NANMU · 手写文章', 142, 98);
  /* 真实标题(两行) */
  g.fillStyle = '#14161A'; g.font = '900 88px "Noto Serif SC", serif';
  g.fillText('你好,', 84, 226);
  g.fillText('nanmu-blog', 84, 330);
  g.fillStyle = 'rgba(29,31,36,0.5)'; g.font = '400 27px "Noto Serif SC", serif';
  g.fillText(ARTICLE_DATE, 84, 396);
  g.strokeStyle = 'rgba(29,31,36,0.4)'; g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(84, 436); g.lineTo(W - 84, 436); g.stroke();
  /* 真实正文第一段:逐字排,两端对齐感(末行自然) */
  g.font = '400 35px "Noto Serif SC", serif'; g.fillStyle = '#22242A';
  const maxW = W - 168, lineH = 62; let x = 84, y = 506;
  for (const ch of ARTICLE_PARA){
    const w = g.measureText(ch).width;
    if (x + w > 84 + maxW){ x = 84; y += lineH; }
    g.fillText(ch, x, y); x += w;
  }
  /* 底部:装订说明行 + 页码 */
  g.fillStyle = 'rgba(29,31,36,0.45)'; g.font = '400 24px "Noto Serif SC", serif';
  g.fillText('第 1 篇 · 全文约 600 字 · nanmu.xyz', 84, H - 92);
  /* 订眼(画在纹理上的孔,3D 朱砂线穿过) */
  const holeX = W * PARAMS.binding.x;
  for (let i = 0; i < PARAMS.binding.holes; i++){
    const hy = H * (0.18 + i * 0.213);
    g.fillStyle = 'rgba(20,18,14,0.85)';
    g.beginPath(); g.arc(holeX, hy, 13, 0, Math.PI * 2); g.fill();
    g.strokeStyle = 'rgba(247,244,235,0.9)'; g.lineWidth = 3;
    g.beginPath(); g.arc(holeX, hy, 16, 0, Math.PI * 2); g.stroke();
  }
  /* 页缘切面 */
  const eg = g.createLinearGradient(W - 34, 0, W, 0);
  eg.addColorStop(0, 'rgba(90,80,60,0)'); eg.addColorStop(1, 'rgba(90,80,60,0.42)');
  g.fillStyle = eg; g.fillRect(W - 34, 0, 34, H);
  const t = new THREE.CanvasTexture(c);
  t.anisotropy = 4;
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
  /* 以页面中心微弯:弓形,不像书页那样绕脊 */
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
  host.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0xF0EDE5, 0.012);
  const camera = new THREE.PerspectiveCamera(P.cam.fov, 1, 0.1, 120);
  let az = P.cam.az, el = P.cam.el;
  function placeCam(){
    const r = P.cam.r * (camera.userData.zoom || 1);
    camera.position.set(Math.sin(az) * Math.cos(el) * r, Math.sin(el) * r + P.cam.ty, Math.cos(az) * Math.cos(el) * r);
    camera.lookAt(0, P.cam.ty, 0);
  }
  function resize(){
    const w = host.clientWidth || 1, h = host.clientHeight || 1;
    renderer.setSize(w, h); camera.aspect = w / h;
    camera.userData.zoom = Math.min(1.9, Math.max(1, 1.05 / Math.max(camera.aspect, 0.01)));
    camera.updateProjectionMatrix();
    placeCam();
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

  /* 碑页(真实文章纹理,同步前先画素纸,字体就绪后换正式纹理) */
  const s = P.stele;
  const steleMat = new THREE.MeshStandardMaterial({
    map: plainPaperTex(3, 1.0), roughness: 0.88, side: THREE.DoubleSide,
    emissive: 0xFFE9BE, emissiveIntensity: 0.04});
  const stele = new THREE.Mesh(steleGeometry(s.w, s.h, s.curve), steleMat);
  stele.castShadow = stele.receiveShadow = true;
  stele.position.set(s.x, s.h / 2 + s.y, s.z); stele.rotation.y = s.ry;
  stele.userData.link = links.post; stele.userData.lift = true; stele.userData.baseY = stele.position.y;
  root.add(stele); reg(stele, 0.35, 1.9, 'rise');
  steleTex().then(t => {
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

  /* 线装:朱砂线穿过订眼,沿页左缘走线 */
  const threadGrp = new THREE.Group();
  {
    const holeU = P.binding.x, R2 = s.w / s.curve;
    const lx = (holeU - 0.5) * s.w;           /* 页面局部 x */
    const a = lx / R2;
    const px = Math.sin(a) * R2, pz = (1 - Math.cos(a)) * R2 - (1 - Math.cos(s.w / 2 / R2)) * R2 * 0.5;
    for (let i = 0; i < P.binding.holes; i++){
      const v = 0.18 + i * 0.213;
      const hy = (v - 0.5) * s.h;
      /* 订眼处的线环 */
      const loop = new THREE.Mesh(new THREE.TorusGeometry(0.09, 0.028, 8, 20), M.seal);
      loop.position.set(px, hy, pz + 0.05);
      threadGrp.add(loop);
      if (i < P.binding.holes - 1){
        const nv = 0.18 + (i + 1) * 0.213;
        const segLen = (nv - v) * s.h - 0.12;
        const seg = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.022, segLen, 6), M.seal);
        seg.position.set(px, (hy + (nv - 0.5) * s.h) / 2, pz + 0.05);
        threadGrp.add(seg);
      }
    }
    stele.add(threadGrp);
  }

  /* 虚线页(日报计划),远处低调 */
  const ghost = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.PlaneGeometry(2.2, 3.1)),
    new THREE.LineDashedMaterial({color: 0x8A8F99, dashSize: 0.15, gapSize: 0.11, transparent: true}));
  ghost.computeLineDistances();
  ghost.position.set(6.4, 1.9, -2.6); ghost.rotation.y = -0.55;
  ghost.userData.link = links.digest; ghost.userData.lift = true; ghost.userData.baseY = ghost.position.y;
  root.add(ghost); reg(ghost, 2.1, 2.6, 'fade');

  /* 接触影 + 投影承接 */
  const shadowCatcher = new THREE.Mesh(new THREE.PlaneGeometry(24, 24), M.shadow);
  shadowCatcher.rotation.x = -Math.PI / 2; shadowCatcher.position.set(s.x, 0.01, s.z - 0.4);
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
  const back = new THREE.PointLight(0xFFBE6E, 0, 16, 1.7); back.position.set(s.x + 0.4, 3.6, s.z - 1.6); scene.add(back);
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
    lerpC(M.seal.emissive, 0x000000, 0x6E2412, t);
    floor.material.opacity = 0.2 + 0.1 * t;
    /* 透光:emissiveMap 字处暗、纸处亮 → 夜间纸透暖光、字成剪影 */
    steleMat.emissiveIntensity = D.pageEmI + (N.translucency - D.pageEmI) * t;
    backMats.forEach((m, i) => { m.emissiveIntensity = 0.0 + (0.22 - i * 0.08) * t; });
  }

  /* 入场 */
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

  /* 交互 */
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

  /* 循环 */
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
      ghost.rotation.y = -0.55 + Math.sin(amb * 0.4) * 0.05;
      if (hovered !== stele)
        stele.position.y = stele.userData.baseY + Math.sin(amb * 0.7) * 0.04;
      if (hovered !== ghost)
        ghost.position.y = ghost.userData.baseY + Math.sin(amb * 0.8 + 9) * 0.05;
    }
    [stele, ghost].forEach(o => {
      const cur = liftT.get(o) || 0, tgt = (o === hovered) ? 1 : 0;
      const nv = cur + (tgt - cur) * Math.min(dt * 8, 1);
      liftT.set(o, nv);
      if (Math.abs(nv) > 0.01)
        o.position.y = o.userData.baseY + nv * 0.3 + (ambientOn && !reduced() && o !== hovered ? Math.sin(amb * 0.75 + o.id) * 0.045 : 0);
    });
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
    stats(){
      let tris = 0, objs = 0;
      scene.traverse(o => { if (o.geometry){ objs++; const g = o.geometry; tris += (g.index ? g.index.count : g.attributes.position.count) / 3; }});
      return {triangles: Math.round(tris), objects: objs};
    },
  };
  start();
  return api;
}
