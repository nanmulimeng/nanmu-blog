// 编辑器(DESIGN §4.2):
// - 状态五态:已保存(rev N)/保存中/未保存/保存失败(重试)/版本冲突(409)
// - 触发:Ctrl+S 手动、停顿 30s 防抖、最长 60s 周期保存(持续输入也落盘)
// - 保存中不再发新请求;成功回调用发起时快照对比当前值,旧响应不把新输入误标为已保存
// - localStorage 补救位:节流 2s;服务端保存成功即清空;打开时发现更新的本地内容提示恢复
// - 未保存离开:beforeunload 确认
const $ = (id) => document.getElementById(id);
const SLUG_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

const els = {
  slug: $('f-slug'), title: $('f-title'), date: $('f-date'), tags: $('f-tags'), body: $('f-body'),
  status: $('status'), saveBtn: $('save-btn'),
  conflictBox: $('conflict-box'), conflictMsg: $('conflict-msg'),
  conflictLocal: $('conflict-local'), conflictRefresh: $('conflict-refresh'),
};

const DEBOUNCE_MS = 30_000;
const PERIODIC_MS = 60_000;
const LS_KEY_BASE = 'wb-local-draft:';

let state = {
  mode: 'loading', // loading | new | open
  rev: 0,
  dirty: false,
  saving: false,
  lastSavedAt: null,
  conflicted: false,
};

function localKey() { return LS_KEY_BASE + (state.mode === 'open' ? els.slug.value : ''); }

function collectFields() {
  return {
    title: els.title.value,
    date: els.date.value,
    tags: els.tags.value.split(',').map((t) => t.trim()).filter((t) => t.length > 0),
    body: els.body.value,
  };
}

function sameFields(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

function hhmm(d = new Date()) {
  return d.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' });
}

function setStatus(kind, text) {
  state.statusKind = kind;
  els.status.dataset.state = kind; // 机器可判状态(避免文案子串歧义)
  els.status.className = `wb-status ${kind === 'error' || kind === 'conflict' ? 'err' : kind === 'clean' ? 'ok' : ''}`;
  els.status.textContent = text;
}

function renderStatus() {
  if (state.conflicted) return; // 冲突态由冲突框呈现
  if (state.saving) { setStatus('saving', '保存中…'); return; }
  if (state.dirty) {
    setStatus('dirty', `未保存(已保存至 rev ${state.rev})`);
  } else if (state.lastSavedAt) {
    setStatus('clean', `已保存 ${hhmm(state.lastSavedAt)}(rev ${state.rev})`);
  } else {
    setStatus('idle', state.mode === 'open' ? `已载入 rev ${state.rev}` : '新草稿,尚未保存');
  }}

// ---------- localStorage 补救位(不属保存契约,只救「忘点保存关了页」) ----------
let lsTimer = null;
function scheduleLocalSave() {
  if (lsTimer) return;
  lsTimer = setTimeout(() => {
    lsTimer = null;
    if (state.mode === 'open' && !state.conflicted) {
      try {
        localStorage.setItem(localKey(), JSON.stringify({
          fields: collectFields(), revBase: state.rev, savedAt: Date.now(),
        }));
      } catch { /* 存储满等:补救位尽力而为 */ }
    }
  }, 2_000);
}

function clearLocal() {
  try { localStorage.removeItem(localKey()); } catch { /* ignore */ }
}

function maybeOfferLocalRecovery(serverRev, serverFields) {
  let local = null;
  try { local = JSON.parse(localStorage.getItem(localKey()) ?? 'null'); } catch { local = null; }
  if (!local || local.revBase !== serverRev) return;
  if (sameFields(local.fields, serverFields)) { clearLocal(); return; }
  // 本地内容基于同一 rev 且与服务端不同 → 视为更新的未保存文本,提示恢复
  const yes = window.confirm('浏览器本地有未保存的内容(上次会话),恢复到编辑器?\n「取消」= 丢弃本地副本,以服务端版本为准。');
  if (yes) {
    els.title.value = local.fields.title;
    els.date.value = local.fields.date;
    els.tags.value = local.fields.tags.join(', ');
    els.body.value = local.fields.body;
    markDirty();
    setStatus('dirty', '已恢复浏览器本地的未保存内容');
  }
  clearLocal();
}

// ---------- 保存 ----------
let debounceTimer = null;

function markDirty() {
  state.dirty = true;
  renderStatus();
  scheduleLocalSave();
  // 停顿 30s 防抖:以最后一次输入为起点重置(持续输入不触发,由 60s 周期兜底)
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => { debounceTimer = null; void save('debounce'); }, DEBOUNCE_MS);
}

