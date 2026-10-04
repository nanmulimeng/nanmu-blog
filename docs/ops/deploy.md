# M0部署手册

> 状态:2026-10-04 工件已落盘版。Task8 工件(post-receive/deploy.sh/Caddyfile.snippet)已提交并通过 `bash -n` 语法检查,路径/锁/npm缓存/日志/release.txt/回滚口径已与本文逐项核对一致;服务器尚未按本手册安装验收,Task9-10执行并留下证据后才能标为已验收。脚本实现基线在[M0计划](../superpowers/plans/2026-10-02-m0-blog-launch.md),本文只维护操作流程,不复制实现。

范围:仅nanmu-blog的bare repo、构建产物与新增Caddy站点块。保持topic-digest和nanmu-skill-mcp现状。所有远程操作须在部署任务授权内执行;本机使用Git Bash,服务器使用Bash,不要将PowerShell/CMD语法混入。

## 0. 前置核查与目标清单

| 目标 | 预期位置/主体 | 权限与验收 |
|------|---------------|-------------|
| SSH/构建用户 | nanmu@123.56.223.97 | 当前用户/组和sudo能力现场核对 |
| 接收仓库 | /opt/git/nanmu-blog.git | nanmu可写,HEAD为main |
| 发布根 | /var/www/nanmu-blog | nanmu可写;Caddy可遍历,不要求Caddy可写 |
| 构建锁 | /var/www/nanmu-blog/build.lock | 所有发布/回滚用同一文件,不能删除持有中的锁文件 |
| npm缓存 | /opt/git/nanmu-blog-npm-cache | 本项目专用,不修改已有项目缓存属主 |
| 构建日志 | /var/www/nanmu-blog/deploy.log | nanmu可写;M0巡检检查大小并按需轮转 |
| Caddy配置 | /etc/caddy/Caddyfile | 先确认unit确实读取此文件;不能仅凭默认路径覆盖 |

本机只读探针:

```bash
ssh -o ConnectTimeout=10 nanmu@123.56.223.97 'set -eu; id; node -v; npm -v; git --version; command -v node; command -v git; command -v flock; command -v timeout; caddy version; timedatectl show -p Timezone; systemctl show caddy -p User -p FragmentPath'
```

逐项记录实际结果,某条失败不能被最后一条成功掩盖。核对已锁Astro包engines,非登录shell能找到Node,目标磁盘/内存够用,现有skills入口HTTP状态作为基线。不要输出完整env或含凭据的配置到session。若unit读取其他配置文件,先修本文目标再继续。

本机前置:M0 Task8a的原始路径/slug与缓存边界已验收、`npm run verify`绿、工作区内容明确、锁文件已提交。当前Task8a仍待实施,普通verify绿不能替代它。不存在`deploy/post-receive`、`deploy/deploy.sh`、`deploy/Caddyfile.snippet`时停在Task8,不能将文档代码块当已安装工件。

## 1. 准备目录和接收仓库(服务器)

先用`ls -ld`核对精确目标是否已存在。已有目标先检查属主/内容并复用,不要重新初始化或递归chown。以下只适用于确认尚不存在的本项目路径:

```bash
sudo install -d -m 0755 -o nanmu -g nanmu /opt/git/nanmu-blog.git /opt/git/nanmu-blog-npm-cache /var/www/nanmu-blog /var/www/nanmu-blog/releases || exit 1
git init --bare -b main /opt/git/nanmu-blog.git
```

父目录`/var/www/nanmu-blog`也需nanmu可写以创建lock/log/symlink,单独核对属主;新建时用同样`install -d`明确设置。不要给整个`/opt/git`开放写权限。发布脚本会将新release根设为755、静态产物设为可读可遍历;`mktemp -d`的700权限不能直接作为Caddy发布目录使用。

## 2. 安装脚本(本机发起)

```bash
(
  set -euo pipefail
  cd "$(git rev-parse --show-toplevel)"
  bash -n deploy/post-receive
  bash -n deploy/deploy.sh
  scp deploy/post-receive deploy/deploy.sh nanmu@123.56.223.97:/opt/git/nanmu-blog.git/hooks/
  ssh nanmu@123.56.223.97 'chmod 755 /opt/git/nanmu-blog.git/hooks/post-receive /opt/git/nanmu-blog.git/hooks/deploy.sh'
)
```

