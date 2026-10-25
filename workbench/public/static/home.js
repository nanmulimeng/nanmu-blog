// 工作台首页:草稿列表(任务 1.4)+登出
const statusEl = document.getElementById('home-status');
const tbody = document.getElementById('drafts-body');

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

async function loadDrafts() {
  try {
    const res = await fetch('/api/drafts');
    if (res.status === 401) { window.location.assign('/login'); return; }
    if (!res.ok) throw new Error(`status ${res.status}`);
    const { drafts } = await res.json();
    if (drafts.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="wb-status">还没有草稿。点右上「+ 新建草稿」开始。</td></tr>';
      return;
    }
    tbody.innerHTML = drafts.map((d) => `
      <tr>
        <td>${esc(d.slug)}</td>
        <td>${esc(d.title)}${d.recovered === 'prev' ? '<span class="wb-status err"> · 已恢复上一完整保存,请检查</span>' : ''}</td>
        <td>${esc(d.date)}</td>
        <td>${d.charCount}</td>
        <td>${d.rev}</td>
        <td>
          <a href="/edit/${encodeURIComponent(d.slug)}">编辑</a> ·
          <button type="button" class="wb-ghost wb-inline-btn" data-del="${esc(d.slug)}" data-title="${esc(d.title)}">删除草稿</button> ·
          <button type="button" class="wb-ghost wb-inline-btn" data-preview="${esc(d.slug)}">预览</button>
        </td>
      </tr>`).join('');
    for (const btn of document.querySelectorAll('[data-del]')) {
      btn.addEventListener('click', () => removeDraft(btn.dataset.del, btn.dataset.title));
    }
    for (const btn of document.querySelectorAll('[data-preview]')) {
      btn.addEventListener('click', () => makePreview(btn.dataset.preview, btn));
    }
  } catch {
    tbody.innerHTML = '<tr><td colspan="6" class="wb-status err">列表加载失败,刷新重试。</td></tr>';
  }
}

async function removeDraft(slug, title) {
  statusEl.className = 'wb-status';
  statusEl.textContent = '';
  if (!window.confirm(`删除草稿「${title}」(${slug})?此操作不可恢复。`)) return;
  try {
    const res = await fetch(`/api/drafts/${encodeURIComponent(slug)}`, {
      method: 'DELETE',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (res.ok) {
      loadDrafts();
    } else if (res.status === 401) {
      window.location.assign('/login');
    } else {
      statusEl.className = 'wb-status err';
      statusEl.textContent = `删除失败(${res.status}),请重试。`;
    }
  } catch {
    statusEl.className = 'wb-status err';
    statusEl.textContent = '网络请求失败,请重试。';
  }
}

document.getElementById('logout-btn').addEventListener('click', async () => {
  statusEl.textContent = '';
  try {
    const res = await fetch('/api/logout', {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (res.ok || res.status === 401) {
      window.location.assign('/login');
    } else {
      statusEl.className = 'wb-status err';
      statusEl.textContent = `登出失败(${res.status}),请重试。`;
    }
  } catch {
    statusEl.className = 'wb-status err';
    statusEl.textContent = '网络请求失败,请重试。';
  }
});

loadDrafts();


/* ── 操作区块(批 3):界面态映射+撤下+重查 ── */
const OPS_STATE = {
  published: '已上线', superseded: '已被替代', withdrawn: '已撤下',
  pending_confirm: '未确认', commit_created: '发布中', backup_received: '发布中',
  deploy_received: '确认中', github_rejected: '失败(备份推送被拒)',
  deploy_rejected: '部分成功(待恢复)', failed: '失败', created: '进行中',
};
const csrfHeaders = () => ({ 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' });

async function loadOperations() {
  const tbody = document.getElementById('ops-tbody');
  try {
    const res = await fetch('/api/operations');
    if (res.status === 401) { window.location.assign('/login'); return; }
    if (!res.ok) throw new Error(`status ${res.status}`);
    const { operations } = await res.json();
    if (!operations.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="wb-status">还没有发布或撤下操作。</td></tr>';
      return;
    }
    const seen = new Set();
    const rows = [];
    for (const o of [...operations].reverse()) {
      if (seen.has(o.slug)) continue;
      seen.add(o.slug);
      const kind = o.kind === 'withdraw' ? '撤下' : '发布';
      const state = OPS_STATE[o.state] || o.state;
      let act = '';
      if (o.state === 'published') {
        act = `<button type="button" class="wb-ghost wb-inline-btn" data-withdraw="${esc(o.slug)}">撤下</button>`;
      } else if (o.state === 'pending_confirm' || o.state === 'deploy_rejected') {
        act = `<button type="button" class="wb-ghost wb-inline-btn" data-recheck="${esc(o.id)}">重查</button>`;
      }
      rows.push(`<tr><td>${esc(o.slug)}</td><td>${kind}</td><td>${esc(state)}</td><td>${act}</td></tr>`);
    }
    tbody.innerHTML = rows.join('');
    for (const b of document.querySelectorAll('[data-withdraw]')) {
      b.addEventListener('click', () => withdrawPost(b.dataset.withdraw));
    }
    for (const b of document.querySelectorAll('[data-recheck]')) {
      b.addEventListener('click', async () => {
        b.disabled = true;
        await fetch(`/api/operations/${b.dataset.recheck}/confirm`, { method: 'POST', headers: csrfHeaders() });
        loadOperations();
      });
    }
  } catch {
    tbody.innerHTML = '<tr><td colspan="4" class="wb-status err">操作列表加载失败,刷新重试。</td></tr>';
  }
}

async function makePreview(slug, btn) {
  btn.disabled = true; btn.textContent = '构建中…';
  try {
    const res = await fetch('/api/preview', {
      method: 'POST', headers: csrfHeaders(),
      body: JSON.stringify({ slug }),
    });
    if (res.status === 401) { window.location.assign('/login'); return; }
    const data = await res.json();
    if (res.ok && data.url) { window.open(data.url, '_blank'); }
    else { alert(`预览失败:${data.error || res.status}(构建约需 15-20 秒,稍后再试)`); }
  } catch { alert('预览失败(网络)'); }
  finally { btn.disabled = false; btn.textContent = '预览'; }
}

async function withdrawPost(slug) {
  const IMPACT = '撤下影响:\n- 正文 URL 将 404;列表/首页/RSS/3D 纸面不再出现\n- Git 历史保留该文(不改写历史)\n- 回滚到含该文的旧版本会重新公开它';
  if (!confirm(`撤下 "${slug}"?\n\n${IMPACT}\n\n确定撤下?`)) return;
  const res = await fetch('/api/withdraw', {
    method: 'POST', headers: csrfHeaders(),
    body: JSON.stringify({ slug, idemKey: crypto.randomUUID() }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { alert(`撤下失败:${data.detail || data.error || res.status}`); return; }
  // 与发布对称:轮询内容身份核对(撤下确认=目标路径不存在)再刷新
  for (let i = 0; i < 10; i++) {
    await new Promise((r) => setTimeout(r, 3000));
    const c = await fetch(`/api/operations/${data.id}/confirm`, {
      method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (!c.ok) continue;
    const cr = await c.json();
    if (cr.status === 'confirmed' || cr.status === 'pending_confirm') break;
  }
  loadOperations();
}

loadOperations();
