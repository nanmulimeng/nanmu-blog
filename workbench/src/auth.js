// 认证与会话(DESIGN §3):argon2id 比对、内存会话表、登录防爆破限速
// 口令哈希只进服务器 env(WORKBENCH_PASSWORD_HASH);本地开发口令为进程内占位符,不落盘
import crypto from 'node:crypto';
import { hashSync, verifySync } from '@node-rs/argon2';

export const SESSION_TTL_MS = 12 * 3600 * 1000;
export const SESSION_COOKIE = 'wb_session';
export const LOGIN_MAX_FAILURES = 5;
export const LOGIN_WINDOW_MS = 15 * 60 * 1000;

/** 生产模式必须显式提供 env 哈希;dev 模式把占位口令一次性哈希后走同一条 verify 路径 */
export function makePasswordVerifier(opts) {
  if (opts.production) {
    const hash = opts.passwordHash;
    if (!hash) {
      throw new Error('生产模式必须配置 WORKBENCH_PASSWORD_HASH(服务器 env,不进代码/日志)');
    }
    return (pw) => {
      try {
        return verifySync(hash, pw);
      } catch {
        return false; // 哈希格式损坏等:按验证失败处理,不向客户端暴露原因
      }
    };
  }
  const hash = hashSync(opts.devPassword ?? 'dev-placeholder'); // 占位符,非真实凭据
  return (pw) => {
    try {
      return verifySync(hash, pw);
    } catch {
      return false;
    }
  };
}

/** 服务端会话表:内存 Map,进程重启即清空(设计如此,无持久会话) */
export class SessionStore {
  #map = new Map(); // sid -> expiresAt(ms)

  constructor(now = Date.now) {
    this.now = now;
  }

  create() {
    const sid = crypto.randomBytes(32).toString('hex');
    const expiresAt = this.now() + SESSION_TTL_MS;
    this.#map.set(sid, expiresAt);
    return { sid, expiresAt };
  }

  get(sid) {
    if (!sid) return null;
    const expiresAt = this.#map.get(sid);
    if (expiresAt === undefined) return null;
    if (this.now() >= expiresAt) {
      this.#map.delete(sid); // 惰性清理
      return null;
    }
    return { sid, expiresAt };
  }

  delete(sid) {
    this.#map.delete(sid);
  }

  /** 定期清理过期会话(防长期运行泄漏) */
  sweep() {
    for (const [sid, expiresAt] of this.#map) {
      if (this.now() >= expiresAt) this.#map.delete(sid);
    }
  }
}

/** 登录失败限速:同 IP 15min 窗口内 5 次失败即锁定;只记失败次数与时间,不记口令 */
export class LoginRateLimiter {
  #failures = new Map(); // ip -> [timestamp]

  constructor(now = Date.now) {
    this.now = now;
  }

  #recent(ip) {
    const list = (this.#failures.get(ip) ?? []).filter(
      (ts) => this.now() - ts < LOGIN_WINDOW_MS,
    );
    this.#failures.set(ip, list);
    return list;
  }

  locked(ip) {
    return this.#recent(ip).length >= LOGIN_MAX_FAILURES;
  }

  recordFailure(ip) {
    const list = this.#failures.get(ip) ?? [];
    list.push(this.now());
    this.#failures.set(ip, list);
  }

  reset(ip) {
    this.#failures.delete(ip);
  }

  count(ip) {
    return this.#recent(ip).length;
  }
}

/** 从 Cookie 头解析会话 id(仅取 wb_session,不做通用 cookie 库) */
export function readSessionCookie(header) {
  if (!header) return null;
  for (const part of header.split(';')) {
    const eq = part.indexOf('=');
    if (eq === -1) continue;
    if (part.slice(0, eq).trim() === SESSION_COOKIE) {
      return part.slice(eq + 1).trim();
    }
  }
  return null;
}

export function serializeSessionCookie(sid, { secure, clear = false } = {}) {
  const parts = [
    `${SESSION_COOKIE}=${clear ? '' : sid}`,
    'Path=/',
    'HttpOnly',
    'SameSite=Strict',
    `Max-Age=${clear ? 0 : SESSION_TTL_MS / 1000}`,
  ];
  if (secure) parts.push('Secure');
  return parts.join('; ');
}
