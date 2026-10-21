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
          <button type="button" class="wb-ghost wb-inline-btn" disabled title="批 2 接入">预览</button> ·
          <button type="button" class="wb-ghost wb-inline-btn" disabled title="批 3 接入">发布</button>
        </td>
      </tr>`).join('');
    for (const btn of document.querySelectorAll('[data-del]')) {
      btn.addEventListener('click', () => removeDraft(btn.dataset.del, btn.dataset.title));
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
