/* R5-lab 方案 A「展卷 · 案头剧场」场景实验
   与 R4 差异:无背景幕/无网格地面,低机位虚空+接触影;
   书页更大更弯、页缘切面描线、朱砂书签垂出页底。 */
import * as THREE from '../r4/3d/three.module.min.js';

export const PARAMS = {
  cam: {fov: 34, r: 16.5, az: 0.46, el: 0.21, azSpan: 0.26, elMin: 0.14, elMax: 0.5, ty: 3.1},
  book: {cx: 2.4, cz: 0.3, w: 4.6, h: 6.4, curve: 0.26,
         spineGap: 0.016, foldStart: -0.72, foldGap: 0.14,
         pages: [
           {ry: -0.60, y: 0.34, glow: false, curve: 0.24},
           {ry: -0.33, y: 0.20, glow: false, curve: 0.27},
           {ry: -0.06, y: 0.10, glow: true,  curve: 0.25},
           {ry:  0.24, y: 0.16, glow: false, curve: 0.28},
           {ry:  0.55, y: 0.27, glow: false, curve: 0.23},
           {ry:  0.88, y: 0.42, glow: false, curve: 0.26},
         ]},
  ghost: {w: 2.4, h: 3.4, x: 6.6, y: 2.2, z: -1.2, ry: -0.7, link: 'digest'},
  entrance: 3.0, sweepAt: 1.15,
};
export const LIGHT = {
  day:   {sky: 0xEFEDE6, fogD: 0.013, hemiS: 0xE8E4D8, hemiG: 0x9A9484, hemiI: 0.85,
          sunC: 0xFFF0D8, sunI: 2.4, sunPos: [9, 14, 6], rimI: 0.0, warmI: 0.0, fillI: 0.35,
          glowI: 0.06, pageEmI: 0.05, shadowI: 0.16},
  night: {sky: 0x0A0D13, fogD: 0.018, hemiS: 0x1A2334, hemiG: 0x05070B, hemiI: 0.5,
          sunC: 0x8FA8D8, sunI: 0.35, sunPos: [-7, 11, -7], rimI: 2.2, warmI: 2.2, fillI: 0.3,
          glowI: 1.0, pageEmI: 0.12, shadowI: 0.5},
};

function rng(seed){ let s = seed >>> 0; return () => (s = s * 1664525 + 1013904223 >>> 0) / 4294967296; }

