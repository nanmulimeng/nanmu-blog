"""校准通道测试(种子=model-calls §3 规则 11/验收 11;替身)。

例外范围唯一:purpose='calibration' 是"校准未完成→拒新增付费"的唯一
豁免;正式管线(score/understand)授权前置=校准状态对**当前配置**生效。
校准调用走完整账本(窗口/月预算/pay_paused 照常,计入不绕闸门);记录
绑定 {model, tokenizer 资源与版本, 计数方式, 系数, 样本对账结果, 判定
时刻}——任一项变化即失效须重校准。任一 ratio>1→停新增置 pay_paused
(持久化,重启仍拒)。
"""

import dataclasses
import itertools
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from nanmu_engine.config import load_config
from nanmu_engine.db import connect_db, migrate
from nanmu_engine.ledger import (authorize, calibration_effective,
                                 calibration_fingerprint,
                                 sync_budget_limits)
from nanmu_engine.ops import calibrate

ENGINE_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def env(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    config = load_config(ENGINE_ROOT)
    sync_budget_limits(conn, config)
    return conn, config


def _authorize(conn, config, purpose="score", **over):
    kw = dict(purpose=purpose, model="deepseek-flash",
              request_hash="h" * 64, identity_key="url:https://e.com/a",
              token_count=1000, issue_date="2026-10-06", origin="initial",
              now=NOW)
    kw.update(over)
    return authorize(conn, config, **kw)


def _transport(prompt_tokens):
    """替身:每请求返回可控 usage.prompt_tokens(计分形态响应)。"""
    seq = itertools.count(1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": f"r{next(seq)}",
            "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps({"attentionScore": 50})}}],
            "usage": {"prompt_tokens": prompt_tokens,
                      "completion_tokens": 5,
                      "prompt_cache_hit_tokens": 0,
                      "prompt_cache_miss_tokens": prompt_tokens}})
    return httpx.MockTransport(handler)


def _meta(conn, key):
    row = conn.execute("SELECT value FROM engine_meta WHERE key=?",
                       (key,)).fetchone()
    return row[0] if row else None


def _set_meta(conn, key, value):
    with conn:
        conn.execute(
            "INSERT INTO engine_meta (key, value, updated_utc)"
            " VALUES (?, ?, datetime('now'))"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value))


def _cal_attempts(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM receipt_attempt a JOIN receipt r"
        " ON r.id=a.receipt_id WHERE r.purpose='calibration'").fetchone()[0]


def _db_path(conn):
    return conn.execute("PRAGMA database_list").fetchone()[2]


# ---------- 验收 11-1:例外唯一(未校准拒正式,calibration 豁免) ----------

def test_uncalibrated_rejects_formal_but_calibration_exempt(env):
    conn, config = env
    assert (_authorize(conn, config, purpose="score").status,
            _authorize(conn, config, purpose="score").reject_reason) == \
        ("rejected", "not_calibrated")
    assert _authorize(conn, config, purpose="understand").reject_reason \
        == "not_calibrated"
    r = _authorize(conn, config, purpose="calibration",
                   identity_key="calibration:sample-0")
    assert r.status == "reserved"            # 唯一例外,其余闸门照常


# ---------- 验收 11-2:通过→绑定记录落 engine_meta+状态生效 ----------

def test_calibrate_pass_binds_record_and_activates(env):
    conn, config = env
    out = calibrate(conn, config, transport=_transport(10), now=NOW)
    assert out["status"] == "passed" and out["passed"] is True
    rec = json.loads(_meta(conn, "calibration"))
    assert rec["passed"] is True and rec["coefficient"] == 1.0
    assert rec["fingerprint"] == calibration_fingerprint(config)
    assert rec["fingerprint"]["model"] == config.budget.default_model
    assert rec["fingerprint"]["tokenizer_version"]
    assert rec["decided_at"]
    assert len(rec["results"]) == 4          # 3 最小合成+1 真实短文
    assert calibration_effective(conn, config) is True
    assert _authorize(conn, config).status == "reserved"
    assert _cal_attempts(conn) == 4          # 账本中可查


