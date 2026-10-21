// 草稿存储(DESIGN §4.2/§5):单记录 draft.json 一次替换是唯一保存提交点
// - 保存:写 tmp → fsync(tmp) → 一次 rename → 尽力 fsync 目录 → 写 prev(上一版兜底,仅一份)
// - 恢复:tmp 残留=替换未发生,读取时丢弃;draft.json 损坏→回退 draft.prev.json
// - 并发:每 slug 单写者串行队列,「读 rev→校验→写 tmp→rename」整体持队列
// slug 规则与 site/src/lib/content.ts 的 assertPostsIds 同构(单层/小写/非纯数字)
import path from 'node:path';
import fs from 'node:fs/promises';

const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

export function validateSlug(slug) {
  return typeof slug === 'string' && SLUG_RE.test(slug) && !/^\d+$/.test(slug);
}

/** 表单字段校验:title 非空、date YYYY-MM-DD、tags 数组、body 字符串 */
export function validateDraftFields(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return { ok: false, detail: 'body' };
  }
  const { title, date, tags, body: text } = body;
  if (typeof title !== 'string' || !title.trim()) return { ok: false, detail: 'title' };
  if (typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(date)
      || Number.isNaN(new Date(`${date}T00:00:00Z`).getTime())) {
    return { ok: false, detail: 'date' };
  }
  if (!Array.isArray(tags) || tags.some((t) => typeof t !== 'string' || t.includes(','))) {
    return { ok: false, detail: 'tags' };
  }
  if (typeof text !== 'string') return { ok: false, detail: 'body' };
  return { ok: true, fields: { title: title.trim(), date, tags, body: text } };
}

function parseRecord(raw) {
  try {
    const rec = JSON.parse(raw);
    if (rec && typeof rec === 'object'
        && Number.isInteger(rec.rev) && rec.rev > 0
        && typeof rec.slug === 'string' && typeof rec.body === 'string') {
      return rec;
    }
  } catch { /* 视为损坏 */ }
  return null;
}

export class DraftStore {
  /** @param {string} rootDir 草稿根目录(工作台私有,不在 git 仓库内) */
  constructor(rootDir, { now = Date.now } = {}) {
    this.root = rootDir;
    this.now = now;
    this.#queues = new Map();
  }

  #queues;

  /** 每 slug 单写者队列:同一草稿的读-校验-写整体串行 */
  enqueue(slug, fn) {
    const prev = this.#queues.get(slug) ?? Promise.resolve();
    const run = prev.then(fn, fn); // 前序失败不阻断本任务(各自独立校验)
    this.#queues.set(slug, run);
    run.catch(() => {}).finally(() => {
      if (this.#queues.get(slug) === run) this.#queues.delete(slug);
    });
    return run;
  }

  #dir(slug) {
    return path.join(this.root, slug); // slug 已由 validateSlug 拒绝 '/','..','\\'
  }

