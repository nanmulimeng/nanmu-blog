# 服务器与开发环境事实

> 部署与排障前必读。事实截至 2026-10-02(巡检实测);标注 [declared] 的条目未实测,使用前先核实。

## 服务器(123.56.223.97)

| 项 | 事实 |
|----|------|
| 提供商 | 阿里云 |
| 系统 | Alinux 3 |
| systemd | **239**(OnCalendar 不支持时区后缀——timer 里写 `08:30` 而非 `08:30 Asia/Shanghai`,topic-digest 已踩坑) |
| 内存 | 1.8G + 2G swap;2026-10-02 实测 used 426Mi / available 1444Mi,load 0 |
| 磁盘 | 32% 已用(2026-10-02) |
| 用户 | nanmu,sudo NOPASSWD |
| 凭据政策 | **密码只在交互式命令行输入,禁止出现在任何文件/脚本/配置/日志/文档** |

### 在跑服务(动工前先知道谁在这儿)

| 服务 | 端口/入口 | 说明 |
|------|-----------|------|
| Caddy | 80/443 | 全局入口,自动 HTTPS;nanmu-blog 上线后加 `blog.nanmu.xyz` 站点块 |
| topic-digest 站点 | nginx 8080 + basicauth | 上游数据源的展示端 |
| topic-digest timers | systemd | hourly ingest + 每日 release 构建(9 月 720/720 全绿) |
| nanmu-skill-mcp | 3456(skills.nanmu.xyz) | **用户在用的 MCP 服务,保留勿动** |

### topic-digest 服务器布局(本项目 engine 只读它的 SQLite)

- bare repo:`/opt/git/topic-digest.git`;代码同步走 **git bundle 传输**(`git remote add server` 直连 push 从未走通,历史事实)
- SQLite:本地文件(具体路径未核实 [declared],M1 实施时确认并回填本文)
- 备份:标准库 `conn.backup()` 每日本地、保留 30 天(约 244M);**无异地备份**(已知欠账)
- 通知:`/etc/topic-digest.env` 不存在 → OnFailure 告警未武装(已知欠账)

### 已清理(2026-08-31)

旧 nanmuli-blog 全家(Java/PG15/Redis/部署包、Caddy IP 站块、gcc-toolset)已卸载;dump 备份在开发机 `C:\tmp\server-cleanup-backup\`。服务器上不再有 Java/PG/Redis。

### 网络

- 大陆服务器:公网域名必须走 Caddy 自动 HTTPS;**子域名免单独备案**(主域名已有 ICP 备案即可,阿里云官方口径,2026-10-02 核实)
- 部分外网信源(OpenAI Blog 等)可达性由 topic-digest 每小时实测,失败被容忍

## 开发机

| 项 | 事实 |
|----|------|
| 系统 | Windows 11 + Git Bash(注意:hook/shell 脚本必须 LF,.gitattributes 已强制) |
| SSH | OpenSSH 可用;免密部署靠公钥(M0 Task 9 配置) |
| 本地仓库 | nanmu-blog 主仓库;`D:\software\item\topic-digest`(上游,只读参考);`D:\software\item\nanmuli-blog`(废弃旧项目,历史参考) |

## 服务器 node(部署依赖)

- node 存在且能跑 astro build:topic-digest 同机构建实测峰值 241MB [verified: 2026-08-31 验收]
- 具体版本与安装方式(系统包 or nvm)未核实 [declared]——M0 Task 9 §0 首步核实;deploy.sh 已做 nvm PATH 兼容

## 事实更新纪律

本文是环境事实的唯一记录处:每次巡检/部署后把过期的行改掉并更新日期;新增未验证条目必须标 [declared]。