# ---------- 验收 11-3:样本超预占计数→停新增(持久化,重启仍拒) ----------

def test_calibrate_ratio_over_pauses_pay_persistently(env):
    conn, config = env
    out = calibrate(conn, config, transport=_transport(999_999), now=NOW)
    assert out["status"] == "failed" and out["passed"] is False
    assert any(r["prompt_tokens"] > r["reserved_count"] for r in out["results"])
    # 持久化:全新连接直读文件
    fresh = sqlite3.connect(_db_path(conn))
    assert fresh.execute("SELECT value FROM engine_meta WHERE"
                         " key='pay_paused'").fetchone()[0] == "1"
    fresh.close()
    # 重启(新连接)仍拒:校准通道自身也被闸门挡住
    conn2 = connect_db(_db_path(conn))
    assert _authorize(conn2, config, purpose="calibration",
                      identity_key="calibration:sample-9",
                      request_hash="z" * 64).reject_reason == "pay_paused"
    # 失败记录也落(判定事实)
    assert json.loads(_meta(conn, "calibration"))["passed"] is False
    conn2.close()


# ---------- 验收 11-4:校准预算耗尽→中止不追加 ----------

def test_calibrate_budget_exhausted_aborts_without_new_attempts(env):
    conn, config = env
    tiny = dataclasses.replace(
        config, budget=dataclasses.replace(
            config.budget, calibration_budget_micro_cny=1))  # 极小上限
    out = calibrate(conn, tiny, transport=_transport(10), now=NOW)
    assert out["status"] == "budget_exhausted"
    assert _cal_attempts(conn) == 0          # 不追加任何调用
    assert calibration_effective(conn, config) is False


# ---------- 验收 11-5:计入窗口与月预算(不绕闸门断言) ----------

def test_calibrate_counts_toward_windows_and_monthly(env, tmp_path):
    conn, config = env
    cfg = dataclasses.replace(config, budget=dataclasses.replace(
        config.budget, rate_limits=dataclasses.replace(
            config.budget.rate_limits, per_minute=2)))
    sync_budget_limits(conn, cfg)
    out = calibrate(conn, cfg, transport=_transport(10), now=NOW)
    assert out["status"] == "gate_rejected:window"   # 第 3 样本被窗口拒
    assert _cal_attempts(conn) == 2

    conn2 = connect_db(str(tmp_path / "engine2.db"))
    migrate(conn2)
    cfg2 = dataclasses.replace(config, budget=dataclasses.replace(
        config.budget, monthly_micro_cny=10))        # 极小月额
    sync_budget_limits(conn2, cfg2)
    out2 = calibrate(conn2, cfg2, transport=_transport(10), now=NOW)
    assert out2["status"] == "gate_rejected:money"   # 月预算照常适用
    assert _cal_attempts(conn2) == 0
    conn2.close()


# ---------- 验收 11-6:绑定项任一变化→失效须重校准 ----------

def test_state_invalidates_on_any_binding_change(env):
    conn, config = env
    assert calibrate(conn, config, transport=_transport(10), now=NOW)["passed"]

    other = dataclasses.replace(config, budget=dataclasses.replace(
        config.budget, default_model="other-model"))     # 换模型
    assert calibration_effective(conn, other) is False
    assert _authorize(conn, other).reject_reason == "not_calibrated"

    tok = config.budget.tokenizers[config.budget.default_model]
    tok_cfg = dataclasses.replace(config, budget=dataclasses.replace(
        config.budget, tokenizers={
            **config.budget.tokenizers,
            config.budget.default_model: dataclasses.replace(
                tok, version="f" * 64)}))                # 只改 config 声明
    # R3:指纹绑实际加载源(TOKENIZER_MAP)——声明改动而加载未变,计数
    # 行为未变,校准不失效(失效条件=实际加载的资源/版本变化)
    assert calibration_effective(conn, tok_cfg) is True

    rec = json.loads(_meta(conn, "calibration"))
    rec["fingerprint"]["counting"] = "legacy_chars_v0"   # 改计数方式
    _set_meta(conn, "calibration", json.dumps(rec, ensure_ascii=False))
    assert calibration_effective(conn, config) is False

    rec["fingerprint"]["counting"] = calibration_fingerprint(
        config)["counting"]                              # 还原,改系数
    _set_meta(conn, "calibration", json.dumps(rec, ensure_ascii=False))
    _set_meta(conn, "calibration_coefficient", "1.5")    # 人工上调系数
    assert calibration_effective(conn, config) is False
    assert _authorize(conn, config).reject_reason == "not_calibrated"