async function save(_trigger) {
  if (state.saving || state.conflicted) return;
  if (!state.dirty) { renderStatus(); return; }
  const slug = els.slug.value.trim();
  if (!SLUG_RE.test(slug) || /^\d+$/.test(slug)) {
    setStatus('error', 'slug 不合法:单层、小写英文数字短横线、非纯数字。');
    return;
  }
  const snap = collectFields();
  if (!snap.title.trim()) { setStatus('error', '标题不能为空,未保存。'); return; }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(snap.date)) { setStatus('error', '日期格式不正确,未保存。'); return; }

  state.saving = true;
  renderStatus();
  els.saveBtn.disabled = true;
  try {
    const res = await fetch(`/api/drafts/${encodeURIComponent(slug)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify({ ...snap, rev: state.rev }),
    });
    if (res.status === 401) { window.location.assign('/login'); return; }
    if (res.ok) {
      const data = await res.json();
      state.rev = data.rev;
      state.mode = 'open';
      els.slug.readOnly = true; // 保存成功即锁定:slug 已成为已存在草稿的身份
      state.lastSavedAt = new Date();
      lastSaveOrLoad = Date.now();
      state.dirty = !sameFields(snap, collectFields());
      if (!state.dirty) clearLocal();
      // 成功后由 finally 统一渲染:dirty 时显示「未保存(已保存至 rev N)」,
      // 即旧请求成功后仍有新输入时不会误标为已保存
    } else if (res.status === 409) {
      const data = await res.json();
      enterConflict(data.currentRev);
    } else if (res.status === 400) {
      setStatus('error', '字段校验未通过(标题/日期/tags/slug),未保存。');
    } else {
      setStatus('error', `保存失败 ${hhmm()} · 可重试(${res.status})`);
    }  } catch {
    setStatus('error', `保存失败 ${hhmm()}(网络) · 可重试`);
  } finally {
    state.saving = false;
    els.saveBtn.disabled = false;
    // 成功分支的渲染发生在 saving=true 期间,复位后需重渲染;
    // 但 error/conflict 的如实文案不得被常规渲染覆盖(e2e 抓出)
    if (!state.conflicted && state.statusKind !== 'error') renderStatus();
    if (state.dirty && !state.conflicted) scheduleLocalSave();
  }
}

function enterConflict(currentRev) {
  state.conflicted = true;
  // 本窗口未保存内容进补救位(刷新/取舍都不丢)
  try {
    localStorage.setItem(localKey(), JSON.stringify({
      fields: collectFields(), revBase: state.rev, savedAt: Date.now(),
    }));
  } catch { /* ignore */ }
  els.conflictMsg.textContent =
    `此草稿已在另一窗口保存(服务端现为 rev ${currentRev},本窗口基于 rev ${state.rev})。此处不覆盖;请核对后取舍。`;
  els.conflictLocal.value =
    `【标题】${els.title.value}\n【日期】${els.date.value}\n【tags】${els.tags.value}\n\n${els.body.value}`;
  els.conflictBox.hidden = false;
  setStatus('conflict', '版本冲突:本窗口内容未保存');
}

els.conflictRefresh.addEventListener('click', () => { window.location.reload(); });

// ---------- 输入绑定 ----------
for (const el of [els.title, els.date, els.tags, els.body]) {
  el.addEventListener('input', () => { if (!state.conflicted) markDirty(); });
}
els.slug.addEventListener('input', () => {
  if (state.mode === 'open') return; // 已保存过的草稿 slug 只读(服务端已锁定身份)
  if (els.title.value || els.body.value) markDirty();
});

document.addEventListener('keydown', (ev) => {
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 's') {
    ev.preventDefault();
    void save('manual');
  }
});
els.saveBtn.addEventListener('click', () => { void save('manual'); });

window.addEventListener('beforeunload', (ev) => {
  if (state.dirty || state.saving) {
    ev.preventDefault();
    ev.returnValue = '';
  }
});

// 周期保存上限:持续输入也每 60s 落盘一次(与 30s 停顿防抖独立)
let lastSaveOrLoad = Date.now();
setInterval(() => {
  if (!state.dirty || state.saving || state.conflicted) { lastSaveOrLoad = Date.now(); return; }
  if (Date.now() - lastSaveOrLoad >= PERIODIC_MS) {
    lastSaveOrLoad = Date.now();
    void save('periodic');
  }
}, 1_000);

// ---------- 载入 ----------
(async function load() {
  const slugInUrl = decodeURIComponent(window.location.pathname.split('/edit/')[1] ?? '');
  const isNew = slugInUrl === 'new';
  els.date.value = new Date().toISOString().slice(0, 10); // 默认今天
  if (!isNew) els.slug.value = slugInUrl;

  if (isNew) {
    state.mode = 'new';
    els.slug.readOnly = false;
    els.slug.focus();
    renderStatus();
    return;
  }
  const res = await fetch(`/api/drafts/${encodeURIComponent(slugInUrl)}`);
  if (res.status === 401) { window.location.assign('/login'); return; }
  if (res.status === 404) {
    // URL 指定的草稿不存在 → 以该 slug 进入新建模式(仍可改)
    state.mode = 'new';
    renderStatus();
    return;
  }
  if (!res.ok) {
    const err = res.status === 422 ? '草稿记录损坏,无法加载' : `加载失败(${res.status})`;
    setStatus('error', err);
    return;
  }
  const { draft, recovered } = await res.json();
  state.mode = 'open';
  state.rev = draft.rev;
  state.lastSavedAt = null;
  els.slug.value = draft.slug;
  els.slug.readOnly = true;
  els.title.value = draft.title;
  els.date.value = draft.date;
  els.tags.value = (draft.tags ?? []).join(', ');
  els.body.value = draft.body;
  $('page-title').textContent = `编辑:${draft.title}`;
  if (recovered === 'prev') {
    setStatus('error', '已恢复到上一完整保存(当前记录曾损坏),请检查内容。');
  } else {
    renderStatus();
  }
  maybeOfferLocalRecovery(draft.rev, draft);
})();
