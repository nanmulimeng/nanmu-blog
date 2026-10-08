// A vertical cross-section catches intersections along the full page height.
// No browser, renderer, or paid service required.
import assert from 'node:assert/strict';
import { PARAMS, bookPageGeometry } from '../prototypes/r4/3d/book.js';

const { book } = PARAMS;
const geometry = bookPageGeometry(book.w, book.h, book.curve);
const p = geometry.attributes.position;
const cols = geometry.parameters.widthSegments + 1;
const cross = (a, b) => a[0] * b[1] - a[1] * b[0];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
function intersects(a, b, c, d){
  const r = sub(b, a), s = sub(d, c), den = cross(r, s);
  if (Math.abs(den) < 1e-10) return false;
  const t = cross(sub(c, a), s) / den, u = cross(sub(c, a), r) / den;
  return t >= -1e-7 && t <= 1 + 1e-7 && u >= -1e-7 && u <= 1 + 1e-7;
}
function profile(angle, i){
  return Array.from({length: cols}, (_, j) => {
    const x = p.getX(j), z = p.getZ(j);
    return [x * Math.cos(angle) + z * Math.sin(angle),
      -x * Math.sin(angle) + z * Math.cos(angle) - i * (book.spineGap || 0)];
  });
}
function countCrossings(progress){
  const profiles = book.pages.map((pg, i) => {
    const initial = book.foldStart === undefined ? pg.ry : book.foldStart + i * book.foldGap;
    return profile(initial + (pg.ry - initial) * progress, i);
  });
  let crossings = 0;
  for (let a = 0; a < profiles.length; a++)
    for (let b = a + 1; b < profiles.length; b++)
      for (let i = 0; i < cols - 1; i++)
        for (let j = 0; j < cols - 1; j++)
          if (intersects(profiles[a][i], profiles[a][i+1], profiles[b][j], profiles[b][j+1])) crossings++;
  return crossings;
}
assert.equal(countCrossings(1), 0, 'completed pages must not cross through each other');
for (let frame = 0; frame <= 120; frame++)
  assert.equal(countCrossings(frame / 120), 0, `unfold progress ${frame}/120 must preserve page separation`);
geometry.dispose();
console.log('PASS: finished fan and 121 unfold samples contain no intersecting page cross-sections');