  /** 读取当前记录(含恢复语义)。返回 null(不存在)/{record,raw,recovered}/{corrupted} */
  async #readCurrent(slug) {
    const dir = this.#dir(slug);
    const tmp = path.join(dir, 'draft.json.tmp');
    const prevPath = path.join(dir, 'draft.prev.json');
    // tmp 残留=替换未发生:丢弃,当前版即旧版(§4.2 中断恢复)
    await fs.rm(tmp, { force: true }).catch(() => {});
    let raw = null;
    try {
      raw = await fs.readFile(path.join(dir, 'draft.json'), 'utf8');
    } catch (e) {
      if (e.code !== 'ENOENT') raw = ''; // 存在但读不出:按损坏处理
    }
    if (raw !== null) {
      const rec = parseRecord(raw);
      if (rec) return { record: rec, raw, recovered: null };
      // 主记录损坏 → 回退 prev(如有)
      try {
        const praw = await fs.readFile(prevPath, 'utf8');
        const prec = parseRecord(praw);
        if (prec) return { record: prec, raw: praw, recovered: 'prev' };
      } catch { /* 无 prev */ }
      return { corrupted: true };
    }
    return null;
  }

  async get(slug) {
    if (!validateSlug(slug)) throw new Error('bad slug');
    const cur = await this.enqueue(slug, () => this.#readCurrent(slug));
    if (!cur) return null;
    if (cur.corrupted) return { corrupted: true };
    return { record: cur.record, recovered: cur.recovered };
  }

  /**
   * 保存:baseRev 不匹配当前 rev → 冲突(409);否则整体替换为新记录(rev+1)。
   * 返回(rename 完成后)新 rev;冲突抛 {statusCode:409, currentRev}。
   */
  async save(slug, fields, baseRev) {
    if (!validateSlug(slug)) throw new Error('bad slug');
    return this.enqueue(slug, async () => {
      const cur = await this.#readCurrent(slug);
      const curRev = cur?.record?.rev ?? 0;
      if (curRev !== baseRev) {
        const err = new Error('draft rev conflict');
        err.statusCode = 409;
        err.wbPayload = { error: 'conflict', currentRev: curRev };
        throw err;
      }
      const record = {
        slug,
        title: fields.title,
        date: fields.date,
        tags: fields.tags,
        body: fields.body,
        rev: curRev + 1,
        savedAt: new Date(this.now()).toISOString(),
        base: cur?.record?.base ?? null, // 编辑基准:批 1 恒 null,发布侧(批 3)写入
      };
      await this.#atomicReplace(slug, record, cur?.raw ?? null);
      return { rev: record.rev, savedAt: record.savedAt };
    });
  }

  /** 单记录一次替换:唯一保存提交点 = rename(tmp → draft.json) */
  async #atomicReplace(slug, record, oldRaw) {
    const dir = this.#dir(slug);
    await fs.mkdir(dir, { recursive: true });
    const finalPath = path.join(dir, 'draft.json');
    const tmp = path.join(dir, 'draft.json.tmp');
    const prevPath = path.join(dir, 'draft.prev.json');
    const prevTmp = path.join(dir, 'draft.prev.json.tmp');
    const data = Buffer.from(`${JSON.stringify(record, null, 2)}\n`, 'utf8');
    await fs.writeFile(tmp, data);
    let fd = await fs.open(tmp, 'r+');
    await fd.sync();
    await fd.close();
    await fs.rename(tmp, finalPath);
    // rename 后尽力 fsync 目录(Linux 生产有效;Windows 目录句柄不支持时静默跳过)
    try {
      const dfd = await fs.open(dir, 'r');
      await dfd.sync();
      await dfd.close();
    } catch { /* 尽力而为 */ }
    // 上一版兜底:替换成功后写 prev(仅一份,失败不影响保存结果)
    if (oldRaw) {
      try {
        await fs.writeFile(prevTmp, oldRaw);
        const pfd = await fs.open(prevTmp, 'r+');
        await pfd.sync();
        await pfd.close();
        await fs.rename(prevTmp, prevPath);
      } catch { /* 兜底文件尽力而为 */ }
    }
  }

  /** 删除草稿(整个 slug 目录);不存在返回 false */
  async remove(slug) {
    if (!validateSlug(slug)) throw new Error('bad slug');
    return this.enqueue(slug, async () => {
      try {
        await fs.rm(this.#dir(slug), { recursive: true, force: false });
        return true;
      } catch (e) {
        if (e.code === 'ENOENT') return false;
        throw e;
      }
    });
  }

  /** 列出全部草稿(列表页用;任务 1.4) */
  async list() {
    let entries;
    try {
      entries = await fs.readdir(this.root, { withFileTypes: true });
    } catch (e) {
      if (e.code === 'ENOENT') return [];
      throw e;
    }
    const out = [];
    for (const ent of entries) {
      if (!ent.isDirectory() || !validateSlug(ent.name)) continue;
      const cur = await this.#readCurrent(ent.name);
      if (cur?.record) {
        const { record, recovered } = cur;
        out.push({
          slug: record.slug,
          title: record.title,
          date: record.date,
          rev: record.rev,
          savedAt: record.savedAt,
          charCount: record.body.length,
          recovered,
        });
      }
    }
    out.sort((a, b) => (a.savedAt < b.savedAt ? 1 : -1));
    return out;
  }
}
