// 工作台首页交互(任务 1.2:会话显示+登出;列表与编辑器在 1.3/1.4 接入)
const statusEl = document.getElementById('home-status');

async function loadSession() {
  const res = await fetch('/api/session');
  if (!res.ok) {
    window.location.assign('/login'); // 会话过期/未登录:回登录页
    return;
  }
  const data = await res.json();
  const t = new Date(data.expiresAt);
  document.getElementById('session-expiry').textContent = t.toLocaleTimeString('zh-CN', { hour12: false });
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

loadSession();
