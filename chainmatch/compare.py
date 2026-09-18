"""对比两个输入是否属于同一条链，并给出风险提示。

结论只有四种：

    same           两边确定是同一条链
    different      两边确定不是同一条链（最危险，会丢币）
    possibly_same  信息不足，候选有交集但无法确定（例如两个 0x 地址）
    unknown        至少一边没能识别出链

"不确定"必须如实说成不确定——在转账场景里，把"可能一样"说成"一样"比说不知道更危险。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import chains
from .model import Resolution

SAME = "same"
DIFFERENT = "different"
POSSIBLY_SAME = "possibly_same"
UNKNOWN = "unknown"

_VERDICT_TEXT = {
    SAME: "✅ 同一条链",
    DIFFERENT: "❌ 不是同一条链",
    POSSIBLY_SAME: "⚠️ 无法确定（候选有重叠）",
    UNKNOWN: "❓ 信息不足，无法判断",
}


@dataclass
class Comparison:
    a: Resolution
    b: Resolution
    verdict: str
    confidence: float
    headline: str
    reason: str
    shared: tuple[str, ...] = ()
    risks: list[str] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)

    @property
    def verdict_text(self) -> str:
        return _VERDICT_TEXT[self.verdict]

    @property
    def is_safe(self) -> bool:
        """只有明确同链、且没有校验和级别的告警时才算"可以转"。"""
        return self.verdict == SAME and not any("校验" in r for r in self.risks)


def compare(a: Resolution, b: Resolution) -> Comparison:
    shared = tuple(c for c in a.candidates if c in b.candidates)
    confidence = round(min(a.confidence, b.confidence), 4)

    if not a.resolved or not b.resolved:
        missing = []
        if not a.resolved:
            missing.append("A")
        if not b.resolved:
            missing.append("B")
        result = Comparison(
            a=a, b=b, verdict=UNKNOWN, confidence=0.0,
            headline="信息不足，无法判断是否同链",
            reason=f"输入 {' 和 '.join(missing)} 没有识别出链信息",
            shared=shared,
        )
    elif a.certain and b.certain:
        if a.top == b.top:
            result = Comparison(
                a=a, b=b, verdict=SAME, confidence=confidence,
                headline=f"两边都是 {chains.label(a.top)}",
                reason="两个输入都唯一指向同一条链",
                shared=shared,
            )
        else:
            result = Comparison(
                a=a, b=b, verdict=DIFFERENT, confidence=confidence,
                headline=f"A 是 {chains.label(a.top)}，B 是 {chains.label(b.top)}",
                reason="两个输入分别唯一指向了不同的链",
                shared=shared,
            )
    elif not shared:
        result = Comparison(
            a=a, b=b, verdict=DIFFERENT, confidence=round(confidence * 0.9, 4),
            headline=f"A 指向 {a.describe()}，B 指向 {b.describe()}",
            reason="两边的候选链没有任何交集",
            shared=shared,
        )
    else:
        result = Comparison(
            a=a, b=b, verdict=POSSIBLY_SAME, confidence=confidence,
            headline=_possibly_headline(a, b, shared),
            reason=_possibly_reason(a, b, shared),
            shared=shared,
        )

    result.risks = _risks(result)
    result.advice = _advice(result)
    return result


def _possibly_headline(a: Resolution, b: Resolution, shared: tuple[str, ...]) -> str:
    if len(shared) == 1:
        return f"两边都可能是 {chains.label(shared[0])}，但证据不足以确定"
    if a.family_hint and a.family_hint == b.family_hint:
        return f"两边都只能确定是同一个技术家族（{a.family_hint.upper()}），具体链未知"
    return f"两边有 {len(shared)} 条共同候选链，但都无法确定具体是哪一条"


def _possibly_reason(a: Resolution, b: Resolution, shared: tuple[str, ...]) -> str:
    if a.certain and not b.certain:
        return f"A 已确定是 {chains.label(a.top)}，但 B 的信息只够缩到 {len(b.candidates)} 条候选"
    if b.certain and not a.certain:
        return f"B 已确定是 {chains.label(b.top)}，但 A 的信息只够缩到 {len(a.candidates)} 条候选"
    return "两边给出的信息都不足以锁定唯一一条链"


# --------------------------------------------------------------------------
# 风险与建议
# --------------------------------------------------------------------------

def _same_address(a: Resolution, b: Resolution) -> bool:
    """两边是否出现了同一个地址（EVM 地址跨链通用时特别危险）。"""
    left = {addr.lower() for addr in a.addresses}
    right = {addr.lower() for addr in b.addresses}
    return bool(left & right)

def _risks(result: Comparison) -> list[str]:
    risks: list[str] = []
    a, b = result.a, result.b

    # 地址校验和之类的问题优先级最高
    for side, res in (("A", a), ("B", b)):
        for warning in res.warnings:
            if "校验" in warning or "篡改" in warning or "测试网" in warning:
                risks.append(f"输入 {side}：{warning}")

    if result.verdict == DIFFERENT:
        risks.append(_cross_chain_risk(a, b))
        if _same_address(a, b):
            risks.append(
                "两边的地址字符串完全相同，但网络不同——这正是最常见的转错链场景，"
                "地址一样绝不代表链一样"
            )
        if {a.top, b.top} == {"bsc", "bnb-beacon-chain"}:
            risks.append("BEP2（Beacon Chain，bnb1 开头）和 BEP20（BSC，0x 开头）是两条不同的链，不能互转")

    if result.verdict == POSSIBLY_SAME:
        if a.family_hint == "evm" or b.family_hint == "evm":
            risks.append(
                "0x 开头的地址在以太坊、BSC、Polygon、Arbitrum 等所有 EVM 链上都有效，"
                "只看地址永远无法判断链，必须让对方说明网络名"
            )
        risks.append("在没有确认网络之前转账，等同于赌一把")

    if result.verdict == SAME:
        chain = chains.BY_ID.get(result.a.top or "")
        if chain and chain.id in ("ripple", "stellar", "eos", "hedera", "ton"):
            risks.append(f"{chain.name_zh or chain.name_en} 转账通常还需要 Tag / Memo，漏填同样会导致资金找不回")
        if chain and chain.family == "evm":
            risks.append("同链不等于同代币：还要核对代币合约地址，谨防同名假币")

    return [r for r in risks if r]


def _cross_chain_risk(a: Resolution, b: Resolution) -> str:
    """跨链转账的后果分级——EVM 之间和跨体系的后果完全不同。"""
    if not (a.top and b.top):
        return "两边不是同一条链，直接转账极可能造成资产损失"
    chain_a, chain_b = chains.BY_ID.get(a.top), chains.BY_ID.get(b.top)
    if not (chain_a and chain_b):
        return "两边不是同一条链，直接转账极可能造成资产损失"

    if chain_a.family == "evm" and chain_b.family == "evm":
        return (
            f"{chain_a.name_zh} 与 {chain_b.name_zh} 都是 EVM 链、地址格式相同，"
            "转错后资产会停留在源链的同一个地址上：如果你掌握该地址私钥，通常还能在源链找回；"
            "但如果收款方是交易所充值地址，多半无法找回"
        )
    return (
        f"{chain_a.name_zh or chain_a.name_en} 与 {chain_b.name_zh or chain_b.name_en} "
        "属于完全不同的地址体系，跨过去的资产无法恢复，会永久丢失"
    )


def _advice(result: Comparison) -> list[str]:
    a, b = result.a, result.b
    if result.verdict == SAME:
        return [
            "网络一致，可以继续；转账前再逐字核对收款地址的前 6 位和后 6 位",
            "建议先小额试转一笔，到账后再转大额",
        ]
    if result.verdict == DIFFERENT:
        advice = ["不要直接转账"]
        if a.top and b.top:
            advice.append(
                f"要么让转出方改用 {chains.label(b.top)} 网络，"
                f"要么让收款方提供 {chains.label(a.top)} 网络的地址"
            )
        advice.append("确实要跨链，请使用官方跨链桥或经由交易所中转（先提到交易所，再按目标网络提出）")
        return advice
    if result.verdict == POSSIBLY_SAME:
        return [
            "让对方明确说出网络名称（是 TRC20 还是 ERC20，而不是 USDT 这种币种名）",
            "或者让对方从钱包里直接分享收款二维码：带 chainId 的二维码可以精确判定链",
            "交易所充值页面上的「网络 / Network」一栏，就是需要核对的那个值",
        ]
    return [
        "请补充网络名称（如 TRC20 / ERC20 / BEP20）、收款地址或钱包收款二维码",
        "只说币种名（USDT、USDC）无法判断链——同一个币在十几条链上都有",
    ]
