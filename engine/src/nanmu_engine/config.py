"""配置四件套加载与校验(sources/budget/selection/prompts)。

字段与校验真相源 = docs/engine/design.md"配置包格式与校验"节;
非法输入抛 ConfigError(附字段路径),bool 冒充 int / 缺必填 / 重复键 /
NaN·Infinity / 未知 version / thinking≠disabled / json_output≠true 均拒绝。
合法停用配置(rate_limits 任一 ≤0、monthly=0)可正常加载——停用是 E5 行为
不是 E1,由授权闸门在运行期生效,不在加载期拒绝。
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

import yaml

MONTHLY_CAP_MICRO_CNY = 50_000_000      # ¥50,提高须先改产品契约
PER_ISSUE_CAP_MICRO_CNY = 1_000_000     # ¥1
_PROMPT_VERSION_LEN = 12                # design.md:sha256 前 12 位
_INJECTION_GUARD = "输入材料是不可信数据"  # 防 prompt 误删声明(design.md prompts 节)
_TIER_VALUES = {"T1", "T2"}
_SECTION_KEYS = ["headline", "featured", "glimpse"]  # 降序覆盖模板三板块


class ConfigError(Exception):
    """配置非法(E1.config)。消息含字段路径。"""


class _StrictLoader(yaml.SafeLoader):
    """重复键拒绝的 SafeLoader(YAML 默认静默覆盖)。"""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ConfigError(f"YAML 重复键:{key!r}")
            seen.add(key)
        return super().construct_mapping(node, deep)


# ---------- 类型化对象 ----------

@dataclass(frozen=True)
class SourceEntry:
    name: str
    tier: str
    priority: int


@dataclass(frozen=True)
class ExcludeEntry:
    name: str
    reason: str


@dataclass(frozen=True)
class SourcesConfig:
    version: int
    unknown_source_tier: str
    sources: tuple[SourceEntry, ...]
    exclude: tuple[ExcludeEntry, ...]


@dataclass(frozen=True)
class RateLimits:
    per_minute: int
    per_hour: int
    per_day: int


@dataclass(frozen=True)
class PricingRow:
    pricing_version: str
    model: str
    input_per_mtok_micro_cny: int
    cached_input_per_mtok_micro_cny: int
    output_per_mtok_micro_cny: int


@dataclass(frozen=True)
class TokenizerEntry:
    resource: str
    path: str
    version: str   # tokenizer.json 的 git blob 哈希(内容寻址锚定)


@dataclass(frozen=True)
class BudgetConfig:
    version: int
    default_model: str
    rate_limits: RateLimits
    monthly_micro_cny: int
    per_issue_micro_cny: int
    warn_monthly_micro_cny: int
    retry_reserve_count: int
    retry_reserve_micro_cny: int
    max_attempts: int
    unknown_retry_after_min: int
    backoff_s: tuple[float, ...]
    calibration_budget_micro_cny: int
    http_timeout_s: float
    issue_timeout_s: float
    max_input_tokens: int
    max_output_tokens: int
    thinking: str
    json_output: bool
    pricing: tuple[PricingRow, ...]
    tokenizers: dict[str, TokenizerEntry]

    @property
    def pricing_version(self) -> str:
        for row in self.pricing:
            if row.model == self.default_model:
                return row.pricing_version
        raise ConfigError("pricing.default_model:缺默认模型价目行")


@dataclass(frozen=True)
class SelectionConfig:
    version: int
    thresholds: dict[str, int]
    max_entries: int
    sections: dict[str, int]
    title_blacklist: tuple[str, ...]


@dataclass(frozen=True)
class PromptFile:
    name: str
    text: str
    version: str          # sha256(内容) 前 12 位

    @property
    def injection_guard_present(self) -> bool:
        return _INJECTION_GUARD in self.text


@dataclass(frozen=True)
class PromptsConfig:
    score: PromptFile
    understand: PromptFile


@dataclass(frozen=True)
class Config:
    root: Path
    sources: SourcesConfig
    budget: BudgetConfig
    selection: SelectionConfig
    prompts: PromptsConfig
    content_hashes: dict[str, str]   # 相对路径 → sha256(文件内容)

    @property
    def pricing_version(self) -> str:
        return self.budget.pricing_version


# ---------- 校验辅助 ----------

def _int_field(value, where: str) -> int:
    # type(v) is int 显式排除 bool(bool 是 int 子类,以 bool 冒充 int 拒绝)
    if type(value) is not int:
        raise ConfigError(f"{where}:须为整数,得到 {type(value).__name__}")
    return value


def _pos_number(value, where: str) -> float:
    """有限正数(int/float 均可,拒绝 bool/NaN/Infinity/≤0)。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{where}:须为数值,得到 {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise ConfigError(f"{where}:须为有限数,得到 {value!r}")
    if number <= 0:
        raise ConfigError(f"{where}:须为正数,得到 {value}")
    return number


def _nonempty_str(value, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{where}:须为非空字符串")
    return value


def _require(mapping, key: str, where: str):
    if not isinstance(mapping, dict) or key not in mapping:
        raise ConfigError(f"{where}.{key}:缺必填字段")
    return mapping[key]


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        raise ConfigError(f"配置文件缺失:{path.name}")
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.load(text, Loader=_StrictLoader)
    except ConfigError:
        raise
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path.name}:YAML 解析失败({exc})") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name}:顶层必须是映射")
    return data


