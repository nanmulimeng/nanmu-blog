/* ═══════════════════════════════════════════════════════════
   R4 主场景「纸筑」· book.js — 程序化建模源资产
   概念:站是一本正在写的发光的书。实页=文章,发光页=最新,
   虚线页=日报(计划),朱砂书签=当前位置。
   接口:createScene(host, opts) → {setTheme, resetView, start, stop, setAmbient, stats}
   依赖:同目录 three.module.min.js(r180,本地固定)
   ═══════════════════════════════════════════════════════════ */
import * as THREE from './three.module.min.js';

/* ── 参数表(可编辑源;改这里即可重建/调整场景) ── */
export const PARAMS = {
  cam: {fov: 38, r: 18.5, az: 0.52, el: 0.30, azSpan: 0.30, elMin: 0.18, elMax: 0.58, ty: 3.4},
  backdrop: {w: 13, h: 9, curve: 0.35, x: -5.5, z: -5.5, ry: 0.42},
  book: {cx: 1.6, cz: 0.4, w: 4.4, h: 6.2, curve: 0.22,
         spineGap: 0.014, foldStart: -0.62, foldGap: 0.16,
         pages: [
           {ry: -0.55, y: 0.30, glow: false},
           {ry: -0.22, y: 0.18, glow: false},
           {ry:  0.08, y: 0.10, glow: true},
           {ry:  0.40, y: 0.16, glow: false},
           {ry:  0.72, y: 0.26, glow: false},
           {ry:  1.02, y: 0.40, glow: false},
         ]},
  panels: [
    {w: 2.0, h: 2.8, x: -1.2, y: 2.6, z: 2.6, ry: 0.3, lines: 9, title: true, link: 'post'},
    {w: 2.0, h: 2.8, x: 4.6,  y: 3.1, z: 2.2, ry: -0.35, lines: 6, link: 'post'},
  ],
  ghost: {w: 2.6, h: 3.6, x: 6.2, y: 2.0, z: 0.6, ry: -0.8, link: 'digest'},
  groundR: 26,
  entrance: 3.0,      // 入场总时长 s
  sweepAt: 1.2,       // 扫光起点
};
export const LIGHT = {
  day:   {sky: 0xE8EBEF, fogD: 0.016, hemiS: 0xDFE8F2, hemiG: 0x8A8578, hemiI: 0.95,
          sunC: 0xFFF2DC, sunI: 2.6, sunPos: [11, 13, 4], rimI: 0.0, warmI: 0.0, fillI: 0.0,
          sheetEm: 0xF5F3EC, sheetEmI: 0.06, backEmI: 0.0, panelEmI: 0.06, glowI: 0.05, pageEmI: 0.05},
  night: {sky: 0x0B0E14, fogD: 0.020, hemiS: 0x1C2638, hemiG: 0x07090D, hemiI: 0.55,
          sunC: 0x8FA8D8, sunI: 0.5, sunPos: [-8, 10, -6], rimI: 2.4, warmI: 1.6, fillI: 0.5,
          sheetEm: 0x8A7B5E, sheetEmI: 0.07, backEmI: 0.35, panelEmI: 0.14, glowI: 0.9, pageEmI: 0.11},
};