上面的直传仅用于首次安装且尚无构建。首次安装前确认目标无自定义hook。升级时暂停所有发布者(含M1 timer),按§7确认无等待/运行任务,取得同一build.lock,备份旧hook到唯一时间戳路径;新脚本先上传到不同文件名,语法验证、chmod成功后再rename替换,不覆盖进程正在读取的脚本。两个文件全部安装并核对版本后才恢复发布。Git推送不会自动更新bare repo的hooks,必须记录安装工件所属commit;LF与执行权限缺一不可。

## 3. SSH免密与remote(本机Git Bash)

使用已有公钥;没有时再生成,不得覆盖现有key。密码仅交互输入,不落盘。若服务器已装同一公钥不重复追加。

```bash
cat "$HOME/.ssh/id_ed25519.pub" | ssh nanmu@123.56.223.97 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys'
ssh -o BatchMode=yes -o ConnectTimeout=10 nanmu@123.56.223.97 true
git remote -v
# 仅确认server不存在时添加;已存在则核对URL,不直接覆盖
git remote add server nanmu@123.56.223.97:/opt/git/nanmu-blog.git
```

失败时按计划Task9诊断公钥、目录权限和服务端日志。bundle是显式降级:fetch不会触发post-receive,必须手动带锁构建;未完成push自动部署时不能宣称M0正式验收通过。

## 4. DNS

核对域名归属/备案与实际接入条件,添加A记录blog.nanmu.xyz到目标IP。`nslookup blog.nanmu.xyz`检查解析;若有AAAA也必须核对,不能让客户端走错误IPv6。不要修改skills已有记录。DNS/公网验证未完成可继续本地构建与独立验收,不能把临时入口算正式站点上线。

## 5. Caddy候选配置、验证与加载(服务器)

先准备候选文件,首次启用博客块前按§6生成可读取的current。不要对运行配置直接反复追加snippet。

本机将snippet上传到本项目根,避免不受控的共享临时文件名:

```bash
scp deploy/Caddyfile.snippet nanmu@123.56.223.97:/var/www/nanmu-blog/Caddyfile.snippet
```

服务器上,确认没有并行修改Caddy配置,并检查站点块尚未存在;已存在时编辑候选中的原块,不追加第二份:

```bash
stamp=$(date +%Y%m%d%H%M%S)
backup="/etc/caddy/Caddyfile.nanmu-blog.$stamp.bak"
candidate="/etc/caddy/Caddyfile.nanmu-blog.$stamp.candidate"
sudo test ! -e "$backup" && sudo test ! -e "$candidate" || exit 1
sudo cp -p /etc/caddy/Caddyfile "$backup" || exit 1
sudo cp -p /etc/caddy/Caddyfile "$candidate" || exit 1
# 确认尚无blog站点块后执行;已有则用编辑器修改candidate
printf '\n' | sudo tee -a "$candidate" >/dev/null
sudo tee -a "$candidate" < /var/www/nanmu-blog/Caddyfile.snippet >/dev/null || exit 1
sudo caddy validate --config "$candidate" --adapter caddyfile || exit 1
```

只有validate成功且候选diff只包含本项目站点变化才替换配置并reload。validate失败保留原配置、不reload;不要因为命令分行就继续执行后续写入。现场存在相对import或环境依赖时,验证必须使用服务相同的上下文。

```bash
sudo cp -p "$candidate" /etc/caddy/Caddyfile || exit 1
if ! sudo systemctl reload caddy; then
  sudo cp -p "$backup" /etc/caddy/Caddyfile
  sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && sudo systemctl reload caddy
  echo '新配置加载失败,已尝试恢复;检查服务状态与日志' >&2
  exit 1
fi
systemctl is-active caddy
```

