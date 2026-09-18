"""地址 → 链的识别。

每条规则尽量做真实的校验和验证（Base58Check / Bech32 / EIP-55 / CRC16 / SS58），
而不只是看长度和开头字符：校验和不通过往往意味着地址被打错或被剪贴板木马替换过，
这比"链选错了"更危险，必须单独报警。
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass

from . import chains
from ._crypto import (
    _B58_ALPHABET,
    b58check_decode,
    crc16_xmodem,
    b58decode,
    bech32_decode,
    eip55_is_valid,
    ss58_decode,
)


@dataclass
class AddressHit:
    kind: str
    chains: tuple[str, ...]
    confidence: float
    detail: str
    warning: str = ""
    family: str | None = None


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------

_XRP_ALPHABET = "rpshnaf39wBUDNEGHJKLM4PQRST7VWXYZ2bcdeCg65jkm8oFqi1tuvAxyz"
_B58_BODY = r"[1-9A-HJ-NP-Za-km-z]"





# --------------------------------------------------------------------------
# 各链规则
# --------------------------------------------------------------------------

def _rule_evm(text: str) -> AddressHit | None:
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", text):
        return None
    candidates = chains.by_addr_kind("evm")
    checksum = eip55_is_valid(text)
    if checksum is False:
        return AddressHit(
            kind="evm", chains=candidates, confidence=0.4, family="evm",
            detail="0x 开头的 40 位地址（以太坊系格式）",
            warning="EIP-55 大小写校验和不通过：这个地址很可能被打错或被篡改，先别转账",
        )
    detail = "0x 开头的 40 位地址（以太坊系格式）"
    if checksum is True:
        detail += "，EIP-55 校验通过"
    return AddressHit(
        kind="evm", chains=candidates, confidence=0.9, family="evm", detail=detail,
        warning="同一个 0x 地址在所有 EVM 链上都存在，光看地址无法判断是哪条链",
    )


def _rule_tron(text: str) -> AddressHit | None:
    if not re.fullmatch(rf"T{_B58_BODY}{{33}}", text):
        return None
    payload = b58check_decode(text)
    if payload is None or payload[0] != 0x41:
        return AddressHit(
            kind="tron", chains=("tron",), confidence=0.4,
            detail="T 开头的波场地址格式",
            warning="Base58Check 校验失败：地址可能被打错，先别转账",
        )
    return AddressHit(
        kind="tron", chains=("tron",), confidence=0.97,
        detail="波场地址（Base58Check 校验通过，版本字节 0x41）",
    )


def _rule_btc_base58(text: str) -> AddressHit | None:
    if not re.fullmatch(rf"[13]{_B58_BODY}{{24,33}}", text):
        return None
    payload = b58check_decode(text)
    if payload is None:
        return AddressHit(
            kind="btc-base58", chains=("bitcoin",), confidence=0.4,
            detail="比特币 Base58 地址格式",
            warning="Base58Check 校验失败：地址可能被打错，先别转账",
        )
    version = payload[0]
    if version == 0x00:
        return AddressHit(
            kind="btc-base58", chains=("bitcoin", "bitcoin-cash"), confidence=0.85,
            detail="P2PKH 地址（Base58Check 校验通过，版本 0x00）",
            warning="比特现金的旧版地址与比特币地址格式完全相同，必须靠网络名区分",
        )
    if version == 0x05:
        return AddressHit(
            kind="btc-base58", chains=("bitcoin", "bitcoin-cash", "litecoin"), confidence=0.8,
            detail="P2SH 地址（Base58Check 校验通过，版本 0x05）",
            warning="3 开头的 P2SH 地址曾被 BTC / BCH / LTC 共用，必须靠网络名区分",
        )
    return None


def _rule_ltc_base58(text: str) -> AddressHit | None:
    if not re.fullmatch(rf"[LM]{_B58_BODY}{{25,33}}", text):
        return None
    payload = b58check_decode(text)
    if payload is None or payload[0] not in (0x30, 0x32):
        return None
    return AddressHit(
        kind="ltc-base58", chains=("litecoin",), confidence=0.95,
        detail="莱特币 Base58 地址（校验通过）",
    )


def _rule_doge(text: str) -> AddressHit | None:
    if not re.fullmatch(rf"D{_B58_BODY}{{32,33}}", text):
        return None
    payload = b58check_decode(text)
    if payload is None or payload[0] != 0x1E:
        return None
    return AddressHit(
        kind="doge", chains=("dogecoin",), confidence=0.95,
        detail="狗狗币地址（校验通过，版本 0x1E）",
    )


def _rule_dash(text: str) -> AddressHit | None:
    if not re.fullmatch(rf"X{_B58_BODY}{{32,33}}", text):
        return None
    payload = b58check_decode(text)
    if payload is None or payload[0] != 0x4C:
        return None
    return AddressHit(kind="dash", chains=("dash",), confidence=0.95,
                      detail="达世币地址（校验通过）")


def _rule_zcash_t(text: str) -> AddressHit | None:
    if not re.fullmatch(rf"t[13]{_B58_BODY}{{32,33}}", text):
        return None
    payload = b58check_decode(text)
    if payload is None or payload[:2] not in (b"\x1c\xb8", b"\x1c\xbd"):
        return None
    return AddressHit(kind="zec-transparent", chains=("zcash",), confidence=0.95,
                      detail="Zcash 透明地址（校验通过）")


def _rule_bech32(text: str) -> AddressHit | None:
    decoded = bech32_decode(text)
    if decoded is None:
        return None
    hrp, _, _ = decoded
    matched = chains.by_bech32_hrp(hrp)
    if matched:
        warning = ""
        if len(matched) > 1:
            warning = f"前缀 {hrp}1 被 {len(matched)} 条链共用，必须靠网络名区分"
        return AddressHit(
            kind=f"bech32:{hrp}", chains=matched, confidence=0.94 if len(matched) == 1 else 0.8,
            detail=f"Bech32 地址，前缀 {hrp}1（校验通过）", warning=warning,
            family="cosmos" if chains.get(matched[0]).family == "cosmos" else None,
        )
    if hrp in ("tb", "bcrt", "tltc"):
        return AddressHit(kind="bech32-testnet", chains=(), confidence=0.0,
                          detail=f"测试网地址（前缀 {hrp}1）",
                          warning="这是测试网地址，不要往里面转主网资产")
    return AddressHit(
        kind=f"bech32:{hrp}", chains=(), confidence=0.0,
        detail=f"Bech32 地址，前缀 {hrp}1（校验通过），但本工具不认识这条链",
    )


def _rule_bch_cashaddr(text: str) -> AddressHit | None:
    body = text.split(":", 1)[1] if ":" in text else text
    if not re.fullmatch(r"[qp][a-z0-9]{41}", body.lower()):
        return None
    if ":" in text and not text.lower().startswith("bitcoincash:"):
        return None
    return AddressHit(kind="bch-cashaddr", chains=("bitcoin-cash",), confidence=0.92,
                      detail="比特现金 CashAddr 地址")


def _rule_xrp(text: str) -> AddressHit | None:
    if not re.fullmatch(r"r[1-9A-HJ-NP-Za-km-z]{23,34}", text):
        return None
    translated = text.translate(str.maketrans(_XRP_ALPHABET, _B58_ALPHABET))
    payload = b58check_decode(translated)
    if payload is None or payload[0] != 0x00:
        return None
    return AddressHit(
        kind="xrp", chains=("ripple",), confidence=0.95,
        detail="瑞波账户地址（校验通过）",
        warning="转入交易所时通常必须同时填写 Tag / Memo，漏填会导致资金找不回",
    )


def _rule_stellar(text: str) -> AddressHit | None:
    if not re.fullmatch(r"G[A-Z2-7]{55}", text):
        return None
    try:
        raw = base64.b32decode(text)
    except Exception:
        return None
    if len(raw) != 35 or raw[0] != 0x30:
        return None
    if int.from_bytes(raw[33:], "little") != crc16_xmodem(raw[:33]):
        return AddressHit(kind="xlm", chains=("stellar",), confidence=0.4,
                          detail="恒星币地址格式",
                          warning="CRC 校验失败：地址可能被打错，先别转账")
    return AddressHit(
        kind="xlm", chains=("stellar",), confidence=0.96,
        detail="恒星币地址（CRC 校验通过）",
        warning="转入交易所时通常必须填写 Memo",
    )


def _rule_ton(text: str) -> AddressHit | None:
    if not re.fullmatch(r"[EU]Q[A-Za-z0-9_+/-]{46}", text):
        return None
    try:
        raw = base64.urlsafe_b64decode(text + "=")
    except Exception:
        return None
    if len(raw) != 36:
        return None
    if int.from_bytes(raw[34:], "big") != crc16_xmodem(raw[:34]):
        return AddressHit(kind="ton", chains=("ton",), confidence=0.4,
                          detail="TON 地址格式",
                          warning="CRC 校验失败：地址可能被打错，先别转账")
    return AddressHit(kind="ton", chains=("ton",), confidence=0.96,
                      detail="TON 地址（CRC 校验通过）",
                      warning="TON 转入交易所通常必须填写 Memo / Comment")


def _rule_solana(text: str) -> AddressHit | None:
    if not re.fullmatch(rf"{_B58_BODY}{{32,44}}", text):
        return None
    raw = b58decode(text)
    if raw is None or len(raw) != 32:
        return None
    confidence = 0.88 if len(text) >= 43 else 0.6
    return AddressHit(kind="solana", chains=("solana",), confidence=confidence,
                      detail="Solana 地址（Base58 解码得到 32 字节公钥）")


def _rule_ss58(text: str) -> AddressHit | None:
    if not re.fullmatch(rf"{_B58_BODY}{{46,50}}", text):
        return None
    decoded = ss58_decode(text)
    if decoded is None:
        return None
    prefix = decoded[0]
    mapping = {0: ("polkadot",), 2: ("kusama",), 5: ("astar",)}
    matched = mapping.get(prefix)
    if matched:
        return AddressHit(kind="ss58", chains=matched, confidence=0.95,
                          detail=f"SS58 地址（网络前缀 {prefix}，校验通过）")
    return AddressHit(
        kind="ss58", chains=("polkadot", "kusama", "astar"), confidence=0.5,
        detail=f"SS58 通用地址（网络前缀 {prefix}，校验通过）",
        warning="通用格式的 Substrate 地址可在多条平行链上使用，必须靠网络名区分",
    )


def _rule_hex64(text: str) -> AddressHit | None:
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", text):
        return None
    return AddressHit(
        kind="hex64", chains=("aptos", "sui", "starknet"), confidence=0.55, family="move",
        detail="0x 开头的 64 位地址",
        warning="Aptos / Sui / Starknet 的地址格式相同，光看地址无法区分，必须靠网络名",
    )


def _rule_bare_hex64(text: str) -> AddressHit | None:
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        return None
    return AddressHit(
        kind="bare-hex64", chains=("near", "icp"), confidence=0.4,
        detail="64 位十六进制字符串",
        warning="可能是 NEAR 隐式账户或 ICP 账户 ID，必须靠网络名确认",
    )


def _rule_near_named(text: str) -> AddressHit | None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,62}\.(near|tg)", text):
        return None
    return AddressHit(kind="near", chains=("near",), confidence=0.93,
                      detail="NEAR 命名账户")


def _rule_algorand(text: str) -> AddressHit | None:
    if not re.fullmatch(r"[A-Z2-7]{58}", text):
        return None
    return AddressHit(kind="algo", chains=("algorand",), confidence=0.9,
                      detail="Algorand 地址")


def _rule_hedera(text: str) -> AddressHit | None:
    if not re.fullmatch(r"\d{1,10}\.\d{1,10}\.\d{1,12}", text):
        return None
    return AddressHit(kind="hedera", chains=("hedera",), confidence=0.85,
                      detail="Hedera 账户 ID",
                      warning="转入交易所时通常必须填写 Memo")


def _rule_filecoin(text: str) -> AddressHit | None:
    if not re.fullmatch(r"f[0134][a-z2-7]{8,86}", text):
        return None
    return AddressHit(kind="filecoin", chains=("filecoin",), confidence=0.9,
                      detail="Filecoin 地址")


def _rule_tezos(text: str) -> AddressHit | None:
    if not re.fullmatch(rf"(tz[123]|KT1){_B58_BODY}{{33}}", text):
        return None
    payload = b58check_decode(text)
    confidence = 0.95 if payload is not None else 0.4
    return AddressHit(kind="tezos", chains=("tezos",), confidence=confidence,
                      detail="Tezos 地址" + ("（校验通过）" if payload else "格式"),
                      warning="" if payload else "Base58Check 校验失败，地址可能被打错")


def _rule_monero(text: str) -> AddressHit | None:
    if not re.fullmatch(rf"[48][0-9AB]{_B58_BODY}{{93}}", text):
        return None
    return AddressHit(kind="xmr", chains=("monero",), confidence=0.93,
                      detail="门罗币地址")


def _rule_kaspa(text: str) -> AddressHit | None:
    if not re.fullmatch(r"kaspa:[a-z0-9]{59,70}", text.lower()):
        return None
    return AddressHit(kind="kaspa", chains=("kaspa",), confidence=0.93,
                      detail="Kaspa 地址")


def _rule_neo(text: str) -> AddressHit | None:
    if not re.fullmatch(rf"[AN]{_B58_BODY}{{33}}", text):
        return None
    payload = b58check_decode(text)
    if payload is None or payload[0] not in (0x17, 0x35):
        return None
    return AddressHit(kind="neo", chains=("neo",), confidence=0.9,
                      detail="Neo 地址（校验通过）")


def _rule_stacks(text: str) -> AddressHit | None:
    if not re.fullmatch(r"S[PM][0-9A-HJKMNP-TV-Z]{37,39}", text):
        return None
    return AddressHit(kind="stacks", chains=("stacks",), confidence=0.9,
                      detail="Stacks 地址")


def _rule_waves(text: str) -> AddressHit | None:
    if not re.fullmatch(rf"3P{_B58_BODY}{{33}}", text):
        return None
    return AddressHit(kind="waves", chains=("waves",), confidence=0.9,
                      detail="Waves 地址")


def _rule_flow(text: str) -> AddressHit | None:
    if not re.fullmatch(r"0x[0-9a-fA-F]{16}", text):
        return None
    return AddressHit(kind="flow", chains=("flow",), confidence=0.85,
                      detail="Flow 地址")


def _rule_cardano_byron(text: str) -> AddressHit | None:
    if not re.fullmatch(r"(Ae2|DdzFF)[1-9A-Za-z]{30,110}", text):
        return None
    return AddressHit(kind="ada-byron", chains=("cardano",), confidence=0.9,
                      detail="Cardano Byron 时代地址")


_RULES = (
    _rule_evm,
    _rule_hex64,
    _rule_flow,
    _rule_tron,
    _rule_bech32,
    _rule_bch_cashaddr,
    _rule_btc_base58,
    _rule_ltc_base58,
    _rule_doge,
    _rule_dash,
    _rule_zcash_t,
    _rule_xrp,
    _rule_stellar,
    _rule_ton,
    _rule_ss58,
    _rule_solana,
    _rule_near_named,
    _rule_cardano_byron,
    _rule_algorand,
    _rule_hedera,
    _rule_filecoin,
    _rule_tezos,
    _rule_monero,
    _rule_kaspa,
    _rule_neo,
    _rule_stacks,
    _rule_waves,
    _rule_bare_hex64,
)

# 刻意没有实现的规则：
# EOS 账户名（eos-name）是 1~12 位的 [a-z1-5.] 字符串，和普通英文单词无法区分，
# 单独识别只会带来误报。EOS 走 URI（eos:）和名称匹配这两条路。


def identify(text: str) -> list[AddressHit]:
    """识别一个地址可能属于哪些链，按可信度从高到低返回。"""
    text = text.strip()
    if not text:
        return []
    hits = [hit for rule in _RULES if (hit := rule(text)) is not None]
    hits.sort(key=lambda h: h.confidence, reverse=True)
    return hits


_ADDR_SCAN = re.compile(
    r"(?<![0-9A-Za-z])("
    r"0x[0-9a-fA-F]{40,64}"
    r"|bitcoincash:[qp][a-z0-9]{41}"
    r"|kaspa:[a-z0-9]{59,70}"
    r"|[a-z]{2,12}1[02-9ac-hj-np-z]{10,100}"
    r"|[1-9A-HJ-NP-Za-km-z]{25,100}"
    r"|[A-Z2-7]{55,58}"
    r"|[a-z0-9][a-z0-9._-]{1,62}\.(?:near|tg)"
    r")(?![0-9A-Za-z])"
)


def scan(text: str) -> list[tuple[str, list[AddressHit]]]:
    """从一段文本（例如 OCR 结果）里找出所有地址。"""
    found: list[tuple[str, list[AddressHit]]] = []
    seen: set[str] = set()
    for match in _ADDR_SCAN.finditer(text):
        candidate = match.group(1)
        if candidate in seen:
            continue
        seen.add(candidate)
        hits = [h for h in identify(candidate) if h.chains or h.warning]
        if hits:
            found.append((candidate, hits))
    return found
