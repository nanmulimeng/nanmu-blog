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
