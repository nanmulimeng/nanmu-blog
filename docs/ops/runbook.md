# 运维 runbook(巡检/回滚/故障)

> 状态:定稿 2026-10-02。部署步骤见 [deploy.md](deploy.md)(随 M0 Task 8 落盘)。
> 服务器:123.56.223.97(user nanmu,sudo NOPASSWD)。凭据不落盘。

## 巡检

| 频率 | 动作 | 正常标准 |
|------|------|----------|
| 每日(1 分钟) | `curl -sI https://blog.nanmu.xyz`;M1 后看昨日日报是否发布 | 200;日报存在 |
| 每周 | `ssh nanmu@123.56.223.97 'journalctl -u nanmu-blog-engine --since "-7d" | grep -i error'`;备份目录有新文件且大小正常 | 无 error;备份连续 |
| 每月 | 更新 docs/engine/budget.md 月度台账;核对 api_usage 月聚合 | < ¥40 |

## 回滚(分钟级)

1. 列版本:`ssh nanmu@123.56.223.97 'ls -1dt /var/www/nanmu-blog/releases/*'`
2. 切换:
   ```
   ln -sfn /var/www/nanmu-blog/releases/<旧sha> /var/www/nanmu-blog/current.tmp
   mv -T /var/www/nanmu-blog/current.tmp /var/www/nanmu-blog/current
   ```
3. 验证:`curl -s https://blog.nanmu.xyz/ | head` + rss

内容级回滚(某篇文章有问题):直接 `git revert` 再 push,重新走构建链。

## 故障处理

| 症状 | 定位 | 处理 |
|------|------|------|
| 站点不可达 | `systemctl status caddy`;DNS 解析 | Caddy reload / 查 DNS。静态站无进程,自身极少故障 |
| push 后未更新 | `ssh ... 'tail -30 /opt/git/nanmu-blog-deploy.log'` | 构建失败看日志修复;若并发被 flock 跳过,稍后重推 |
| 日报未出 | `journalctl -u nanmu-blog-engine --since today` | LLM 故障 → 等下期;连续 2 期失败 → 人工跑 engine 并查 receipt unknown 堆积 |
| 成本异常 | engine.db:`SELECT month,model,cost_cny FROM api_usage ORDER BY month DESC` | 查 unknown 回执;必要时 budget 对应档调 0 停用 |
| topic-digest 读失败 | 其自身 health 输出 | 只影响当天日报;铁律 4 不动它,等其恢复 |
| 服务器内存告急 | `free -m` | RAG 服务 MemoryMax=200M 兜底;build 峰值实测 241MB |

## 通知

- OnFailure 通知凭据配置后(随 M1 部署),engine/build 失败自动通知
- 通知未武装期间(现在):靠每周巡检兜底——这是已知欠账,记录在 spec §7
