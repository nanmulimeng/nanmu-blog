import { exec } from 'node:child_process';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs';
import path from 'node:path';

const execFileP = promisify(execFile);

/* ── 预览构建(DESIGN §4.3)──
   worktree 只是脚手架:开临时 worktree → 草稿写入 posts/ → 跑与
   生产相同的构建 → dist 拷贝到 previews/<op-id>/ 独立副本 → 删 worktree。
   失败:不建预览目录,stdout/stderr 留证到 previews/<op-id>.failed.log;
   拷贝走 tmp+rename,中断不留半目录。构建超时 20 分钟兜底(命令必须能终止)。 */

const BUILD_TIMEOUT_MS = 20 * 60 * 1000;

function git(cwd, args) {
  return execFileP('git', args, { cwd });
}

function runShell(cmd, cwd) {
  return new Promise((resolve) => {
    exec(cmd, { cwd, timeout: BUILD_TIMEOUT_MS, maxBuffer: 32 * 1024 * 1024 },
      (err, stdout, stderr) => resolve({ err, stdout: String(stdout), stderr: String(stderr) }));
  });
}

async function removeWorktree(repoPath, wt) {
  try {
    await git(repoPath, ['worktree', 'remove', '--force', wt]);
  } catch {
    /* --force 兜底失败时再 prune 一次;worktree 目录已随异常消失也视为已清 */
    try { await git(repoPath, ['worktree', 'prune']); } catch { /* 最后兜底,不掩盖主流程 */ }
  }
}

export async function buildPreview({ repoPath, branch = 'main', draft, opId, previewsDir, buildCmd }) {
  const repoAbs = path.resolve(repoPath);
  const wt = path.join(path.dirname(repoAbs), `wt-${opId}`);
  fs.mkdirSync(previewsDir, { recursive: true });
  const failLog = path.join(previewsDir, `${opId}.failed.log`);
  let out = '';
  try {
    await git(repoAbs, ['worktree', 'add', '--detach', wt, branch]);
    const postsDir = path.join(wt, 'site', 'src', 'content', 'posts');
    fs.mkdirSync(postsDir, { recursive: true });
    fs.writeFileSync(path.join(postsDir, `${draft.slug}.md`), draft.content, 'utf8');

    const r = await runShell(buildCmd, path.join(wt, 'site'));
    out = `# buildCmd: ${buildCmd}\n# exit: ${r.err ? (r.err.code ?? 'killed') : 0}\n` +
      `--- stdout ---\n${r.stdout}\n--- stderr ---\n${r.stderr}`;
    if (r.err) {
      fs.writeFileSync(failLog, out, 'utf8');
      return { ok: false, reason: 'build-failed', log: failLog };
    }
    const dist = path.join(wt, 'site', 'dist');
    if (!fs.existsSync(dist)) {
      fs.writeFileSync(failLog, `${out}\n--- dist missing ---\n`, 'utf8');
      return { ok: false, reason: 'dist-missing', log: failLog };
    }
    /* tmp+rename:拷贝中断不留半目录(rename 同卷原子) */
    const tmp = path.join(previewsDir, `${opId}.tmp`);
    fs.rmSync(tmp, { recursive: true, force: true });
    fs.cpSync(dist, tmp, { recursive: true });
    fs.renameSync(tmp, path.join(previewsDir, opId));
    return { ok: true, dir: path.join(previewsDir, opId) };
  } catch (e) {
    try {
      fs.writeFileSync(failLog, `${out}\n--- exception ---\n${e && e.stack || e}\n`, 'utf8');
    } catch { /* 留证尽力而为,不掩盖原始失败 */ }
    return { ok: false, reason: 'build-error', log: failLog };
  } finally {
    await removeWorktree(repoAbs, wt);
  }
}