# ---------- R3(P1-3):计量证据/同身份复用/指纹绑实际加载资源 ----------

def test_missing_usage_is_not_pass_evidence(env):
    """R3:响应无 usage.prompt_tokens=未取得计量证据——"没有观察到超量"
    不等于"已取得通过证据",不得 passed(校准是付费链路的前置闸)。"""
    conn, config = env
    seq = itertools.count(1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": f"r{next(seq)}",
            "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps({"attentionScore": 50})}}],
            "usage": {"completion_tokens": 5}})      # 无 prompt_tokens/分项
    out = calibrate(conn, config, transport=httpx.MockTransport(handler),
                    now=NOW)
    assert out["passed"] is False
    assert out["status"] == "missing_usage"
    assert calibration_effective(conn, config) is False
    assert json.loads(_meta(conn, "calibration"))["passed"] is False


def test_repeat_calibration_reuses_settled_receipts(env):
    """R3:同身份(样本+系数+配置)重校准复用已结算回执的账本结果,
    零网络零新增付费 attempt(logical_key 须与账本写入格式一致)。"""
    conn, config = env
    out1 = calibrate(conn, config, transport=_transport(10), now=NOW)
    assert out1["passed"] is True and _cal_attempts(conn) == 4

    calls = []
    counting = httpx.MockTransport(
        lambda req: (calls.append(1), httpx.Response(200, json={
            "id": "x", "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps({"attentionScore": 50})}}],
            "usage": {"prompt_tokens": 999_999, "completion_tokens": 5,
                      "prompt_cache_hit_tokens": 0,
                      "prompt_cache_miss_tokens": 999_999}}))[1])
    out2 = calibrate(conn, config, transport=counting, now=NOW)
    assert out2["passed"] is True
    assert _cal_attempts(conn) == 4                  # 零新增 attempt
    assert all(r["reused"] for r in out2["results"])
    assert calls == []                               # 零网络(replay 命中)


def test_fingerprint_binds_loaded_resource_not_config_claim(env):
    """R3:指纹描述实际加载的 tokenizer(TOKENIZER_MAP),不是 config
    声明——声明改动而实际加载未变,计数行为未变,校准不失效。"""
    conn, config = env
    tok = config.budget.tokenizers[config.budget.default_model]
    claimed = dataclasses.replace(config, budget=dataclasses.replace(
        config.budget, tokenizers={
            **config.budget.tokenizers,
            config.budget.default_model: dataclasses.replace(
                tok, version="f" * 64)}))
    assert calibration_fingerprint(claimed) == calibration_fingerprint(config)


def test_calibration_budget_counts_pending_reservations(env):
    """R3(锁定):校准预算按已批准预占口径核算——未结算的校准预占
    (actual NULL)按 reserved 保守计入,不得因"已结算=0"放行新样本。"""
    conn, config = env
    probe = _authorize(conn, config, purpose="calibration",
                       identity_key="calibration:probe",
                       request_hash="p" * 64, issue_date=None)
    assert probe.status == "reserved"
    tiny = dataclasses.replace(
        config, budget=dataclasses.replace(
            config.budget, calibration_budget_micro_cny=probe.reserved_micro_cny + 1))
    out = calibrate(conn, tiny, transport=_transport(10), now=NOW)
    assert out["status"] == "budget_exhausted"       # 首样本即按预占计被拒
    assert _cal_attempts(conn) == 1                  # 只有 probe,零追加


# ==================== 交界核验轮(A1/A2:校准通道×账本复用) ====================