def _check_version(data: dict, where: str, current: int = 1) -> int:
    version = _int_field(_require(data, "version", where), f"{where}.version")
    if version != current:
        raise ConfigError(f"{where}.version:未知结构版本 {version}(当前 {current})")
    return version


# ---------- 各文件校验 ----------

def _load_sources(data: dict) -> SourcesConfig:
    where = "sources"
    _check_version(data, where)
    tier = data.get("unknown_source_tier", "T2")
    if tier not in _TIER_VALUES:
        raise ConfigError(f"{where}.unknown_source_tier:须为 T1|T2,得到 {tier!r}")
    entries: list[SourceEntry] = []
    names: set[str] = set()
    for i, item in enumerate(_require(data, "sources", where)):
        w = f"{where}.sources[{i}]"
        name = _nonempty_str(item.get("name"), f"{w}.name")
        item_tier = item.get("tier")
        if item_tier not in _TIER_VALUES:
            raise ConfigError(f"{w}.tier:须为 T1|T2,得到 {item_tier!r}")
        priority = item.get("priority", 100)
        priority = _int_field(priority, f"{w}.priority")
        if priority < 0:
            raise ConfigError(f"{w}.priority:须 ≥0,得到 {priority}")
        if name in names:
            raise ConfigError(f"{w}.name:源名称重复 {name!r}")
        names.add(name)
        entries.append(SourceEntry(name, item_tier, priority))
    excludes: list[ExcludeEntry] = []
    for i, item in enumerate(data.get("exclude", [])):
        w = f"{where}.exclude[{i}]"
        name = _nonempty_str(item.get("name"), f"{w}.name")
        if name in names:
            raise ConfigError(
                f"{w}.name:{name!r} 同时出现在 sources 与 exclude")
        excludes.append(ExcludeEntry(name, _nonempty_str(item.get("reason"), f"{w}.reason")))
    return SourcesConfig(1, tier, tuple(entries), tuple(excludes))


