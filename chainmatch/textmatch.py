"""文本 → 链的识别：别名、代币标准、模糊匹配。

注意：这里只处理"名称类"文本。地址必须保持原始大小写，由 address.py 处理。
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from functools import lru_cache

from . import chains
from .model import Signal

# 代币标准里常见的"前缀 + 数字"写法，统一成不带连字符的形式
_STANDARD_PREFIXES = "erc|bep|trc|nep|krc|hrc|sip|tep|kip|fa|asa|brc"


def normalize(text: str) -> str:
    """规范化名称文本：全角转半角、转小写、统一分隔符。"""
    out = unicodedata.normalize("NFKC", text).lower()
    # ERC-20 / ERC 20 / ERC_20 一律并成 erc20
    out = re.sub(rf"\b({_STANDARD_PREFIXES})[\s\-–—_]{{1,3}}(\d+)", r"\1\2", out)
    out = re.sub(r"[-–—_/\\,;:()\[\]{}|·、，。！？]+", " ", out)
    out = re.sub(r"\s+", " ", out)
    return out.strip()


@lru_cache(maxsize=1)
def _index() -> dict[str, tuple[str, ...]]:
    """规范化后的别名 -> 链 id 列表。"""
    merged: dict[str, list[str]] = {}
    for alias, ids in chains.alias_index().items():
        key = normalize(alias)
        if not key:
            continue
        bucket = merged.setdefault(key, [])
        for chain_id in ids:
            if chain_id not in bucket:
                bucket.append(chain_id)
    return {k: tuple(v) for k, v in merged.items()}


@lru_cache(maxsize=1)
def _ambiguous() -> frozenset[str]:
    return frozenset(normalize(term) for term in chains.AMBIGUOUS_TERMS)


@lru_cache(maxsize=1)
def _token_only() -> frozenset[str]:
    return frozenset(normalize(term) for term in chains.TOKEN_ONLY_TERMS)


@lru_cache(maxsize=1)
def _pattern() -> re.Pattern[str]:
    """把所有别名编译成一个正则，长别名排在前面以保证"最长优先"。

    这样 "bitcoin cash" 不会被拆成 "bitcoin"，"polygon zkevm" 也不会退化成
    "polygon"，因为 re 的分支是最左最先匹配、且 finditer 不回头重叠。
    """
    parts = []
    for alias in sorted(_index(), key=len, reverse=True):
        escaped = re.escape(alias)
        if alias.isascii():
            # ASCII 别名要求词边界，避免 "one" 命中 "money"
            parts.append(rf"(?<![0-9a-z]){escaped}(?![0-9a-z])")
        else:
            parts.append(escaped)
    return re.compile("|".join(parts))


def _score_for(alias: str, whole_input: bool, ids: tuple[str, ...]) -> float:
    if alias in _ambiguous():
        return 0.5
    if whole_input:
        return 0.97
    if len(alias) <= 3:
        return 0.6          # eth / btc / op 这类短词，单独出现时降权
    if len(alias) <= 5:
        return 0.85
    return 0.9


def match_text(text: str) -> list[Signal]:
    """从一段文本里找出所有指向链的证据。"""
    normalized = normalize(text)
    if not normalized:
        return []

    signals: list[Signal] = []
    index = _index()
    hits: list[tuple[str, tuple[str, ...]]] = []
    for match in _pattern().finditer(normalized):
        alias = match.group(0)
        ids = index.get(alias)
        if ids:
            hits.append((alias, ids))

    seen: set[str] = set()
    for alias, ids in hits:
        if alias in seen:
            continue
        seen.add(alias)
        whole = normalized == alias
        confidence = _score_for(alias, whole, ids)
        if len(ids) > 1:
            warning = f"“{alias}”可能指 {len(ids)} 条不同的链，必须人工确认"
            detail = f"名称“{alias}”含义不唯一"
            confidence = min(confidence, 0.5)
        else:
            warning = ""
            detail = f"名称/标准“{alias}” → {chains.label(ids[0])}"
        signals.append(Signal(
            kind="standard" if re.search(r"\d", alias) else "alias",
            detail=detail,
            chains=ids,
            confidence=confidence,
            warning=warning,
        ))

    if not signals:
        signals.extend(_fuzzy(normalized))

    # 只写了代币名（USDT 之类），提醒这不是链
    tokens = set(normalized.split())
    token_only = tokens & _token_only()
    if token_only and not any(s.chains for s in signals):
        signals.append(Signal(
            kind="token-only",
            detail=f"“{'、'.join(sorted(token_only))}”只是币种，不代表任何一条链",
            chains=(),
            confidence=0.0,
            warning="同一个币在多条链上都有，必须另外说明网络（如 USDT-TRC20 / USDT-ERC20）",
        ))
    return signals


def _fuzzy(normalized: str) -> list[Signal]:
    """没有精确命中时的兜底：容忍 OCR 错字和拼写错误。"""
    index = _index()
    candidates = [a for a in index if len(a) >= 4]
    out: list[Signal] = []
    seen: set[str] = set()
    for token in [normalized] + normalized.split():
        if len(token) < 4:
            continue
        cutoff = 0.8 if len(token) >= 5 else 0.86
        for alias in difflib.get_close_matches(token, candidates, n=2, cutoff=cutoff):
            if alias in seen:
                continue
            seen.add(alias)
            ids = index[alias]
            out.append(Signal(
                kind="fuzzy",
                detail=f"“{token}”疑似写错，最接近“{alias}” → {chains.label(ids[0])}",
                chains=ids,
                confidence=0.45,
                warning="这是模糊猜测的结果，务必人工核对网络名",
            ))
        if out:
            break
    return out