def _net_down():
    def handler(request):
        raise httpx.ConnectError("net down", request=request)
    return httpx.MockTransport(handler)


# ==================== 复核轮(校准 replay 有效性/预算口径) ====================

def _http400_with_usage():
    """替身:HTTP 400(no_retry)但 body 带 usage——失败回执带费用证据
    的形态(record_failure 会把它写进 usage_json)。"""
    def handler(request):
        return httpx.Response(400, json={
            "error": {"message": "bad request"},
            "usage": {"prompt_tokens": 5, "completion_tokens": 0,
                      "prompt_cache_hit_tokens": 0,
                      "prompt_cache_miss_tokens": 5}})
    return httpx.MockTransport(handler)


def test_calibration_failed_attempt_with_usage_not_pass_evidence(env):
    """复核 P1:带 usage 的失败回执是费用证据,不是通过样本——replay
    只认成功(received)attempt;失败样本重走 can_retry(no_retry 拒),
    不因 usage_json 非空被当已通过,一次失败请求不得变成校准许可。"""
    conn, config = env
    out1 = calibrate(conn, config, transport=_http400_with_usage(),
                     now=NOW)
    assert out1["status"] == "gate_rejected:sample_failed:no_retry"
    assert _cal_attempts(conn) == 1

    calls = []
    counting = httpx.MockTransport(
        lambda req: (calls.append(1), httpx.Response(200, json={
            "id": "x", "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps({"attentionScore": 50})}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                      "prompt_cache_hit_tokens": 0,
                      "prompt_cache_miss_tokens": 10}}))[1])
    out2 = calibrate(conn, config, transport=counting, now=NOW)
    assert out2["passed"] is False                  # 不得 passed
    assert out2["status"].startswith("gate_rejected:resend_")  # can_retry 拒
    assert _cal_attempts(conn) == 1                 # 零新增 attempt
    assert calls == []                              # 零网络(replay 不命中)
    assert calibration_effective(conn, config) is False

    # 重放只依赖持久化记录:关闭连接重开,判定一致
    db = _db_path(conn)
    conn.close()
    conn2 = connect_db(db)
    out3 = calibrate(conn2, config, transport=counting, now=NOW)
    assert out3["passed"] is False
    assert out3["status"] == out2["status"]
    assert _cal_attempts(conn2) == 1
    assert calls == []
    conn2.close()


def test_calibration_budget_limits_approved_reservations(env):
    """复核 P1:calibration.budget_micro_cny 是"按预占值批准的调用量"
    上限(model-calls §3 规则 11),不是实付预算——每样本实付极低但
    累计预占耗尽后必须中止,已批准累计不得超上限。"""
    conn, config = env
    tiny = dataclasses.replace(
        config, budget=dataclasses.replace(
            config.budget, calibration_budget_micro_cny=6000))
    out = calibrate(conn, tiny, transport=_transport(10), now=NOW)
    assert out["status"] == "budget_exhausted"
    assert out["passed"] is False
    n, total = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(reserved_micro_cny), 0)"
        " FROM receipt_attempt a JOIN receipt r ON r.id=a.receipt_id"
        " WHERE r.purpose='calibration'").fetchone()
    assert 0 < n < 4                # 耗尽即中止,未跑完四样本
    assert total <= 6000            # 已批准预占累计不超上限
    assert calibration_effective(conn, config) is False


