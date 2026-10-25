import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { buildPreview } from '../src/preview_build.js';

/* ── fixture:临时 bare 仓库(不碰本仓库/生产远端,批 3 同口径) ── */
function makeBareRepo(dir) {
  const bare = path.join(dir, 'bare.git');
  const seed = path.join(dir, 'seed');
  execFileSync('git', ['init', '--bare', '-b', 'main', bare]);
  execFileSync('git', ['clone', bare, seed]);
  fs.mkdirSync(path.join(seed, 'site', 'src', 'content', 'posts'), { recursive: true });
  fs.writeFileSync(path.join(seed, 'site', 'README'), 'fixture site\n');
  const git = (args, cwd) =>
    execFileSync('git', args, { cwd, env: { ...process.env, GIT_AUTHOR_NAME: 't', GIT_AUTHOR_EMAIL: 't@t', GIT_COMMITTER_NAME: 't', GIT_COMMITTER_EMAIL: 't@t', HOME: dir } });
  git(['add', '-A'], seed);
  git(['commit', '-m', 'seed'], seed);
  git(['push', 'origin', 'HEAD:main'], seed);
  return { bare, seed };
}

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'wbprev-'));
}

test('2.1 成功路径:草稿真实进构建,产物拷贝独立副本,worktree 删除', async () => {
  const dir = tmpDir();
  try {
    const { bare } = makeBareRepo(dir);
    const previewsDir = path.join(dir, 'previews');
    // buildCmd 在 worktree/site 下执行:把 posts 草稿原文拷进 dist,
    // 证明「草稿写入 → 构建输入 → 产物」链路(生产为 npm ci && npm run build)
    const buildCmd = 'node -e "const fs=require(\'fs\');fs.mkdirSync(\'dist\',{recursive:true});' +
      'fs.copyFileSync(\'src/content/posts/preview-test.md\',\'dist/draft-echo.md\');' +
      'fs.writeFileSync(\'dist/index.html\',\'<html>ok</html>\')"';
    const r = await buildPreview({
      repoPath: bare, branch: 'main', opId: 'op-1', previewsDir, buildCmd,
      draft: { slug: 'preview-test', content: '---\ntitle: 校对\n---\n正文哨兵。\n' },
    });
    assert.equal(r.ok, true);
    // 独立副本:previews/op-1/ 有产物,草稿内容真实进入构建输入
    assert.ok(fs.existsSync(path.join(previewsDir, 'op-1', 'index.html')));
    const echoed = fs.readFileSync(path.join(previewsDir, 'op-1', 'draft-echo.md'), 'utf8');
    assert.ok(echoed.includes('正文哨兵。'));
    // worktree 只作脚手架,构建完即删:仓库无残留 worktree
    // (git porcelain 输出正斜杠,统一比较)
    const list = execFileSync('git', ['worktree', 'list', '--porcelain'], { cwd: bare, env: { ...process.env, HOME: dir } }).toString();
    assert.ok(!list.replace(/\\/g, '/').includes(dir.replace(/\\/g, '/') + '/wt-'), `worktree 未清理: ${list}`);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('2.1 失败路径:构建失败不建预览,stdout/stderr 留证,worktree 仍清理', async () => {
  const dir = tmpDir();
  try {
    const { bare } = makeBareRepo(dir);
    const previewsDir = path.join(dir, 'previews');
    const buildCmd = 'node -e "console.error(\'build-boom\'); process.exit(1)"';
    const r = await buildPreview({
      repoPath: bare, branch: 'main', opId: 'op-2', previewsDir, buildCmd,
      draft: { slug: 'preview-test', content: 'x\n' },
    });
    assert.equal(r.ok, false);
    assert.ok(r.reason && r.reason.includes('build'));
    // 失败不得产生预览目录
    assert.ok(!fs.existsSync(path.join(previewsDir, 'op-2')));
    // 留证:失败日志含 stderr 输出
    const logFiles = fs.readdirSync(previewsDir).filter((f) => f.startsWith('op-2') && f.endsWith('.log'));
    assert.ok(logFiles.length === 1, `期望恰一份失败留证, got ${logFiles}`);
    const log = fs.readFileSync(path.join(previewsDir, logFiles[0]), 'utf8');
    assert.ok(log.includes('build-boom'));
    // worktree 同样清理,不留半成品
    const list = execFileSync('git', ['worktree', 'list', '--porcelain'], { cwd: bare, env: { ...process.env, HOME: dir } }).toString();
    assert.ok(!list.replace(/\\/g, '/').includes(dir.replace(/\\/g, '/') + '/wt-'));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('2.1 半成品中断:产物拷贝前失败 → previews/<op-id> 不得存在半目录', async () => {
  const dir = tmpDir();
  try {
    const { bare } = makeBareRepo(dir);
    const previewsDir = path.join(dir, 'previews');
    // 构建成功但不产 dist(模拟构建器坏输出)
    const buildCmd = 'node -e "fs=require(\'fs\')"';
    const r = await buildPreview({
      repoPath: bare, branch: 'main', opId: 'op-3', previewsDir, buildCmd,
      draft: { slug: 'preview-test', content: 'x\n' },
    });
    assert.equal(r.ok, false);
    assert.ok(!fs.existsSync(path.join(previewsDir, 'op-3')));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