/* 纸页纹理:更细的纤维 + 不等长行线 + 双线框 + 页码 + 页缘切面暗线 */
function pageTex(seed, {title = false, glow = false} = {}){
  const c = document.createElement('canvas'); c.width = 512; c.height = 712;
  const g = c.getContext('2d'), r = rng(seed);
  g.fillStyle = '#F6F3EA'; g.fillRect(0, 0, 512, 712);
  for (let i = 0; i < 5200; i++){ g.fillStyle = `rgba(96,88,64,${r() * 0.045})`; g.fillRect(r() * 512, r() * 712, 1 + r() * 1.6, 1); }
  for (let i = 0; i < 90; i++){
    g.strokeStyle = `rgba(130,118,90,${0.025 + r() * 0.035})`; g.lineWidth = 0.7;
    const x = r() * 512, y = r() * 712;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + (r() - .5) * 42, y + (r() - .5) * 7); g.stroke();
  }
  /* 双线书框 */
  g.strokeStyle = 'rgba(30,32,38,0.55)'; g.lineWidth = 2; g.strokeRect(30.5, 30.5, 451, 651);
  g.strokeStyle = 'rgba(30,32,38,0.28)'; g.lineWidth = 1; g.strokeRect(38.5, 38.5, 435, 635);
  g.fillStyle = '#17191E';
  let y = 84;
  if (title){
    g.fillRect(56, y, 250, 22); y += 40;
    g.fillRect(56, y, 168, 22); y += 52;
    g.fillStyle = '#C2402A'; g.fillRect(56, y, 34, 6); y += 26;
  }
  g.fillStyle = '#1D1F24';
  while (y < 596){
    const indent = r() > .78 ? 26 : 0;               /* 段首缩进 */
    const w = 300 - indent - r() * 90;
    g.fillStyle = `rgba(29,31,36,${0.42 + r() * 0.25})`;
    g.fillRect(56 + indent, y, w, 5); y += 19;
    if (r() > .45){ g.fillRect(56, y, w * (0.35 + r() * .55), 5); y += 19; }
    if (r() > .82) y += 14;                           /* 段距 */
  }
  g.fillStyle = 'rgba(29,31,36,0.5)'; g.font = '16px monospace'; g.textAlign = 'center';
  g.fillText('— ' + (1 + Math.floor(r() * 9)) + ' —', 256, 652);
  /* 页缘切面:右缘与下缘细暗线,远看像纸的厚度 */
  const eg = g.createLinearGradient(494, 0, 512, 0);
  eg.addColorStop(0, 'rgba(90,80,60,0)'); eg.addColorStop(1, 'rgba(90,80,60,0.4)');
  g.fillStyle = eg; g.fillRect(494, 0, 18, 712);
  const eb = g.createLinearGradient(0, 694, 0, 712);
  eb.addColorStop(0, 'rgba(90,80,60,0)'); eb.addColorStop(1, 'rgba(90,80,60,0.35)');
  g.fillStyle = eb; g.fillRect(0, 694, 512, 18);
  if (glow){                                          /* 发光页:天头一枚朱砂小印 */
    g.fillStyle = '#C2402A'; g.fillRect(430, 52, 26, 26);
    g.fillStyle = '#F6F3EA'; g.font = 'bold 19px serif'; g.fillText('新', 443, 71);
  }
  return new THREE.CanvasTexture(c);
}
/* 接触影:径向暗斑,替代 R4 的网格地面 */
function shadowTex(){
  const c = document.createElement('canvas'); c.width = c.height = 512;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(256, 256, 30, 256, 256, 250);
  grad.addColorStop(0, 'rgba(20,18,14,1)'); grad.addColorStop(0.55, 'rgba(20,18,14,0.5)');
  grad.addColorStop(1, 'rgba(20,18,14,0)');
  g.fillStyle = grad; g.fillRect(0, 0, 512, 512);
  return new THREE.CanvasTexture(c);
}
export function bookPageGeometry(w, h, curve){
  const geo = new THREE.PlaneGeometry(w, h, 44, 1);
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

export function createScene(host, opts = {}){
  const P = PARAMS;
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  const links = Object.assign({post: 'post-hello.html', digest: 'digest.html'}, opts.links || {});

  const renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, innerWidth < 760 ? 1.5 : 2));
  renderer.shadowMap.enabled = innerWidth >= 760;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;touch-action:pan-y;cursor:grab';
  host.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0xEFEDE6, 0.013);
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
    camera.userData.zoom = Math.min(1.9, Math.max(1, 1.15 / Math.max(camera.aspect, 0.01)));
    camera.updateProjectionMatrix();
    placeCam();
  }
  addEventListener('resize', resize);

  const M = {
    seal: new THREE.MeshStandardMaterial({color: 0xC2402A, roughness: 0.45, metalness: 0.12}),
    shadow: new THREE.MeshBasicMaterial({map: shadowTex(), transparent: true, depthWrite: false,
      opacity: 0.16, color: 0x14120E}),
  };
  const root = new THREE.Group(); scene.add(root);
  const track = [];
  function reg(o, t0, t1, kind){ o.userData.ent = {t0, t1, kind, from: {}, to: {}}; track.push(o); }

  /* 书页雕塑:每页曲率微异,页缘描线给厚度错觉 */
  const pageMats = [];
  P.book.pages.forEach((pg, i) => {
    const tex = pageTex(61 + i * 7, {title: i === 0, glow: pg.glow});
    const mat = new THREE.MeshStandardMaterial({map: tex, roughness: 0.86, side: THREE.DoubleSide,
      emissive: pg.glow ? 0xFFE9BE : 0xF7F5EE, emissiveMap: tex, emissiveIntensity: 0.05});
    pageMats.push(mat);
    const mesh = new THREE.Mesh(bookPageGeometry(P.book.w, P.book.h, pg.curve ?? P.book.curve), mat);
    mesh.castShadow = mesh.receiveShadow = true;
    mesh.position.set(P.book.cx - P.book.w / 2, P.book.h / 2 + pg.y, P.book.cz - i * P.book.spineGap);
    mesh.rotation.y = pg.ry;
    if (pg.glow){ mesh.userData.link = links.post; mesh.userData.lift = true; mesh.userData.baseY = mesh.position.y; }
    root.add(mesh);
    mesh.userData.foldAngle = P.book.foldStart + i * P.book.foldGap;
    reg(mesh, 0.55, 2.65, 'unfold');
    if (pg.glow){
      /* 朱砂书签:从页顶夹入,垂出页底 */
      const tab = new THREE.Mesh(new THREE.BoxGeometry(0.34, 4.4, 0.045), M.seal);
      const edge = P.book.w * 0.5, R = P.book.w / (pg.curve ?? P.book.curve);
      tab.position.set(Math.sin(edge / R) * R, P.book.h * 0.5 - 0.9, (1 - Math.cos(edge / R)) * R);
      tab.rotation.y = -edge / R;
      tab.castShadow = true;
      mesh.add(tab);
    }
  });
  /* 虚线页(日报计划) */
  const ghost = dashedFrame(P.ghost.w, P.ghost.h, 0x8A8F99);
  ghost.position.set(P.ghost.x, P.ghost.y, P.ghost.z); ghost.rotation.y = P.ghost.ry;
  ghost.userData.link = links.digest; ghost.userData.lift = true; ghost.userData.baseY = P.ghost.y;
  root.add(ghost);
  reg(ghost, 2.3, 2.8, 'fade');

  /* 虚空接触影(替代地面) */
  const shadowCatcher = new THREE.Mesh(new THREE.PlaneGeometry(26, 26), M.shadow);
  shadowCatcher.rotation.x = -Math.PI / 2; shadowCatcher.position.set(P.book.cx, 0.01, P.book.cz);
  scene.add(shadowCatcher); reg(shadowCatcher, 0, 0.6, 'fade');
  /* 真实投影接收:一片不可见 plane */
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(60, 60), new THREE.ShadowMaterial({opacity: 0.22}));
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);

  /* 灯光 */
  const hemi = new THREE.HemisphereLight(0xE8E4D8, 0x9A9484, 0.85); scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xFFF0D8, 2.4);
  sun.castShadow = renderer.shadowMap.enabled;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = sun.shadow.camera.bottom = -14;
  sun.shadow.camera.right = sun.shadow.camera.top = 14;
  sun.shadow.bias = -0.0004;
  sun.position.set(9, 14, 6);
  scene.add(sun);
  const rim = new THREE.DirectionalLight(0x6E9BFF, 0); rim.position.set(-10, 7, -9); scene.add(rim);
  const fill = new THREE.DirectionalLight(0xC8D2E4, 0.35); fill.position.set(8, 5, 12); scene.add(fill);
  const warm = new THREE.PointLight(0xFFBE6E, 0, 14, 1.8); warm.position.set(1.6, 2.6, 2.2); scene.add(warm);
  const sweep = new THREE.SpotLight(0xFFF6E2, 0, 44, 0.5, 0.6, 1.2);
  sweep.position.set(-14, 13, 9); scene.add(sweep, sweep.target);

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
    warm.intensity = D.warmI + (N.warmI - D.warmI) * t;
    M.shadow.opacity = D.shadowI + (N.shadowI - D.shadowI) * t;
    lerpC(M.seal.emissive, 0x000000, 0x6E2412, t);
    floor.material.opacity = 0.22 + 0.1 * t;
    pageMats.forEach((m, i) => {
      const glow = P.book.pages[i].glow;
      m.emissiveIntensity = glow ? D.glowI + (N.glowI - D.glowI) * t : D.pageEmI + (N.pageEmI - D.pageEmI) * t;
    });
  }

  /* 入场 */
  track.forEach(o => {
    const e = o.userData.ent;
    if (e.kind === 'unfold'){ e.from.ry = o.userData.foldAngle; e.to.ry = o.rotation.y; e.from.y = o.position.y + 1.1; e.to.y = o.position.y; }
    if (e.kind === 'fade'){ e.from.op = 0; e.to.op = o.material.opacity ?? 1; }
  });
  const easeOut = x => 1 - Math.pow(1 - x, 3);
  let entT = -1;
  function playEntrance(){
    entT = 0;
    track.forEach(o => {
      const e = o.userData.ent;
      if (e.kind === 'unfold'){ o.rotation.y = e.from.ry; o.position.y = e.from.y; }
      if (e.kind === 'fade'){ o.material.transparent = true; o.material.opacity = 0; }
    });
    sweep.intensity = 0;
  }
  function finishEntrance(){
    entT = -1; sweep.intensity = 0;
    track.forEach(o => {
      const e = o.userData.ent;
      if (e.kind === 'unfold'){ o.rotation.y = e.to.ry; o.position.y = e.to.y; }
      if (e.kind === 'fade'){ o.material.opacity = e.to.op; }
    });
  }
  function stepEntrance(dt){
    if (entT < 0) return;
    entT += dt;
    track.forEach(o => {
      const e = o.userData.ent, k = easeOut(Math.min(Math.max((entT - e.t0) / (e.t1 - e.t0), 0), 1));
      if (e.kind === 'unfold'){ o.rotation.y = e.from.ry + (e.to.ry - e.from.ry) * k; o.position.y = e.from.y + (e.to.y - e.from.y) * k; }
      if (e.kind === 'fade'){ o.material.opacity = e.to.op * k; }
    });
    const sk = Math.min(Math.max((entT - P.sweepAt) / 1.4, 0), 1);
    sweep.intensity = Math.sin(sk * Math.PI) * 60;
    sweep.target.position.set(-6 + sk * 14, 2, 0);
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
    const hit = ray.intersectObjects(root.children.filter(o => o.userData.link), false)[0];
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
      ghost.rotation.y = PARAMS.ghost.ry + Math.sin(amb * 0.4) * 0.05;
      root.children.forEach(o => {
        if (o.userData.baseY !== undefined && o !== hovered)
          o.position.y = o.userData.baseY + Math.sin(amb * 0.8 + o.id) * 0.05;
      });
    }
    root.children.forEach(o => {
      if (!o.userData.lift) return;
      const cur = liftT.get(o) || 0, tgt = (o === hovered) ? 1 : 0;
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
