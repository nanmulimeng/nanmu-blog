import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

/* ── 预览存活与资源 token(DESIGN §4.3,任务 2.3)──
   预览:24h 过期+总量 10 上限从最旧清理;删除/过期/被清理 → 一律 410
   (不区分,不泄露存在性)。删除连带失效其全部 token。
   token:服务端记录的短期 bearer 凭证(会话/预览 ID/有效期 30min/类别
   css+font+img);值不进日志;会话活跃性由路由层组合判定(撤回语义)。 */

export const PREVIEW_TTL_MS = 24 * 3600 * 1000;
export const PREVIEW_MAX = 10;
export const TOKEN_TTL_MS = 30 * 60 * 1000;
export const TOKEN_KINDS = new Set([
  'css', 'woff', 'woff2', 'ttf', 'otf',
  'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'avif', 'ico',
]);

export function createPreviewStore({ previewsDir, now = Date.now, max = PREVIEW_MAX,
                                      ttlMs = PREVIEW_TTL_MS, tokenTtlMs = TOKEN_TTL_MS } = {}) {
  const live = new Map();   // opId -> {registeredAt}
  const tokens = new Map(); // tokenStr -> {sid, opId, exp}

  const dropDir = (opId) => {
    try { fs.rmSync(path.join(previewsDir, opId), { recursive: true, force: true }); }
    catch { /* 清理尽力而为 */ }
  };

  function remove(opId) {
    live.delete(opId);
    for (const [k, v] of tokens) if (v.opId === opId) tokens.delete(k);
    dropDir(opId);
  }

  function sweep() {
    const t = now();
    for (const [id, rec] of live) if (t - rec.registeredAt >= ttlMs) remove(id);
    while (live.size > max) {
      let oldest = null;
      for (const [id, rec] of live) if (!oldest || rec.registeredAt < oldest[1].registeredAt) oldest = [id, rec];
      remove(oldest[0]);
    }
  }

  return {
    previewsDir,
    dirOf(opId) { return path.join(previewsDir, opId); },
    register(opId) { live.set(opId, { registeredAt: now() }); sweep(); },
    get(opId) {
      const rec = live.get(opId);
      if (!rec) return null;
      if (now() - rec.registeredAt >= ttlMs) { remove(opId); return null; }
      return rec;
    },
    remove,
    issueToken({ sid, opId }) {
      const t = crypto.randomBytes(18).toString('base64url');
      tokens.set(t, { sid, opId, exp: now() + tokenTtlMs });
      return t;
    },
    /* 返回 'ok' 或拒绝原因;gone 之外一律 401 语义 */
    checkToken({ t, opId, kind }) {
      const rec = tokens.get(t);
      if (!rec) return 'unknown';
      if (now() >= rec.exp) { tokens.delete(t); return 'expired'; }
      if (rec.opId !== opId) return 'cross';
      if (!TOKEN_KINDS.has(kind)) return 'kind';
      return 'ok';
    },
    tokenSid(t) { return tokens.get(t)?.sid ?? null; },
  };
}