def _load_budget(root: Path, data: dict) -> BudgetConfig:
    where = "budget"
    _check_version(data, where)
    default_model = _nonempty_str(
        _require(data, "default_model", where), f"{where}.default_model")

    rl = _require(data, "rate_limits", where)
    rate = RateLimits(*[
        _int_field(_require(rl, k, f"{where}.rate_limits"), f"{where}.rate_limits.{k}")
        for k in ("per_minute", "per_hour", "per_day")
    ])  # 任一 ≤0 = 合法停用(E5.limit),不在此拒绝

    money = _require(data, "money_micro_cny", where)
    monthly = _int_field(
        _require(money, "monthly", f"{where}.money_micro_cny"),
        f"{where}.money_micro_cny.monthly")
    per_issue = _int_field(
        _require(money, "per_issue", f"{where}.money_micro_cny"),
        f"{where}.money_micro_cny.per_issue")
    warn_monthly = _int_field(
        _require(money, "warn_monthly", f"{where}.money_micro_cny"),
        f"{where}.money_micro_cny.warn_monthly")
    if monthly < 0 or per_issue < 0 or warn_monthly < 0:
        raise ConfigError(f"{where}.money_micro_cny:须为非负整数微元")
    if monthly > MONTHLY_CAP_MICRO_CNY:
        raise ConfigError(
            f"{where}.money_micro_cny.monthly:{monthly} 超上限 "
            f"{MONTHLY_CAP_MICRO_CNY}(¥50),提高须先改产品契约")
    if per_issue > PER_ISSUE_CAP_MICRO_CNY:
        raise ConfigError(
            f"{where}.money_micro_cny.per_issue:{per_issue} 超上限 "
            f"{PER_ISSUE_CAP_MICRO_CNY}(¥1)")
    if monthly > 0 and warn_monthly > monthly:
        raise ConfigError(
            f"{where}.money_micro_cny.warn_monthly:{warn_monthly} > monthly {monthly}"
            "(monthly=0 时可保留原预警阈值)")

    reserve = _require(data, "reserve", where)
    retry_reserve_count = _int_field(
        _require(reserve, "retry_reserve_count", f"{where}.reserve"),
        f"{where}.reserve.retry_reserve_count")
    retry_reserve_micro = _int_field(
        _require(reserve, "retry_reserve_micro_cny", f"{where}.reserve"),
        f"{where}.reserve.retry_reserve_micro_cny")
    if retry_reserve_count < 0 or retry_reserve_micro < 0:
        raise ConfigError(f"{where}.reserve:两项均须非负整数(0=不专门预留)")

    retry = _require(data, "retry", where)
    max_attempts = _int_field(
        _require(retry, "max_attempts", f"{where}.retry"), f"{where}.retry.max_attempts")
    if max_attempts < 1:
        raise ConfigError(f"{where}.retry.max_attempts:须为正整数(含首次),得到 {max_attempts}")
    unknown_after = _require(retry, "unknown_retry_after_min", f"{where}.retry")
    unknown_after = _int_field(unknown_after, f"{where}.retry.unknown_retry_after_min")
    if unknown_after < 30:
        raise ConfigError(
            f"{where}.retry.unknown_retry_after_min:须 ≥30,得到 {unknown_after}")
    backoff_raw = _require(retry, "backoff_s", f"{where}.retry")
    if not isinstance(backoff_raw, list):
        raise ConfigError(f"{where}.retry.backoff_s:须为列表")
    backoff = tuple(
        _pos_number(v, f"{where}.retry.backoff_s[{i}]") for i, v in enumerate(backoff_raw))
    if len(backoff) < max_attempts - 1:
        raise ConfigError(
            f"{where}.retry.backoff_s:长度 {len(backoff)} 须覆盖普通重试次数 "
            f"{max_attempts - 1}")

    calibration = _require(data, "calibration", where)
    calibration_budget = _int_field(
        _require(calibration, "budget_micro_cny", f"{where}.calibration"),
        f"{where}.calibration.budget_micro_cny")
    if calibration_budget < 1:
        raise ConfigError(
            f"{where}.calibration.budget_micro_cny:须为正整数微元,得到 {calibration_budget}")

    timeouts = _require(data, "timeouts", where)
    http_timeout = _pos_number(
        _require(timeouts, "http_timeout_s", f"{where}.timeouts"), f"{where}.timeouts.http_timeout_s")
    issue_timeout = _pos_number(
        _require(timeouts, "issue_timeout_s", f"{where}.timeouts"), f"{where}.timeouts.issue_timeout_s")

    limits = _require(data, "limits", where)
    max_input = _int_field(
        _require(limits, "max_input_tokens", f"{where}.limits"), f"{where}.limits.max_input_tokens")
    max_output = _int_field(
        _require(limits, "max_output_tokens", f"{where}.limits"), f"{where}.limits.max_output_tokens")
    if max_input < 1 or max_output < 1:
        raise ConfigError(f"{where}.limits:输入/输出上限均须正整数")

    llm = _require(data, "llm", where)
    thinking = _require(llm, "thinking", f"{where}.llm")
    if thinking != "disabled":
        raise ConfigError(f"{where}.llm.thinking:M1 仅接受 disabled,得到 {thinking!r}")
    json_output = _require(llm, "json_output", f"{where}.llm")
    if json_output is not True:
        raise ConfigError(f"{where}.llm.json_output:M1 仅接受 true,得到 {json_output!r}")

    pricing_raw = _require(data, "pricing", where)
    if not isinstance(pricing_raw, list) or not pricing_raw:
        raise ConfigError(f"{where}.pricing:须为非空列表")
    pricing: list[PricingRow] = []
    models: set[str] = set()
    for i, row in enumerate(pricing_raw):
        w = f"{where}.pricing[{i}]"
        entry = PricingRow(
            pricing_version=_nonempty_str(row.get("pricing_version"), f"{w}.pricing_version"),
            model=_nonempty_str(row.get("model"), f"{w}.model"),
            input_per_mtok_micro_cny=_int_field(
                row.get("input_per_mtok_micro_cny"), f"{w}.input_per_mtok_micro_cny"),
            cached_input_per_mtok_micro_cny=_int_field(
                row.get("cached_input_per_mtok_micro_cny"), f"{w}.cached_input_per_mtok_micro_cny"),
            output_per_mtok_micro_cny=_int_field(
                row.get("output_per_mtok_micro_cny"), f"{w}.output_per_mtok_micro_cny"),
        )
        for price in (entry.input_per_mtok_micro_cny,
                      entry.cached_input_per_mtok_micro_cny,
                      entry.output_per_mtok_micro_cny):
            if price < 0:
                raise ConfigError(f"{w}:单价须为非负整数微元/百万 token")
        if entry.model in models:
            raise ConfigError(f"{w}.model:重复模型价目 {entry.model!r}")
        models.add(entry.model)
        pricing.append(entry)
    if default_model not in models:
        raise ConfigError(
            f"{where}.pricing:缺 default_model {default_model!r} 的价目行")

    tokenizers_raw = _require(data, "tokenizers", where)
    if not isinstance(tokenizers_raw, dict) or not tokenizers_raw:
        raise ConfigError(f"{where}.tokenizers:须为非空映射(model → 资源)")
    tokenizers: dict[str, TokenizerEntry] = {}
    for model, entry in tokenizers_raw.items():
        w = f"{where}.tokenizers.{model}"
        tokenizers[model] = TokenizerEntry(
            resource=_nonempty_str(entry.get("resource"), f"{w}.resource"),
            path=_nonempty_str(entry.get("path"), f"{w}.path"),
            version=_nonempty_str(entry.get("version"), f"{w}.version"),
        )
        blob_path = root / tokenizers[model].path
        if not blob_path.is_file():
            raise ConfigError(f"{w}.path:tokenizer 资源缺失 {tokenizers[model].path}")
        blob = blob_path.read_bytes()
        actual = hashlib.sha1(b"blob %d\x00" % len(blob) + blob).hexdigest()
        if actual != tokenizers[model].version:
            raise ConfigError(
                f"{w}.version:与资源文件 blob 哈希不符(配置 {tokenizers[model].version[:12]}…,"
                f"实际 {actual[:12]}…)——版本漂移,拒绝加载")
    if default_model not in tokenizers:
        raise ConfigError(
            f"{where}.tokenizers:缺 default_model {default_model!r} 的映射(计数不可得=不出网)")

    return BudgetConfig(
        version=1,
        default_model=default_model,
        rate_limits=rate,
        monthly_micro_cny=monthly,
        per_issue_micro_cny=per_issue,
        warn_monthly_micro_cny=warn_monthly,
        retry_reserve_count=retry_reserve_count,
        retry_reserve_micro_cny=retry_reserve_micro,
        max_attempts=max_attempts,
        unknown_retry_after_min=unknown_after,
        backoff_s=backoff,
        calibration_budget_micro_cny=calibration_budget,
        http_timeout_s=http_timeout,
        issue_timeout_s=issue_timeout,
        max_input_tokens=max_input,
        max_output_tokens=max_output,
        thinking=thinking,
        json_output=json_output,
        pricing=tuple(pricing),
        tokenizers=tokenizers,
    )