/* ── 确定性随机与纹理 ── */
function rng(seed){ let s = seed >>> 0; return () => (s = s * 1664525 + 1013904223 >>> 0) / 4294967296; }
function paperTex(seed, base = '#F5F3EC'){
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'), r = rng(seed);
  g.fillStyle = base; g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 2400; i++){ g.fillStyle = `rgba(60,55,40,${r() * 0.05})`; g.fillRect(r() * 256, r() * 256, 1 + r() * 1.5, 1); }
  for (let i = 0; i < 60; i++){
    g.strokeStyle = `rgba(120,110,85,${0.03 + r() * 0.04})`; g.lineWidth = 0.6;
    const x = r() * 256, y = r() * 256;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + (r() - .5) * 30, y + (r() - .5) * 6); g.stroke();
  }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; return t;
}
function textTex(seed, lines, title){
  const c = document.createElement('canvas'); c.width = 256; c.height = 348;
  const g = c.getContext('2d'), r = rng(seed);
  g.fillStyle = '#F7F5EE'; g.fillRect(0, 0, 256, 348);
  g.fillStyle = '#1A1C20';
  if (title){ g.fillRect(28, 30, 150, 12); g.fillRect(28, 52, 96, 12); }
  let y = title ? 96 : 36;
  for (let i = 0; i < lines; i++){
    const w = 150 + r() * 60;
    g.fillStyle = `rgba(26,28,32,${0.5 + r() * 0.2})`;
    g.fillRect(28, y, w, 4); y += 16;
    if (r() > .5){ g.fillRect(28, y, w * (0.4 + r() * .5), 4); y += 16; }
  }
  g.strokeStyle = '#C2402A'; g.lineWidth = 2.5; g.strokeRect(8.5, 8.5, 239, 331);
  return new THREE.CanvasTexture(c);
}
function groundTex(seed){
  const c = document.createElement('canvas'); c.width = c.height = 512;
  const g = c.getContext('2d'), r = rng(seed);
  const grad = g.createRadialGradient(256, 256, 40, 256, 256, 256);
  grad.addColorStop(0, '#D9D6CC'); grad.addColorStop(0.75, '#C4C1B6'); grad.addColorStop(1, 'rgba(196,193,182,0)');
  g.fillStyle = grad; g.fillRect(0, 0, 512, 512);
  g.strokeStyle = 'rgba(40,44,52,0.07)'; g.lineWidth = 1;
  for (let i = 0; i <= 16; i++){
    const p = i * 32;
    g.beginPath(); g.moveTo(p, 0); g.lineTo(p, 512); g.stroke();
    g.beginPath(); g.moveTo(0, p); g.lineTo(512, p); g.stroke();
  }
  for (let i = 0; i < 900; i++){ g.fillStyle = `rgba(50,48,40,${r() * 0.06})`; g.fillRect(r() * 512, r() * 512, 1.5, 1.5); }
  return new THREE.CanvasTexture(c);
}
function bentSheet(w, h, curve){
  const geo = new THREE.PlaneGeometry(w, h, 40, 1);
  const pos = geo.attributes.position, R = w / curve;
  for (let i = 0; i < pos.count; i++){
    const x = pos.getX(i), a = x / R;
    pos.setX(i, Math.sin(a) * R);
    pos.setZ(i, (1 - Math.cos(a)) * R);
  }
  geo.computeVertexNormals();
  return geo;
}
export function bookPageGeometry(w, h, curve){
  // Local x=0 is the spine. Centre-pivot planes cut through one another.
  const geo = new THREE.PlaneGeometry(w, h, 40, 1);
  const pos = geo.attributes.position, R = w / curve;
  for (let i = 0; i < pos.count; i++){
    const a = (pos.getX(i) + w / 2) / R;
    pos.setX(i, Math.sin(a) * R);
    pos.setZ(i, (1 - Math.cos(a)) * R);
  }
  geo.computeVertexNormals();
  return geo;
}
function dashedFrame(w, h, color){
  const lines = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.PlaneGeometry(w, h)),
    new THREE.LineDashedMaterial({color, dashSize: 0.16, gapSize: 0.12, transparent: true}));
  lines.computeLineDistances();
  return lines;
}

