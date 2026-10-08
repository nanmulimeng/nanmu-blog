// R5 碑页几何回归:参数间距防线——检查弓深、后衬页错层间距、虚线页中心距。
// 注意:本脚本不做完整三维交叉检测,也不采样动态状态;PASS 只代表当前参数
// 组合满足保守间距阈值,不能单独表述为"任意时刻无穿插"的证明。
// R5 无旋转书页扇(rise 平移 + 固定 ry),动态风险主要来自参数改动。
// Node 直跑,无浏览器依赖。
import assert from 'node:assert/strict';
import { PARAMS, steleGeometry } from '../prototypes/r5/3d/scene5.js';

const s = PARAMS.stele;
const geo = steleGeometry(s.w, s.h, s.curve);
const p = geo.attributes.position;
let zMin = Infinity, zMax = -Infinity, xMin = Infinity, xMax = -Infinity;
for (let i = 0; i < p.count; i++){
  zMin = Math.min(zMin, p.getZ(i)); zMax = Math.max(zMax, p.getZ(i));
  xMin = Math.min(xMin, p.getX(i)); xMax = Math.max(xMax, p.getX(i));
}
assert.ok(zMax - zMin < 0.2, `stele bow depth ${zMax - zMin} should stay shallow`);

/* 后衬页:与碑页同形,中心 z 间距必须大于两页弯曲深度之和(保守取 0.4) */
for (const b of PARAMS.backs){
  assert.ok(Math.abs(b.dz) > 0.4, `back sheet dz=${b.dz} too close to stele plane`);
}
/* 相邻后衬页之间也要留距 */
for (let i = 1; i < PARAMS.backs.length; i++){
  const gap = Math.abs(PARAMS.backs[i].dz - PARAMS.backs[i - 1].dz);
  assert.ok(gap > 0.4, `adjacent back sheets gap=${gap} too small`);
}
/* 虚线页与碑页:水平面(x,z)中心距须大于各自半径之和的一半(粗判) */
const g = PARAMS.ghost;
const dx = g.x - s.x, dz = g.z - s.z;
const dist = Math.hypot(dx, dz);
assert.ok(dist > (s.w + g.w) / 2 * 0.8, `ghost too close to stele: ${dist}`);

console.log(`PASS: stele bow depth ${(zMax - zMin).toFixed(3)}, backs offset ok, ghost distance ${dist.toFixed(2)}`);