def _load_selection(data: dict) -> SelectionConfig:
    where = "selection"
    _check_version(data, where)
    thresholds_raw = _require(data, "thresholds", where)
    thresholds = {}
    for tier in _TIER_VALUES:
        value = _int_field(
            _require(thresholds_raw, tier, f"{where}.thresholds"), f"{where}.thresholds.{tier}")
        if not 0 <= value <= 100:
            raise ConfigError(f"{where}.thresholds.{tier}:须 0-100,得到 {value}")
        thresholds[tier] = value
    max_entries = _int_field(
        _require(data, "max_entries", where), f"{where}.max_entries")
    if not 1 <= max_entries <= 15:
        raise ConfigError(f"{where}.max_entries:须 1-15,得到 {max_entries}")
    sections_raw = _require(data, "sections", where)
    sections: dict[str, int] = {}
    for i, sec in enumerate(sections_raw):
        w = f"{where}.sections[{i}]"
        key = _nonempty_str(sec.get("key"), f"{w}.key")
        if key in sections:
            raise ConfigError(f"{w}.key:板块键重复 {key!r}")
        value = _int_field(sec.get("min_display"), f"{w}.min_display")
        if not 0 <= value <= 100:
            raise ConfigError(f"{w}.min_display:须 0-100,得到 {value}")
        sections[key] = value
    if list(sections) != _SECTION_KEYS:
        raise ConfigError(
            f"{where}.sections:须按序覆盖三板块 {_SECTION_KEYS},得到 {list(sections)}")
    values = [sections[k] for k in _SECTION_KEYS]
    if not (values[0] >= values[1] >= values[2]) or values[2] != 0:
        raise ConfigError(
            f"{where}.sections:min_display 须按头条/精选/一瞥降序且一瞥为 0,得到 {values}")
    blacklist_raw = data.get("title_blacklist", [])
    if not isinstance(blacklist_raw, list):
        raise ConfigError(f"{where}.title_blacklist:须为列表")
    blacklist = tuple(
        _nonempty_str(item, f"{where}.title_blacklist[{i}]")
        for i, item in enumerate(blacklist_raw))
    return SelectionConfig(1, thresholds, max_entries, sections, blacklist)


