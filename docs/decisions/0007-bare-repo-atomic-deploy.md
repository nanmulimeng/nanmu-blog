# ADR-0007: 部署 = bare repo + post-receive 后台构建 + mv -T 原子 symlink

- 状态:部分被 [ADR-0009](0009-preimplementation-contracts.md) 取代;下文保留原决策历史,当前实现以spec与ADR-0009为准
- 日期:2026-10-02
- 关联:spec §7;模式来源 topic-digest 生产验证 + 部署调研补强

> 2026-10-04有效口径:取代范围:下文flock -n忙时跳过、/tmp锁路径及旧构建流程不可照抄。保留bare repo与原子切换决策;当前实现基线见[M0计划](../superpowers/plans/2026-10-02-m0-blog-launch.md),唯一操作入口见[部署手册](../ops/deploy.md)。

## 背景

单人开发、Windows 本地、Linux 服务器(1.8G 内存,Caddy 已占 80/443)。要求:push 即部署、可回滚、构建失败线上不受影响。

## 决策

- 服务器 bare repo `/opt/git/nanmu-blog.git`,post-receive hook **只认 refs/heads/main**(忽略删分支)
- hook 内 `flock -n /tmp/nanmu-blog-build.lock -c deploy.sh` **后台执行、立即返回**——push 不被 astro build 阻塞;并发 push 自动跳过后到者
- deploy.sh:`set -euo pipefail`,checkout 临时目录 → `npm ci --cache`(服务器留缓存)→ `astro build --outDir releases/<sha>/dist` → 清理临时目录
- **原子切换必须 `mv -T`**(先建 `current.tmp` 软链再 rename);`ln -f` 有 unlink 窗口,禁用
- 保留最近 5 个 release,更旧删除;回滚 = 切 symlink(分钟级)
- **构建失败不切换 symlink**:set -e 在切换前退出,线上保持旧版
- Caddy:`root * /var/www/nanmu-blog/current/dist` + file_server,symlink 对 web server 透明

## 理由

- topic-digest 生产验证的同款模式,运维心智统一
- `mv -T` 原子性有 strace 级论证(Austin Adams 的经典分析)
- 无 CI 外部依赖(无 GitHub 密钥管理),全部自持

## 后果(代价)

- 服务器需 node + npm 缓存(已具备,topic-digest 同款构建)
- 构建在 1.8G 服务器上跑(实测同量级峰值 241MB,无虞)

## 被否决的替代方案

1. GitHub Actions 构建、服务器只收产物——引入外部依赖与密钥管理;可作为未来优化项
2. rsync 直推 dist——无版本化、无回滚,否决
3. 服务器跑常驻 CI agent——重,否决
