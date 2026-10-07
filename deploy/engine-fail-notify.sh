#!/usr/bin/env bash
# engine OnFailure 告警(Task 25):失败事实写 journal;配置了
# NANMU_NOTIFY_WEBHOOK(ServerChan 兼容 GET,值为完整 .send URL)时
# 同时推送。业务级去重(E1/E2 连续期/月预警)由 engine 进程内
# notify_sent 表承担,本脚本只做进程级失败信号,不做去重。
# curl 失败不阻塞(exit 0)——告警失败不应让告警 unit 自身报错
# 掩盖原始失败。
set -u

summary="nanmu-blog engine run FAILED at $(date -Is) on $(hostname)"
systemd-cat -t nanmu-blog-engine -p err <<< "$summary"

webhook="${NANMU_NOTIFY_WEBHOOK:-}"
if [ -n "$webhook" ]; then
    # GET + urlencode 参数(ServerChan 形态);超时 15s;失败仅记 journal
    if curl -fsS --max-time 15 --get "$webhook" \
        --data-urlencode "title=nanmu-blog 引擎运行失败" \
        --data-urlencode "desp=${summary}" >/dev/null 2>&1; then
        systemd-cat -t nanmu-blog-engine <<< "alert pushed via webhook"
    else
        systemd-cat -t nanmu-blog-engine -p err \
            <<< "webhook alert failed (original failure: $summary)"
    fi
fi
exit 0
