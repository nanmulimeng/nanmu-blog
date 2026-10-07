"""校准 CLI(python -m nanmu_engine.calibrate --root <engine 根>)。

审计修正(2026-10-07)③:此前交接文档写了不存在的该命令——本模块补齐
真实执行入口。装配序=引擎同款单实例锁(root/run.lock,与 nanmu-run
互斥,防校准与运行并发写 engine.db)→ load_config(E1 配置错=退出 2)
→ connect_db+migrate → ops.calibrate(默认真实网络;transport 注入口
仅供测试替身)。结果处理:全部样本 usage≤ceil(计数×系数)→校准记录
绑定配置指纹生效,退出 0;任一超限→ops.calibrate 对账时已持久化置
pay_paused,退出 1;锁忙=退出 1(与 run 同码)。同身份(calibration:
样本+系数)已有结算回执的样本直接复用,重跑零新增付费(幂等契约见
ops.calibrate docstring)。
"""

from __future__ import annotations

import logging
from pathlib import Path

from nanmu_engine.config import ConfigError, load_config
from nanmu_engine.db import connect_db, migrate
from nanmu_engine.ledger import sync_budget_limits
from nanmu_engine.ops import calibrate
from nanmu_engine.run import acquire_instance_lock

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None, *, transport=None) -> int:
    """CLI 装配薄层;退出码 0=校准生效 / 1=未通过或锁忙 / 2=配置错误。"""
    import argparse

    # 观测性:与 run.main 同款 handler,journalctl 巡检依赖 stage=/event=
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    parser = argparse.ArgumentParser(prog="nanmu-calibrate")
    parser.add_argument("--root", default=".", help="engine 根目录")
    args = parser.parse_args(argv)
    root = Path(args.root)

    lock = acquire_instance_lock(root / "run.lock")
    if lock is None:
        logger.error("stage=calibrate event=lock_busy 另一实例运行中,退出")
        return 1

    try:
        try:
            config = load_config(root)
        except ConfigError as exc:
            logger.error("stage=calibrate event=E1.config message=%s", exc)
            return 2
        conn = connect_db(str(root / "engine.db"))
        migrate(conn)
        # 新库自举:migrate 不建 budget 行,authorize 视行缺失为配置错
        # (key_missing 拒)。校准是未校准库的第一付费入口,须从 config
        # 同步限额行(幂等),与既有库上最新 config 对齐。
        sync_budget_limits(conn, config)
        try:
            out = calibrate(conn, config, transport=transport)
        finally:
            conn.close()
        if out.get("passed"):
            logger.info("stage=calibrate event=passed status=%s samples=%d",
                        out.get("status"), len(out.get("results", [])))
            return 0
        logger.error("stage=calibrate event=%s 校准未通过,详见"
                     " engine_meta.calibration(超限时已置 pay_paused)",
                     out.get("status"))
        return 1
    finally:
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
