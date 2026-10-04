# 服务器与开发环境事实

> 部署与排障前必读。2026-10-02文档审查未登录服务器。下表中2026-08-31数据来自上游验收报告,2026-10-02巡检值为上一会话转述[declared],部署前必须复核。

## 服务器(123.56.223.97)

| 项 | 事实 |
|----|------|
| 提供商 | 阿里云 |
| 系统 | Alinux 3 |
| systemd | **239**为历史版本记录;曾记录带时区表达式失败,本机原因未复现。暂沿用裸本地时间,先核对Asia/Shanghai与next elapse |
| 内存 | 1.8G + 2G swap;上一会话记录2026-10-02 used 426Mi / available 1444Mi,load 0[declared] |
| 磁盘 | 上一会话记录32%已用(2026-10-02)[declared] |
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

- 公网入口采用Caddy自动HTTPS。备案条件为此前设计期转述,当前文档未保存完整官方出处与账户核查证据;域名归属、ICP备案/接入及公安备案适用要求在M0上线前分别核实,不以“子域名”三个字推定全部条件已满足。
- 部分外网信源(OpenAI Blog 等)可达性由 topic-digest 每小时实测,失败被容忍

## 开发机

| 项 | 事实 |
|----|------|
| 系统 | Windows 11 + Git Bash(注意:hook/shell 脚本必须 LF,.gitattributes 已强制) |
| SSH | OpenSSH 可用;免密部署靠公钥(M0 Task 9 配置) |
| 本地仓库 | nanmu-blog 主仓库;`D:\software\item\topic-digest`(上游,只读参考);`D:\software\item\nanmuli-blog`(废弃旧项目,历史参考) |

## 服务器 node(部署依赖)

- node 存在且能跑 astro build:topic-digest 同机构建实测峰值 241MB [verified: 2026-08-31 验收]
- 上游m0-report记录2026-08-31 Node v20.18.1;旧部署手册安装到/usr/local。当前版本/路径仍[declared],M0 Task 9核查所选Astro包engines与真实PATH;不可因博客需要而直接替换同机公共Node。本项目deploy/工件已在Task8落盘并做本地语法验证,尚未安装到服务器

## 事实更新纪律

本文是环境事实的唯一记录处:每次巡检/部署后把过期的行改掉并更新日期;新增未验证条目必须标 [declared]。

## M0/M1部署前只读核查

- M0:运行用户、Node/npm/bash/git/flock/timeout版本和路径、Caddy版本、当前站点配置与现有站点基线HTTP状态、Asia/Shanghai时区、磁盘/内存。主域证书不自动覆盖子域,让Caddy为blog主机名申请证书并实测。
- M1:上游unit/环境中的DB路径、运行用户及DB/WAL/SHM读取权限、源状态与正文覆盖率;Python内置sqlite版本与sqlite CLI版本分开记录。
- `/run/lock` 的父目录权限可能不允许普通用户新建锁(上游验收已记录此坑);用本项目可写目录或预建锁文件,重启后再验收。
- timer继续用裸本地时间作为本机兼容策略,在目标机验证解析/next elapse;不把旧验收的经验扩展成未经查证的全版本支持断言。
- 本项目通知独立使用 `/etc/nanmu-blog.env`,只保存变量引用到仓库;不趁机修topic-digest告警或异地备份。
- 服务器bare repo仅备份开发机代码。engine.db需Online Backup和恢复测试;rag.db可从已发布语料重建;同机备份不能抵抗整机丢失,异地数据库备份仍是显式欠账。

## 2026-10-04证据边界修正

[systemd v239官方文档](https://github.com/systemd/systemd/blob/v239/man/systemd.time.xml)的Calendar Events章节明确支持IANA时区。历史失败不能直接归因为上游239不支持;本机发行版、表达式写法与实际时区仍待现场核查,此修订不改变服务器配置。

环境表的系统/用户/服务/清理结果均为历史记录,不是本轮在线探测。以后更新关键项按“值、核查时间(含时区)、证据命令/日志位置”一起记录;Node/npm/Git/Caddy/Python及Python内置SQLite分别记录,不要用sqlite CLI版本替代Python运行时。备案核查只记录结论、日期与官方来源,不把账号信息写进文档。
