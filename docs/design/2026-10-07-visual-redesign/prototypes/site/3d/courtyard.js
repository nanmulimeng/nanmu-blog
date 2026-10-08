/* ═══════════════════════════════════════════════════════════
   nanmu-blog 3D 小院 · 确定性程序化建模脚本 + 场景运行时(R3)
   ─────────────────────────────────────────────────────────
   本文件即 3D 源资产:所有几何由参数生成,无外部模型/贴图;
   纸面纹理由内置种子随机在运行时绘制(确定性)。
   依赖:同目录 three.module.min.js(r180,MIT)。
   复建方式:python -m http.server 后打开 scene.html 或首页。
   调整入口:PARAMS 常量表(尺寸/镜头/灯光/配色/动效时长)。
   ═══════════════════════════════════════════════════════════ */
import * as THREE from './three.module.min.js';

/* ── 参数表:尺寸(米制意象) ── */
export const PARAMS = {
  ground: { w: 24, d: 20 },
  hall:   { x: -2.2, z: -0.6, plinth: [7.0, 0.5, 5.8], wall: [6.0, 2.4, 4.6],
            roofLen: 7.4, roofHalf: 3.1, roofH: 1.5,
            door: [-4.4, 1.55, 1.71], doorSize: [0.9, 2.1],
            winLit: [-1.1, 1.55, 1.71], winLitSize: [1.15, 0.95],
            winDark: [0.81, 1.55, -0.6], winDarkSize: [1.0, 0.85] },
  wing:   { x: 4.6, z: 1.6, size: [3.0, 1.9, 3.5] },   // 虚线线框=在建
  plot:   { x: -6.2, z: 4.4, size: 3.4 },              // 点线地界=规划
  tree:   { x: 2.0, z: 5.6 },
  stones: [[-4.9, 3.0], [-4.1, 3.9], [-3.2, 4.7]],
  camera: { target: [-0.4, 1.0, 0.8], radius: 17, az: 0.64, el: 0.56, fov: 36,
            azRange: 0.24, elRange: [0.42, 0.72] },     // 有限角度
  anim:   { groundIn: .5, riseStagger: .22, riseDur: .8, roofDur: .7,
            wireIn: .6, lampDelay: .3, lampDur: 1.0, settle: .2 },
};

/* ── 昼夜灯光参数(插值过渡) ── */
const LIGHT = {
  day:   { bg: 0xF4EEE0, hemiSky: 0xEFE6CF, hemiGround: 0xC9BFA4, hemiI: 0.95,
           sun: 0xFFF3D9, sunI: 2.0, sunPos: [8, 12, 6],
           lampI: 0.0, lampEmissive: 0.25, spot: 0.10, moonI: 0 },
  night: { bg: 0x171916, hemiSky: 0x3A4034, hemiGround: 0x1C1E18, hemiI: 0.85,
           sun: 0x93A7CC, sunI: 0.6, sunPos: [-5, 9, 7],
           lampI: 14.0, lampEmissive: 2.4, spot: 0.5, moonI: 0.22 },
};

/* 确定性伪随机(纹理用,保证可复现) */
function seeded(seed){ let s = seed >>> 0;
  return () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296; }