/* ═══ 主工厂 ═══ */
export function createScene(host, opts = {}){
  const P = PARAMS;
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  const links = Object.assign({post: 'posts.html', digest: 'digest.html'}, opts.links || {});

  const renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, innerWidth < 760 ? 1.5 : 2));
  renderer.shadowMap.enabled = innerWidth >= 760;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;touch-action:pan-y;cursor:grab';
  host.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0xE8EBEF, 0.016);
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
    /* 竖屏构图:横向视角不足时按比例拉远,保住书页组与虚线页完整 */
    camera.userData.zoom = Math.min(1.9, Math.max(1, 1.2 / Math.max(camera.aspect, 0.01)));
    camera.updateProjectionMatrix();
    placeCam();
  }
  addEventListener('resize', resize);

  /* ── 材质 ── */
  const M = {
    paper: new THREE.MeshStandardMaterial({map: paperTex(11), roughness: 0.92, side: THREE.FrontSide}),
    backing: new THREE.MeshStandardMaterial({color: 0xC4CAD2, roughness: 0.88, metalness: 0.05, side: THREE.BackSide}),
    seal: new THREE.MeshStandardMaterial({color: 0xC2402A, roughness: 0.5, metalness: 0.1}),
    ground: new THREE.MeshStandardMaterial({map: groundTex(7), roughness: 0.96, transparent: true}),
  };
  const root = new THREE.Group(); scene.add(root);
  const track = [];
  function reg(o, t0, t1, kind){ o.userData.ent = {t0, t1, kind, from: {}, to: {}}; track.push(o); }

  /* 背景弧幕 */
  {
    const s = P.backdrop, grp = new THREE.Group(), geo = bentSheet(s.w, s.h, s.curve);
    const front = new THREE.Mesh(geo, M.paper); front.receiveShadow = true; front.position.y = s.h / 2;
    const back = new THREE.Mesh(geo, M.backing); back.position.y = s.h / 2;
    grp.add(front, back);
    grp.position.set(s.x, 0, s.z); grp.rotation.y = s.ry;
    root.add(grp); reg(grp, 0.15, 1.0, 'rise');
  }
  /* 书页雕塑 */
  const pageMats = [];
  P.book.pages.forEach((pg, i) => {
    const tex = textTex(61 + i, 11, pg.glow);
    const mat = new THREE.MeshStandardMaterial({map: tex, roughness: 0.88, side: THREE.DoubleSide,
      emissive: pg.glow ? 0xFFE9BE : 0xF7F5EE, emissiveMap: tex, emissiveIntensity: 0.05});
    pageMats.push(mat);
    const mesh = new THREE.Mesh(bookPageGeometry(P.book.w, P.book.h, P.book.curve), mat);
    mesh.castShadow = mesh.receiveShadow = true;
    mesh.position.set(P.book.cx - P.book.w / 2, P.book.h / 2 + pg.y, P.book.cz - i * P.book.spineGap);
    mesh.rotation.y = pg.ry;
    if (pg.glow){ mesh.userData.link = links.post; mesh.userData.lift = true; }
    root.add(mesh);
    // One shared unfold progress preserves angular ordering throughout entry.
    mesh.userData.foldAngle = P.book.foldStart + i * P.book.foldGap;
    reg(mesh, 0.55, 2.65, 'unfold');
    if (pg.glow){
      const tab = new THREE.Mesh(new THREE.BoxGeometry(0.05, 1.0, 0.42), M.seal);
      const edge = P.book.w * 0.93, R = P.book.w / P.book.curve;
      tab.position.set(Math.sin(edge / R) * R, P.book.h * 0.48, (1 - Math.cos(edge / R)) * R);
      tab.rotation.y = -edge / R;
      mesh.add(tab);
    }
  });
  /* 浮页(文章入口) */
  const panelMats = [], clickable = [];
  P.panels.forEach((p, i) => {
    const tex = textTex(31 + i, p.lines, p.title);
    const mat = new THREE.MeshStandardMaterial({map: tex, roughness: 0.85, side: THREE.DoubleSide,
      emissive: 0xF7F5EE, emissiveMap: tex, emissiveIntensity: 0.06});
    panelMats.push(mat);
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(p.w, p.h), mat);
    mesh.castShadow = true;
    mesh.position.set(p.x, p.y, p.z); mesh.rotation.y = p.ry;
    mesh.userData.link = links[p.link] || links.post; mesh.userData.lift = true; mesh.userData.baseY = p.y;
    root.add(mesh); clickable.push(mesh);
    reg(mesh, 1.9 + i * 0.22, 2.5 + i * 0.22, 'drop');
  });
  /* 虚线页(日报计划) */
  const ghost = dashedFrame(P.ghost.w, P.ghost.h, 0x8A8F99);
  ghost.position.set(P.ghost.x, P.ghost.y, P.ghost.z); ghost.rotation.y = P.ghost.ry;
  ghost.userData.link = links.digest; ghost.userData.lift = true; ghost.userData.baseY = P.ghost.y;
  root.add(ghost); clickable.push(ghost);
  reg(ghost, 2.3, 2.8, 'fade');
  /* 地面 */
  const ground = new THREE.Mesh(new THREE.CircleGeometry(P.groundR, 64), M.ground);
  ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true;
  scene.add(ground); reg(ground, 0, 0.5, 'fade');

  /* ── 灯光 ── */
  const hemi = new THREE.HemisphereLight(0xDFE8F2, 0x8A8578, 0.95); scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xFFF2DC, 2.6);
  sun.castShadow = renderer.shadowMap.enabled;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = sun.shadow.camera.bottom = -16;
  sun.shadow.camera.right = sun.shadow.camera.top = 16;
  sun.shadow.bias = -0.0004;
  scene.add(sun);
  const rim = new THREE.DirectionalLight(0x6E9BFF, 0); rim.position.set(-10, 6, -8); scene.add(rim);
  const fill = new THREE.DirectionalLight(0x93A8CC, 0); fill.position.set(9, 5, 12); scene.add(fill);
  const warm = new THREE.PointLight(0xFFBE6E, 0, 12, 1.8); warm.position.set(0.4, 2.2, 1.4); scene.add(warm);
  const sweep = new THREE.SpotLight(0xFFF6E2, 0, 40, 0.5, 0.6, 1.2);
  sweep.position.set(-14, 12, 8); scene.add(sweep, sweep.target);

  /* ── 主题 ── */
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
    warm.intensity = D.warmI + (N.warmI - D.warmI) * t;
    lerpC(M.paper.emissive, D.sheetEm, N.sheetEm, t);
    M.paper.emissiveIntensity = D.sheetEmI + (N.sheetEmI - D.sheetEmI) * t;
    lerpC(M.backing.emissive, 0x000000, 0x22304A, t);
    M.backing.emissiveIntensity = D.backEmI + (N.backEmI - D.backEmI) * t;
    /* 朱砂书签夜间不沉成黑色:极弱暖红自发光,只保可读,不当光源 */
    lerpC(M.seal.emissive, 0x000000, 0x6E2412, t);
    pageMats.forEach((m, i) => {
      const glow = P.book.pages[i].glow;
      m.emissiveIntensity = glow ? D.glowI + (N.glowI - D.glowI) * t : D.pageEmI + (N.pageEmI - D.pageEmI) * t;
    });
    panelMats.forEach(m => { m.emissiveIntensity = D.panelEmI + (N.panelEmI - D.panelEmI) * t; });
  }

  /* ── 入场 ── */
  track.forEach(o => {
    const e = o.userData.ent;
    if (e.kind === 'rise'){ e.from.y = -4.5; e.to.y = o.position.y; e.from.rz = 0.5; }
    if (e.kind === 'unfold'){ e.from.ry = o.userData.foldAngle; e.to.ry = o.rotation.y; e.from.y = o.position.y + 1.2; e.to.y = o.position.y; }
    if (e.kind === 'drop'){ e.from.y = o.position.y + 5; e.to.y = o.position.y; }
    if (e.kind === 'fade'){ e.from.op = 0; e.to.op = o.material.opacity ?? 1; }
  });
  const easeOut = x => 1 - Math.pow(1 - x, 3);
  let entT = -1;
  function playEntrance(){
    entT = 0;
    track.forEach(o => {
      const e = o.userData.ent;
      if (e.kind === 'rise'){ o.position.y = e.from.y; o.rotation.z = e.from.rz; }
      if (e.kind === 'unfold'){ o.rotation.y = e.from.ry; o.position.y = e.from.y; }
      if (e.kind === 'drop'){ o.position.y = e.from.y; }
      // Solid sheets remain in the opaque depth-tested pass; only fades need alpha.
      if (e.kind === 'fade'){ o.material.transparent = true; o.material.opacity = 0; }
    });
    sweep.intensity = 0;
  }
  function finishEntrance(){
    entT = -1; sweep.intensity = 0;
    track.forEach(o => {
      const e = o.userData.ent;
      if (e.kind === 'rise'){ o.position.y = e.to.y; o.rotation.z = 0; }
      if (e.kind === 'unfold'){ o.rotation.y = e.to.ry; o.position.y = e.to.y; }
      if (e.kind === 'drop'){ o.position.y = e.to.y; }
      if (e.kind === 'fade'){ o.material.opacity = e.to.op; }
    });
  }
  function stepEntrance(dt){
    if (entT < 0) return;
    entT += dt;
    track.forEach(o => {
      const e = o.userData.ent, k = easeOut(Math.min(Math.max((entT - e.t0) / (e.t1 - e.t0), 0), 1));
      if (e.kind === 'rise'){ o.position.y = e.from.y + (e.to.y - e.from.y) * k; o.rotation.z = e.from.rz * (1 - k); }
      if (e.kind === 'unfold'){ o.rotation.y = e.from.ry + (e.to.ry - e.from.ry) * k; o.position.y = e.from.y + (e.to.y - e.from.y) * k; }
      if (e.kind === 'drop'){ o.position.y = e.from.y + (e.to.y - e.from.y) * k; }
      if (e.kind === 'fade'){ o.material.opacity = e.to.op * k; }
    });
    const sk = Math.min(Math.max((entT - P.sweepAt) / 1.4, 0), 1);
    sweep.intensity = Math.sin(sk * Math.PI) * 60;
    sweep.target.position.set(-6 + sk * 14, 2, 0);
    if (entT > P.entrance + 0.4) finishEntrance();
  }

  /* ── 交互 ── */
  const ray = new THREE.Raycaster(), ptr = new THREE.Vector2();
  let dragging = false, moved = 0, px = 0, py = 0, hovered = null, liftT = new Map();
  const el2 = renderer.domElement;
  function pick(e){
    const r = el2.getBoundingClientRect();
    ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, camera);
    const hit = ray.intersectObjects(clickable.concat(root.children.filter(o => o.userData.link)), false)[0];
    return hit ? hit.object : null;
  }
  el2.addEventListener('pointerdown', e => { dragging = true; moved = 0; px = e.clientX; py = e.clientY; });
  el2.addEventListener('pointermove', e => {
    if (dragging){
      moved += Math.abs(e.clientX - px) + Math.abs(e.clientY - py);
      az = Math.min(Math.max(az - (e.clientX - px) * 0.0032, P.cam.az - P.cam.azSpan), P.cam.az + P.cam.azSpan);
      el = Math.min(Math.max(el + (e.clientY - py) * 0.0026, P.cam.elMin), P.cam.elMax);
      px = e.clientX; py = e.clientY;
    } else {
      hovered = pick(e);
      el2.style.cursor = hovered ? 'pointer' : 'grab';
    }
  });
  el2.addEventListener('pointerup', e => {
    dragging = false;
    if (moved < 6){
      const hit = pick(e);
      if (hit && hit.userData.link) location.href = hit.userData.link;
    }
  });
  el2.addEventListener('pointerleave', () => { hovered = null; });

  /* ── 循环管理:按需渲染 ── */
  let running = false, ambientOn = true, inView = true, pageVisible = !document.hidden, amb = 0;
  const clock = new THREE.Clock();
  function needsLoop(){
    if (reduced()) return entT >= 0;               // reduced:仅入场需要(实际直接跳完成态)
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
      root.children.forEach(o => {
        if (o.userData.baseY !== undefined && o !== hovered)
          o.position.y = o.userData.baseY + Math.sin(amb * 0.8 + o.id) * 0.05;
      });
      ghost.rotation.y = PARAMS.ghost.ry + Math.sin(amb * 0.4) * 0.05;
    }
    /* 悬停抬升 */
    clickable.forEach(o => {
      const cur = liftT.get(o) || 0;
      const tgt = (o === hovered) ? 1 : 0;
      const nv = cur + (tgt - cur) * Math.min(dt * 8, 1);
      liftT.set(o, nv);
      if (o.userData.baseY !== undefined && Math.abs(nv) > 0.01)
        o.position.y = o.userData.baseY + nv * 0.35 + (ambientOn && !reduced() && o !== hovered ? Math.sin(amb * 0.8 + o.id) * 0.05 : 0);
    });
    placeCam();
    renderer.render(scene, camera);
    if (!needsLoop()){ running = false; renderer.setAnimationLoop(null); }
  }
  function start(){ if (!running){ running = true; clock.getDelta(); renderer.setAnimationLoop(tick); } }
  function stop(){ running = false; renderer.setAnimationLoop(null); }
  function renderOnce(){ applyTheme(themeT); placeCam(); renderer.render(scene, camera); }

  /* 离屏/隐藏暂停 */
  if ('IntersectionObserver' in window)
    new IntersectionObserver(en => { inView = en[0].isIntersecting; if (inView) start(); }, {threshold: 0.05}).observe(host);
  document.addEventListener('visibilitychange', () => { pageVisible = !document.hidden; if (pageVisible) start(); });

  /* ── 初始化 ── */
  resize(); placeCam();
  if (reduced()){ finishEntrance(); } else { playEntrance(); }
  applyTheme(0);

  const api = {
    /* 修复(reduced-motion 缺口):任何主题变化都立即 applyTheme+renderOnce,
       不依赖渲染循环;非 reduced 时再叠加过渡动画 */
    setTheme(dark, immediate){
      themeTarget = dark ? 1 : 0;
      if (immediate || reduced()){
        themeT = themeTarget; applyTheme(themeT); renderOnce();
      } else start();
    },
    resetView(){
      az = PARAMS.cam.az; el = PARAMS.cam.el;
      if (reduced()) renderOnce(); else start();
    },
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
