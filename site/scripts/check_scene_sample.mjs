/* scene6.js 排印字面量与 FIXED_SAMPLE 字体预载样本对账(批次 C 资产轮)。
   背景:fonts.load 样本缺字不报错,只让该字静默回退系统字体
   (批次 C 曾因此让零期空态文案部分字符回退渲染)。本脚本从
   articleTex/digestTex/aboutTex/pageHead/wrapLines 的函数体提取全部
   字符串字面量,与 FIXED_SAMPLE 对照——任何新增排印文案缺字即失败,
   防止「改文案忘同步样本」这一类回归。动态数据(title/excerpt/date
   等)由 fontsReady 运行时拼入样本,不在此对账。 */
import { readFileSync } from 'node:fs';

const SCENE = new URL('../public/3d/scene6.js', import.meta.url);
const src = readFileSync(SCENE, 'utf8');
const problems = [];

function bodyOf(name) {
  const i = src.indexOf('function ' + name + '(');
  if (i < 0) { problems.push(`找不到函数 ${name}`); return ''; }
  let d = 0;
  const j = src.indexOf('{', i);
  for (let k = j; k < src.length; k++) {
    if (src[k] === '{') d++;
    else if (src[k] === '}') {
      if (--d === 0) return src.slice(j + 1, k);
    }
  }
  problems.push(`${name} 函数体提取失败`);
  return '';
}

const litsRaw = ['wrapLines', 'pageHead', 'articleTex', 'digestTex', 'aboutTex']
  .map(bodyOf)
  .join('')
  .match(/'([^']*)'/g) || [];
// 字体声明字面量(如 '900 88px "Noto Serif SC", serif')不是排印内容
const lits = litsRaw
  .filter((m) => !/px |serif|Noto/.test(m))
  .map((m) => m.slice(1, -1));
const need = new Set(lits.join('').split('').filter((c) => c.trim() !== ''));

const fi = src.indexOf('const FIXED_SAMPLE =');
if (fi < 0) problems.push('找不到 FIXED_SAMPLE');
const fixedSrc = src.slice(fi, src.indexOf(';', fi));
const fixed = new Set(fixedSrc.replace(/^[^=]+=/, '').replace(/['+\s]/g, '').split(''));

const missing = [...need].filter((c) => !fixed.has(c));
if (missing.length) {
  problems.push(`FIXED_SAMPLE 缺字(将回退系统字体渲染): ${missing.join('')}`);
}
const extra = [...fixed].filter((c) => !need.has(c));
if (extra.length) {
  console.log(`[sample] 冗余字符(无害,可清理): ${extra.join('')}`);
}

if (problems.length) {
  for (const p of problems) console.error(`[sample] ${p}`);
  process.exit(1);
}
console.log('[sample] FIXED_SAMPLE 覆盖全部排印字面量 %d 字符 => OK', need.size);