记录backup精确路径。服务active不等于业务正常,继续核对blog HTTPS、skills变更前基线、TLS及404真实状态。官网说明:[validate/reload](https://caddyserver.com/docs/command-line)、[Linux服务与文件权限](https://caddyserver.com/docs/running#linux-service)。

## 6. 首次开通与常态发布确认

首次开通先push生成current,观察日志并验证实际Caddy用户可读,再加载§5候选配置、确认DNS/TLS与页面;人工开通不计入180秒指标。日志无进展时按§8诊断,不无限等待。后续常态发布才执行下面计时块:环境已配置、目标main分支与暂存内容已核对。push返回只说明接收,锁等待最长900秒、构建最长900秒是故障上限;正常M0验收要求180秒内可见。

```bash
start=$(date +%s)
test "$(git branch --show-current)" = main || exit 1
expected=$(git rev-parse refs/heads/main) || exit 1
git push server main || exit 1
ssh nanmu@123.56.223.97 'tail -30 /var/www/nanmu-blog/deploy.log; readlink /var/www/nanmu-blog/current'
```

如还未建立current,在有界等待中查看日志;首次冷安装失败先定位,不急着启用Caddy块。用实际Caddy运行用户在服务器检查`test -r /var/www/nanmu-blog/current/dist/index.html`及父目录遍历权限;属主nanmu能读取不能替代此验收。

公开站点启用后在本机轮询,最多180秒,超时留下失败证据:

```bash
ok=0
while [ $(( $(date +%s) - start )) -lt 180 ]; do
  observed=$(curl --fail --silent --show-error --max-time 10 https://blog.nanmu.xyz/release.txt) || observed=''
  if [ "$observed" = "$expected" ]; then ok=1; break; fi
  sleep 5
done
elapsed=$(( $(date +%s) - start ))
printf 'published=%s elapsed=%ss expected=%s\n' "$ok" "$elapsed" "$expected"
[ "$ok" = 1 ] && [ "$elapsed" -le 180 ]
```

首篇正式计时在Task10已配置好的环境进行,不把人工DNS/Caddy开通时间混入常态发布指标。还需首页200、两条RSS可解析、文章/日报空态、草稿不存在、随机不存在URL为404以及skills基线正常。

## 7. 回滚

先停止新push(含M1自动发布)。在服务器用`ps -eo pid,ppid,args`检查本项目精确路径关联的nohup/bash/flock/timeout/deploy进程,包括正在等待锁的任务;检查不清楚时不回滚。锁空闲不代表没有排队任务,不能只用一次flock探针判断。待相关任务自然完成或按已核对PID处理并留下证据后,选有`.complete`的完整旧SHA。下例再次取得同一锁以排除竞争,不要删当前版本或锁文件:

```bash
rollback_sha='REPLACE_WITH_VERIFIED_40_HEX_SHA'
[[ "$rollback_sha" =~ ^[0-9a-f]{40}$ ]] || exit 1
export rollback_sha
flock -E 75 -w 900 /var/www/nanmu-blog/build.lock bash -c '
  set -eu
  target="/var/www/nanmu-blog/releases/$rollback_sha"
  test "$(cat "$target/.complete")" = "$rollback_sha" || exit 1
  test "$(cat "$target/dist/release.txt")" = "$rollback_sha" || exit 1
  ln -sfn "$target" /var/www/nanmu-blog/current.tmp
  mv -T /var/www/nanmu-blog/current.tmp /var/www/nanmu-blog/current
'
```

复核release.txt、首页和RSS。临时回滚不会移动bare repo main,下次部署会恢复main;长期撤回用本地revert、verify、push。M1须同步核对日报期状态,已公布费用不因内容回滚删除。

## 8. 超时、失败与手动重跑

```bash
ssh nanmu@123.56.223.97 'flock -E 75 -w 900 /var/www/nanmu-blog/build.lock timeout -k 30s 900s /opt/git/nanmu-blog.git/hooks/deploy.sh >> /var/www/nanmu-blog/deploy.log 2>&1'
```

原样push可能up-to-date,不会重新触发hook。失败后检查日志、远端main、current与.complete;目录存在不代表构建完成。残留`.build.*`和不完整版本先列目标并确认没有进程使用再清理,不能用宽泛通配删除整个release根。

故障注入仅在计划Task9的独立验收仓库/目录,生产main始终可验证。完成后把版本、时间、退出码、线上SHA、HTTP状态、回滚和权限结果写入session,回填环境事实并更新本文状态。