def test_calibration_replay_uses_latest_settled_attempt(env):
    """交界 A1:首发传输 unknown(attempt_no=1 无计量)→过窗补发结算
    (attempt_no=2)→再次重跑:replay 须命中最新已结算 attempt——只认
    attempt_no=1 会判"未复用"重复付费。"""
    from datetime import timedelta
    conn, config = env
    t0 = datetime.now(timezone.utc)
    out1 = calibrate(conn, config, transport=_net_down(), now=t0)
    assert out1["status"].startswith("gate_rejected:sample_failed")
    assert _cal_attempts(conn) == 1

    out2 = calibrate(conn, config, transport=_transport(10),
                     now=t0 + timedelta(minutes=31))
    assert out2["passed"] is True
    assert _cal_attempts(conn) == 5              # 样本0补发+样本1-3首发

    calls = []
    counting = httpx.MockTransport(
        lambda req: (calls.append(1), httpx.Response(200, json={
            "id": "x", "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps({"attentionScore": 50})}}],
            "usage": {"prompt_tokens": 999_999, "completion_tokens": 5,
                      "prompt_cache_hit_tokens": 0,
                      "prompt_cache_miss_tokens": 999_999}}))[1])
    out3 = calibrate(conn, config, transport=counting,
                     now=t0 + timedelta(minutes=32))
    assert out3["passed"] is True
    assert calls == []                           # 全样本 replay 命中零网络
    assert _cal_attempts(conn) == 5              # 零新增(含样本0 的 no=2)
    assert all(r["reused"] for r in out3["results"])


def test_calibration_resend_goes_through_can_retry(env):
    """交界 A2:校准再发送同过 can_retry 三条件(§3 规则 3,与
    score._attempt_side 同构):unknown 30min 窗内不补发(等待),过窗按
    unknown_retry 通道补发且 attempt_origin 如实记录(不再恒 initial)。"""
    from datetime import timedelta
    conn, config = env
    t0 = datetime.now(timezone.utc)
    out1 = calibrate(conn, config, transport=_net_down(), now=t0)
    assert out1["status"].startswith("gate_rejected:sample_failed")

    # 窗内(<30min)重跑:不补发、零新增、返回等待语义
    out2 = calibrate(conn, config, transport=_transport(10),
                     now=t0 + timedelta(minutes=1))
    assert out2["status"] == "unknown_wait"
    assert out2["passed"] is False
    assert _cal_attempts(conn) == 1

    out3 = calibrate(conn, config, transport=_transport(10),
                     now=t0 + timedelta(minutes=31))
    assert out3["passed"] is True
    origin = conn.execute(
        "SELECT a.attempt_origin FROM receipt_attempt a JOIN receipt r"
        " ON r.id=a.receipt_id WHERE r.purpose='calibration'"
        " AND a.attempt_no=2 ORDER BY a.id LIMIT 1").fetchone()[0]
    assert origin == "unknown_retry"            # 通道如实记录


# ---------- 审计修正③:校准 CLI 执行入口(python -m nanmu_engine.calibrate) ----------

def _hold_lock(path):
    """跨平台持有 run.lock(Windows msvcrt / POSIX fcntl)。"""
    f = open(path, "a")
    try:
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        return f, lambda: msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    except ImportError:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f, lambda: fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _engine_root_env(tmp_path):
    import shutil
    shutil.copytree(ENGINE_ROOT / "config", tmp_path / "config")
    shutil.copytree(ENGINE_ROOT / "resources", tmp_path / "resources")
    return tmp_path


def test_calibrate_cli_pass_with_stub(tmp_path):
    """CLI 全链(锁→config→engine.db→ops.calibrate)替身验证:退出 0,
    校准记录生效绑定指纹。零真实网络。"""
    import nanmu_engine.calibrate as cli
    root = _engine_root_env(tmp_path)
    rc = cli.main(["--root", str(root)], transport=_transport(10))
    assert rc == 0, "校准通过应退出 0"
    conn = connect_db(str(root / "engine.db"))
    assert calibration_effective(conn, load_config(ENGINE_ROOT)) is True
    assert _cal_attempts(conn) == 4
    conn.close()


def test_calibrate_cli_lock_busy(tmp_path):
    """与引擎共用 run.lock:另一实例持锁→退出 1,不建库不校准。"""
    import nanmu_engine.calibrate as cli
    lock, unlock = _hold_lock(tmp_path / "run.lock")
    try:
        assert cli.main(["--root", str(tmp_path)],
                        transport=_transport(10)) == 1
        assert not (tmp_path / "engine.db").exists()
    finally:
        unlock()
        lock.close()


def test_calibrate_cli_config_error(tmp_path):
    import nanmu_engine.calibrate as cli
    assert cli.main(["--root", str(tmp_path)]) == 2