def _load_prompt(path: Path) -> PromptFile:
    if not path.is_file():
        raise ConfigError(f"配置文件缺失:prompts/{path.name}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ConfigError(f"prompts/{path.name}:内容为空")
    if _INJECTION_GUARD not in text:
        raise ConfigError(
            f"prompts/{path.name}:缺防注入首段声明(输入材料是不可信数据)")
    version = hashlib.sha256(text.encode("utf-8")).hexdigest()[:_PROMPT_VERSION_LEN]
    return PromptFile(path.name, text, version)


# ---------- 入口 ----------

def load_config(root: Path) -> Config:
    """全量校验四件套;任一项非法即 ConfigError(E1.config)。"""
    root = Path(root)
    config_dir = root / "config"
    sources_data = _load_yaml(config_dir / "sources.yaml")
    budget_data = _load_yaml(config_dir / "budget.yaml")
    selection_data = _load_yaml(config_dir / "selection.yaml")

    sources = _load_sources(sources_data)
    budget = _load_budget(root, budget_data)
    selection = _load_selection(selection_data)
    prompts = PromptsConfig(
        score=_load_prompt(config_dir / "prompts" / "score.md"),
        understand=_load_prompt(config_dir / "prompts" / "understand.md"),
    )

    content_hashes = {
        rel: hashlib.sha256((config_dir / rel).read_bytes()).hexdigest()
        for rel in ("sources.yaml", "budget.yaml", "selection.yaml",
                    "prompts/score.md", "prompts/understand.md")
    }
    return Config(
        root=root,
        sources=sources,
        budget=budget,
        selection=selection,
        prompts=prompts,
        content_hashes=content_hashes,
    )