function paperTexture(hex, seed){
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d');
  g.fillStyle = hex; g.fillRect(0, 0, 256, 256);
  const rnd = seeded(seed);
  for (let i = 0; i < 2600; i++){
    g.fillStyle = `rgba(${rnd() > .5 ? '60,50,30' : '255,252,240'},${(rnd() * .05).toFixed(3)})`;
    g.fillRect(rnd() * 256, rnd() * 256, 1 + rnd() * 1.6, 1 + rnd() * 1.6);
  }
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/* 三棱柱(屋顶):三角形截面沿 x 挤出 */
function gablePrism(len, half, h){
  const s = new THREE.Shape();
  s.moveTo(-half, 0); s.lineTo(half, 0); s.lineTo(0, h); s.closePath();
  const geo = new THREE.ExtrudeGeometry(s, { depth: len, bevelEnabled: false });
  geo.rotateY(Math.PI / 2);                       // 挤出轴 z → x(x ∈ [0,len])
  geo.translate(-len / 2, 0, 0);                  // 居中
  geo.computeVertexNormals();
  return geo;
}

/* 虚线线框盒(在建东厢) */
function dashedBox(w, h, d, color, dash = .32, gap = .22){
  const geo = new THREE.EdgesGeometry(new THREE.BoxGeometry(w, h, d));
  const mat = new THREE.LineDashedMaterial({ color, dashSize: dash, gapSize: gap });
  const lines = new THREE.LineSegments(geo, mat);
  lines.computeLineDistances();
  return lines;
}

export function createCourtyard(container, opts = {}){
  const P = PARAMS;
  const reduced = opts.reducedMotion ?? matchMedia('(prefers-reduced-motion: reduce)').matches;
  const lowPower = opts.lowPower ?? (innerWidth < 700);

  /* renderer / scene / camera */
  const renderer = new THREE.WebGLRenderer({ antialias: !lowPower, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(devicePixelRatio, lowPower ? 1.5 : 2));
  renderer.shadowMap.enabled = !lowPower;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.domElement.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;display:block;touch-action:pan-y;cursor:grab';
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(P.camera.fov, 1, .1, 100);

  /* 材质(纸感,粗糙无金属) */
  const texGround = paperTexture('#EFE7D2', 7);  texGround.repeat.set(6, 5);
  const texWall   = paperTexture('#F6F0E0', 21); texWall.repeat.set(2, 1.4);
  const M = {
    ground: new THREE.MeshStandardMaterial({ map: texGround, roughness: 1 }),
    plinth: new THREE.MeshStandardMaterial({ color: 0xE6DCC2, roughness: .95 }),
    wall:   new THREE.MeshStandardMaterial({ map: texWall, roughness: .95 }),
    roof:   new THREE.MeshStandardMaterial({ color: 0x8A7A5E, roughness: .9, flatShading: true }),
    wood:   new THREE.MeshStandardMaterial({ color: 0x5C4630, roughness: .85 }),
    ink:    new THREE.MeshStandardMaterial({ color: 0x3A332A, roughness: .9 }),
    lamp:   new THREE.MeshStandardMaterial({ color: 0xE9B45B, emissive: 0xE9B45B,
              emissiveIntensity: LIGHT.day.lampEmissive, roughness: .6 }),
    leaf:   new THREE.MeshStandardMaterial({ color: 0x8A9271, roughness: 1, flatShading: true }),
    seal:   new THREE.MeshStandardMaterial({ color: 0xB23A26, roughness: .8 }),
    stone:  new THREE.MeshStandardMaterial({ color: 0xD8CEB4, roughness: 1, flatShading: true }),
  };

  const root = new THREE.Group(); scene.add(root);
  const track = [];   // 入场动画登记 {obj, kind, t0, dur, from...}

  /* 地面 + 网格线 */
  const ground = new THREE.Mesh(new THREE.BoxGeometry(P.ground.w, .5, P.ground.d), M.ground);
  ground.position.y = -.25; ground.receiveShadow = true; root.add(ground);
  track.push({ obj: ground, kind: 'fade', t0: 0, dur: P.anim.groundIn });
  const gridMat = new THREE.LineBasicMaterial({ color: 0xC7BC9E, transparent: true, opacity: .5 });
  const gridPts = [];
  for (let i = -5; i <= 5; i++){ gridPts.push(new THREE.Vector3(i * 2.2, .01, -P.ground.d/2), new THREE.Vector3(i * 2.2, .01, P.ground.d/2)); }
  for (let j = -4; j <= 4; j++){ gridPts.push(new THREE.Vector3(-P.ground.w/2, .01, j * 2.2), new THREE.Vector3(P.ground.w/2, .01, j * 2.2)); }
  const grid = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(gridPts), gridMat);
  root.add(grid); track.push({ obj: grid, kind: 'fade', t0: .1, dur: .5 });

  /* ── 正房 ── */
  const hall = new THREE.Group(); hall.position.set(P.hall.x, 0, P.hall.z);
  hall.userData = { link: 'posts.html', name: '正房 · 文章' };
  const [pw, ph, pd] = P.hall.plinth, [ww, wh, wd] = P.hall.wall;
  const plinth = new THREE.Mesh(new THREE.BoxGeometry(pw, ph, pd), M.plinth);
  plinth.position.y = ph / 2; plinth.castShadow = plinth.receiveShadow = true;
  const walls = new THREE.Mesh(new THREE.BoxGeometry(ww, wh, wd), M.wall);
  walls.position.y = ph + wh / 2; walls.castShadow = walls.receiveShadow = true;
  const roof = new THREE.Mesh(gablePrism(P.hall.roofLen, P.hall.roofHalf, P.hall.roofH), M.roof);
  roof.position.y = ph + wh; roof.castShadow = true;
  /* 门(凹色块 + 门框) */
  const door = new THREE.Mesh(new THREE.BoxGeometry(...P.hall.doorSize.map(v=>v), .06), M.wood);
  door.position.set(P.hall.door[0] - P.hall.x, P.hall.door[1], wd / 2 + .03);
  /* 亮窗(带窗棂) */
  const winLit = new THREE.Mesh(new THREE.BoxGeometry(P.hall.winLitSize[0], P.hall.winLitSize[1], .05), M.lamp);
  winLit.position.set(P.hall.winLit[0] - P.hall.x, P.hall.winLit[1], wd / 2 + .03);
  const muntin1 = new THREE.Mesh(new THREE.BoxGeometry(.045, P.hall.winLitSize[1], .02), M.ink);
  muntin1.position.copy(winLit.position).z += .04;
  const muntin2 = new THREE.Mesh(new THREE.BoxGeometry(P.hall.winLitSize[0], .045, .02), M.ink);
  muntin2.position.copy(muntin1.position);
  /* 暗窗(山墙侧) */
  const winDark = new THREE.Mesh(new THREE.BoxGeometry(.05, P.hall.winDarkSize[1], P.hall.winDarkSize[0]), M.ink);
  winDark.position.set(ww / 2 + .03, P.hall.winDark[1], P.hall.winDark[2] - P.hall.z);
  hall.add(plinth, walls, roof, door, winLit, muntin1, muntin2, winDark);
  root.add(hall);
  [plinth, walls].forEach((o, i) => track.push({ obj: o, kind: 'rise', t0: .45 + i * P.anim.riseStagger, dur: P.anim.riseDur }));
  track.push({ obj: roof, kind: 'drop', t0: .45 + 2 * P.anim.riseStagger, dur: P.anim.roofDur });
  [door, winLit, muntin1, muntin2, winDark].forEach(o => track.push({ obj: o, kind: 'fade', t0: 1.15, dur: .4 }));

  /* ── 东厢:虚线线框 + 脚手架 ── */
  const wing = new THREE.Group(); wing.position.set(P.wing.x, 0, P.wing.z);
  wing.userData = { link: 'digest.html', name: '东厢 · AI 日报(在建)' };
  const [vw, vh, vd] = P.wing.size;
  const frame = dashedBox(vw, vh, vd, 0x8A8270); frame.position.y = vh / 2;
  const base = dashedBox(vw + .3, .02, vd + .3, 0x8A8270, .2, .16); base.position.y = .01;
  /* 脚手架:两组斜撑 */
  const scafMat = new THREE.LineDashedMaterial({ color: 0x8A8270, dashSize: .1, gapSize: .14 });
  const scafPts = [
    new THREE.Vector3(-vw/2, 0, vd/2+.02), new THREE.Vector3(vw/2, vh, vd/2+.02),
    new THREE.Vector3(vw/2, 0, vd/2+.02), new THREE.Vector3(-vw/2, vh, vd/2+.02),
    new THREE.Vector3(vw/2+.02, 0, -vd/2), new THREE.Vector3(vw/2+.02, vh, vd/2),
    new THREE.Vector3(vw/2+.02, 0, vd/2), new THREE.Vector3(vw/2+.02, vh, -vd/2),
  ];
  const scaf = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(scafPts), scafMat);
  scaf.computeLineDistances();
  wing.add(frame, base, scaf); root.add(wing);
  [frame, base, scaf].forEach((o, i) => track.push({ obj: o, kind: 'fade', t0: 1.25 + i * .12, dur: P.anim.wireIn }));

  /* ── 留白:点线地界 + 界桩 + 小旗 ── */
  const plot = new THREE.Group(); plot.position.set(P.plot.x, 0, P.plot.z);
  plot.userData = { link: 'about.html#plan', name: '留白 · 检索(规划中)' };
  const ps = P.plot.size;
  const plotLine = dashedBox(ps, .02, ps, 0x8A8270, .12, .2); plotLine.position.y = .01;
  plot.add(plotLine);
  [[-ps/2,-ps/2],[ps/2,-ps/2],[ps/2,ps/2],[-ps/2,ps/2]].forEach(([sx, sz]) => {
    const stake = new THREE.Mesh(new THREE.CylinderGeometry(.035, .045, .5, 6), M.wood);
    stake.position.set(sx, .25, sz); stake.castShadow = true; plot.add(stake);
  });
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(.025, .03, 1.1, 6), M.wood);
  pole.position.set(ps/2, .55, ps/2); plot.add(pole);
  const flag = new THREE.Mesh(new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(0, 0, 0), new THREE.Vector3(.62, -.14, 0), new THREE.Vector3(0, -.3, 0),
  ]), new THREE.MeshBasicMaterial({ color: 0xB23A26, side: THREE.DoubleSide }));
  flag.geometry.setIndex([0, 1, 2]); flag.geometry.computeVertexNormals();
  flag.position.set(ps/2, 1.06, ps/2); plot.add(flag);
  root.add(plot);
  track.push({ obj: plot, kind: 'fade', t0: 1.45, dur: .5 });

  /* ── 汀步石 ── */
  P.stones.forEach(([sx, sz], i) => {
    const st = new THREE.Mesh(new THREE.CylinderGeometry(.42, .46, .09, 7), M.stone);
    st.position.set(sx, .05, sz); st.rotation.y = i * .7; st.receiveShadow = st.castShadow = true;
    root.add(st); track.push({ obj: st, kind: 'fade', t0: 1.3 + i * .08, dur: .35 });
  });

  /* ── 树 ── */
  const tree = new THREE.Group(); tree.position.set(P.tree.x, 0, P.tree.z);
  const trunk = new THREE.Mesh(new THREE.CylinderGeometry(.09, .14, 1.6, 7), M.wood);
  trunk.position.y = .8; trunk.castShadow = true;
  const crown = new THREE.Group();
  [[0, 1.95, 0, .62], [-.5, 1.6, .18, .42], [.48, 1.66, -.14, .38]].forEach(([x, y, z, r]) => {
    const b = new THREE.Mesh(new THREE.IcosahedronGeometry(r, 1), M.leaf);
    b.position.set(x, y, z); b.castShadow = true; crown.add(b);
  });
  tree.add(trunk, crown); root.add(tree);
  track.push({ obj: tree, kind: 'rise', t0: 1.5, dur: .6 });

  /* ── 灯光 ── */
  const hemi = new THREE.HemisphereLight(LIGHT.day.hemiSky, LIGHT.day.hemiGround, LIGHT.day.hemiI);
  const sun = new THREE.DirectionalLight(LIGHT.day.sun, LIGHT.day.sunI);
  sun.position.set(...LIGHT.day.sunPos);
  sun.castShadow = !lowPower;
  sun.shadow.mapSize.set(1024, 1024);
  sun.shadow.camera.left = sun.shadow.camera.bottom = -14;
  sun.shadow.camera.right = sun.shadow.camera.top = 14;
  sun.shadow.bias = -.0004;
  const lamp = new THREE.PointLight(0xF2BE63, 0, 9, 1.8);
  lamp.position.set(P.hall.winLit[0], P.hall.winLit[1], P.hall.z + 2.0);
  /* 窗前光斑(地面) */
  const spotTex = (() => {
    const c = document.createElement('canvas'); c.width = c.height = 128;
    const g = c.getContext('2d');
    const rg = g.createRadialGradient(64, 64, 4, 64, 64, 62);
    rg.addColorStop(0, 'rgba(242,190,99,.9)'); rg.addColorStop(1, 'rgba(242,190,99,0)');
    g.fillStyle = rg; g.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(c);
  })();
  const spot = new THREE.Mesh(new THREE.PlaneGeometry(4.6, 2.6),
    new THREE.MeshBasicMaterial({ map: spotTex, transparent: true, opacity: 0,
      depthWrite: false, blending: THREE.AdditiveBlending }));
  spot.rotation.x = -Math.PI / 2; spot.rotation.z = .12;
  spot.position.set(P.hall.winLit[0], .02, P.hall.z + 3.4);
  scene.add(hemi, sun, lamp, spot);

  /* ── 主题(昼/夜)过渡 ── */
  let themeT = 0;           // 0=昼 1=夜
  let themeTarget = 0;
  function setTheme(dark, instant){
    themeTarget = dark ? 1 : 0;
    if (instant || reduced) themeT = themeTarget;
  }
  const cA = new THREE.Color(), cB = new THREE.Color();
  function applyTheme(t){
    cA.setHex(LIGHT.day.bg); cB.setHex(LIGHT.night.bg);
    scene.background = cA.clone().lerp(cB, t);
    hemi.color.setHex(LIGHT.day.hemiSky).lerp(cB.setHex(LIGHT.night.hemiSky), t);
    hemi.groundColor.setHex(LIGHT.day.hemiGround).lerp(cB.setHex(LIGHT.night.hemiGround), t);
    hemi.intensity = THREE.MathUtils.lerp(LIGHT.day.hemiI, LIGHT.night.hemiI, t);
    sun.color.setHex(LIGHT.day.sun).lerp(cB.setHex(LIGHT.night.sun), t);
    sun.intensity = THREE.MathUtils.lerp(LIGHT.day.sunI, LIGHT.night.sunI, t);
    sun.position.set(
      THREE.MathUtils.lerp(LIGHT.day.sunPos[0], LIGHT.night.sunPos[0], t),
      THREE.MathUtils.lerp(LIGHT.day.sunPos[1], LIGHT.night.sunPos[1], t),
      THREE.MathUtils.lerp(LIGHT.day.sunPos[2], LIGHT.night.sunPos[2], t));
    lamp.intensity = THREE.MathUtils.lerp(LIGHT.day.lampI, LIGHT.night.lampI, t);
    spot.material.opacity = THREE.MathUtils.lerp(LIGHT.day.spot, LIGHT.night.spot, t);
    M.lamp.emissiveIntensity = THREE.MathUtils.lerp(LIGHT.day.lampEmissive, LIGHT.night.lampEmissive, t);
    M.ground.color.setScalar(1).lerp(cB.setHex(0x3d4038), t * .82);
    M.wall.color.setScalar(1).lerp(cB.setHex(0x4a4f45), t * .8);
    M.plinth.color.setHex(0xE6DCC2).lerp(cB.setHex(0x3a3e35), t * .85);
    M.roof.color.setHex(0x8A7A5E).lerp(cB.setHex(0x3A3E33), t * .9);
    M.leaf.color.setHex(0x8A9271).lerp(cB.setHex(0x454b3c), t * .85);
    M.stone.color.setHex(0xD8CEB4).lerp(cB.setHex(0x464a40), t * .85);
    gridMat.color.setHex(0xC7BC9E).lerp(cB.setHex(0x3a3f34), t);
  }
  applyTheme(0);

  /* ── 镜头:固定主镜头 + 有限拖拽 ── */
  let az = P.camera.az, el = P.camera.el;
  const target = new THREE.Vector3(...P.camera.target);
  function placeCam(){
    cam.position.set(
      target.x + P.camera.radius * Math.cos(el) * Math.sin(az),
      target.y + P.camera.radius * Math.sin(el),
      target.z + P.camera.radius * Math.cos(el) * Math.cos(az));
    cam.lookAt(target);
  }
  placeCam();
  let dragging = false, px = 0, py = 0, moved = 0;
  const elC = P.camera.elRange;
  container.addEventListener('pointerdown', e => { dragging = true; moved = 0; px = e.clientX; py = e.clientY; container.setPointerCapture(e.pointerId); });
  container.addEventListener('pointermove', e => {
    if (dragging){
      const dx = e.clientX - px, dy = e.clientY - py; px = e.clientX; py = e.clientY;
      moved += Math.abs(dx) + Math.abs(dy);
      az = THREE.MathUtils.clamp(az - dx * .0035, P.camera.az - P.camera.azRange, P.camera.az + P.camera.azRange);
      el = THREE.MathUtils.clamp(el + dy * .0025, elC[0], elC[1]);
      placeCam(); if (reduced) renderOnce();
    } else { hoverPick(e); }
  });
  addEventListener('pointerup', () => { dragging = false; });
  function resetView(){ az = P.camera.az; el = P.camera.el; placeCam(); if (reduced) renderOnce(); }

  /* ── 房间拾取:悬停抬升 / 点击进栏目 ── */
  const ray = new THREE.Raycaster(); const ptr = new THREE.Vector2();
  const pickables = [hall, wing, plot];
  let hovered = null;
  function pick(e){
    const r = container.getBoundingClientRect();
    ptr.x = ((e.clientX - r.left) / r.width) * 2 - 1;
    ptr.y = -((e.clientY - r.top) / r.height) * 2 + 1;
    ray.setFromCamera(ptr, cam);
    const hit = ray.intersectObjects(pickables, true)[0];
    let g = hit ? hit.object : null;
    while (g && !g.userData.link) g = g.parent;
    return g;
  }
  function hoverPick(e){
    const g = pick(e);
    if (g !== hovered){
      if (hovered) hovered.userData.lift = 0;
      hovered = g;
      if (hovered) hovered.userData.lift = 1;
      container.style.cursor = g ? 'pointer' : 'grab';
      if (reduced) renderOnce();
    }
  }
  container.addEventListener('click', e => {
    if (moved > 6) return;                       // 拖拽不触发
    const g = pick(e);
    if (g) location.href = g.userData.link;
  });

  /* ── 入场动画 + 环境动效 + 主循环 ── */
  const easeOut = x => 1 - Math.pow(1 - x, 3);
  let startT = null, ambient = !reduced;
  const liftCur = new Map();
  function eachMat(o, fn){
    const seen = new Set();
    o.traverse(m => { if (m.material && !seen.has(m.material)){ seen.add(m.material); fn(m.material); } });
  }
  /* 入场登记:fade 记录各材质原始透明度 */
  track.forEach(s => {
    const o = s.obj;
    if (s.kind === 'rise'){ s.yTo = o.position.y; o.position.y = s.yTo - 1.2; }
    if (s.kind === 'drop'){ s.yTo = o.position.y; o.position.y = s.yTo + 2.2; }
    if (s.kind === 'fade'){
      s.mats = [];
      eachMat(o, m => { s.mats.push({ m, op: m.opacity ?? 1 }); m.transparent = true; m.opacity = 0; });
    }
  });
  function setFade(s, k){
    (s.mats || []).forEach(({ m, op }) => { m.opacity = op * k; });
  }
  function tick(now){
    if (startT === null) startT = now;
    const t = (now - startT) / 1000;
    /* 入场 */
    track.forEach(s => {
      const k = THREE.MathUtils.clamp((t - s.t0) / s.dur, 0, 1);
      if (k <= 0) return;
      const e = easeOut(k);
      if (s.kind === 'rise' || s.kind === 'drop'){
        const from = s.kind === 'rise' ? s.yTo - 1.2 : s.yTo + 2.2;
        s.obj.position.y = from + (s.yTo - from) * e;
      } else if (s.kind === 'fade'){
        setFade(s, e);
      }
    });
    /* 点灯:入场的最后一拍,昼夜都成立 */
    const lk = easeOut(THREE.MathUtils.clamp((t - 1.7 - P.anim.lampDelay) / P.anim.lampDur, 0, 1));
    /* 主题过渡 */
    if (Math.abs(themeT - themeTarget) > .001){
      themeT += Math.sign(themeTarget - themeT) * Math.min(.03, Math.abs(themeTarget - themeT));
    }
    applyTheme(themeT);
    M.lamp.emissiveIntensity *= lk;
    lamp.intensity *= lk;
    spot.material.opacity *= lk;
    /* 环境动效 */
    if (ambient){
      crown.rotation.z = Math.sin(t * .6) * .018;
      crown.rotation.x = Math.sin(t * .43) * .012;
      flag.rotation.y = Math.sin(t * 1.1) * .25;
      if (themeT > .5){
        const fl = 1 + Math.sin(t * 7.3) * .04 + Math.sin(t * 12.7) * .025;
        M.lamp.emissiveIntensity = LIGHT.night.lampEmissive * fl * lk;
        lamp.intensity = LIGHT.night.lampI * fl * lk;
      }
    }
    /* 悬停抬升 */
    pickables.forEach(g => {
      const want = g.userData.lift ? .35 : 0;
      const cur = liftCur.get(g) ?? 0;
      const nxt = cur + (want - cur) * .14;
      liftCur.set(g, nxt);
      g.position.y = nxt;
    });
    renderer.render(scene, cam);
  }
  function renderOnce(){ renderer.render(scene, cam); }

  /* 尺寸自适应 */
  function resize(){
    const w = container.clientWidth, h = container.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    cam.aspect = w / h; cam.updateProjectionMatrix();
    if (reduced) renderOnce();
  }
  const ro = new ResizeObserver(resize); ro.observe(container); resize();

  /* 启动:reduced-motion 直跳完成态 */
  let running = false;
  function start(){ if (running) return; running = true; renderer.setAnimationLoop(tick); }
  function stop(){ running = false; renderer.setAnimationLoop(null); }
  if (reduced){
    /* 直接完成态 */
    track.forEach(s => {
      if (s.kind === 'rise' || s.kind === 'drop') s.obj.position.y = s.yTo;
      if (s.kind === 'fade') setFade(s, 1);
    });
    themeT = themeTarget; applyTheme(themeTarget); renderOnce();
  } else {
    start();
  }

  /* 页面隐藏 / 离屏即暂停 */
  document.addEventListener('visibilitychange', () => {
    if (reduced) return;
    if (document.hidden) stop(); else if (onScreen) start();
  });
  let onScreen = true;
  new IntersectionObserver(es => {
    onScreen = es[0].isIntersecting;
    if (reduced) return;
    if (onScreen && !document.hidden) start(); else stop();
  }, { threshold: .05 }).observe(container);

  /* 主题事件 */
  document.addEventListener('nm-theme', e => setTheme(e.detail.dark));

  return {
    setTheme, resetView, start, stop,
    stats(){ let tris = 0, objs = 0;
      scene.traverse(o => { objs++; if (o.geometry){
        const g = o.geometry; tris += (g.index ? g.index.count : g.attributes.position.count) / 3; } });
      return { triangles: Math.round(tris), objects: objs }; },
  };
}
