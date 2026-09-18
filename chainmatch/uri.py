"""支付 URI / CAIP 标识符解析。

钱包二维码里装的通常不是裸地址，而是带网络信息的 URI：

    ethereum:0xabc…@56/transfer?address=…   （EIP-681，@56 就是 BSC）
    eip155:137:0xabc…                        （CAIP-10）
    tron:TR7NH…
    bitcoin:bc1q…?amount=0.01

带 chainId 的 URI 是最可靠的信号——它直接写明了是哪条链。
"""

from __future__ import annotations

import re

from . import chains
from .model import Signal

# scheme -> 链 id
_SCHEME_MAP: dict[str, str] = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "litecoin": "litecoin", "dogecoin": "dogecoin",
    "bitcoincash": "bitcoin-cash", "bchtest": "bitcoin-cash",
    "dash": "dash", "zcash": "zcash", "monero": "monero",
    "tron": "tron", "tronlink": "tron",
    "solana": "solana",
    "ton": "ton", "tonkeeper": "ton",
    "ripple": "ripple", "xrpl": "ripple", "xrp": "ripple",
    "stellar": "stellar", "web+stellar": "stellar",
    "cosmos": "cosmos", "near": "near", "algorand": "algorand",
    "polkadot": "polkadot", "kusama": "kusama",
    "aptos": "aptos", "sui": "sui", "cardano": "cardano",
    "filecoin": "filecoin", "tezos": "tezos", "kaspa": "kaspa",
    "hedera": "hedera", "multiversx": "multiversx", "elrond": "multiversx",
    "binance": "bnb-beacon-chain",
}

_URI_RE = re.compile(
    r"^(?P<scheme>[a-z0-9+.\-]{2,20}):(?://)?(?:pay-|transfer/)?"
    r"(?P<target>[^@/?#]*)"
    r"(?:@(?P<chainid>0x[0-9a-fA-F]+|[0-9]+))?",
    re.IGNORECASE,
)

# CAIP-2 命名空间 -> 解析方式
_CAIP_RE = re.compile(
    r"^(?P<ns>eip155|solana|cosmos|tron|bip122|polkadot|aptos|sui|near|stellar|algorand)"
    r":(?P<ref>[0-9a-zA-Z\-]{1,64})(?::(?P<addr>[0-9a-zA-Z]+))?$",
    re.IGNORECASE,
)

# 少量常见的 CAIP-2 链引用（创世块哈希前缀 / chain-id 字符串）
_CAIP_REF_MAP: dict[str, str] = {
    "000000000019d6689c085ae165831e93": "bitcoin",
    "12a765e31ffd4059bada1e25190f6e98": "litecoin",
    "1a91e3dace36e2be3bf030a65679fe82": "bitcoin-cash",
    "cosmoshub-4": "cosmos",
    "osmosis-1": "osmosis",
    "celestia": "celestia",
    "injective-1": "injective",
    "phoenix-1": "terra",
    "columbus-5": "terra-classic",
    "5j7s6nienebd3grbfh": "solana",       # Solana mainnet-beta 的 CAIP 引用
    "0x2b6653dc": "tron",
    "91b171bb158e2d3848fa23a9f1c25182": "polkadot",
}


def parse(text: str) -> list[Signal]:
    """解析一条 URI，返回它给出的链证据；不是 URI 时返回空列表。"""
    text = text.strip()
    if ":" not in text:
        return []

    caip = _CAIP_RE.match(text)
    if caip:
        signal = _from_caip(caip)
        if signal:
            return [signal]

    match = _URI_RE.match(text)
    if not match:
        return []
    scheme = match.group("scheme").lower()
    raw_chain_id = match.group("chainid")

    if scheme in ("ethereum", "eth", "eip155"):
        if raw_chain_id:
            numeric = int(raw_chain_id, 16) if raw_chain_id.lower().startswith("0x") else int(raw_chain_id)
            chain_id = chains.by_evm_chain_id(numeric)
            if chain_id:
                return [Signal(
                    kind="uri", chains=(chain_id,), confidence=0.99,
                    detail=f"支付 URI 写明 chainId={numeric} → {chains.label(chain_id)}",
                )]
            return [Signal(
                kind="uri", chains=(), confidence=0.0,
                detail=f"支付 URI 写明 chainId={numeric}，但本工具不认识这条链",
                warning="请自行核对该 chainId 对应的网络",
            )]
        return [Signal(
            kind="uri", chains=("ethereum",), confidence=0.75,
            detail="ethereum: 支付 URI，未写 chainId，按以太坊主网理解",
            warning="URI 没带 chainId，部分钱包会用同样的格式表示其它 EVM 链",
        )]

    chain_id = _SCHEME_MAP.get(scheme)
    if chain_id:
        return [Signal(
            kind="uri", chains=(chain_id,), confidence=0.96,
            detail=f"支付 URI 的 {scheme}: 前缀 → {chains.label(chain_id)}",
        )]
    return []


def _from_caip(match: re.Match[str]) -> Signal | None:
    namespace = match.group("ns").lower()
    reference = match.group("ref").lower()
    if namespace == "eip155":
        try:
            numeric = int(reference)
        except ValueError:
            return None
        chain_id = chains.by_evm_chain_id(numeric)
        if chain_id:
            return Signal(kind="uri", chains=(chain_id,), confidence=0.99,
                          detail=f"CAIP-10 标识 eip155:{numeric} → {chains.label(chain_id)}")
        return Signal(kind="uri", chains=(), confidence=0.0,
                      detail=f"CAIP-10 标识 eip155:{numeric}，本工具不认识这条链",
                      warning="请自行核对该 chainId 对应的网络")
    mapped = _CAIP_REF_MAP.get(reference)
    if mapped is None:
        mapped = _SCHEME_MAP.get(namespace)
    if mapped is None:
        return None
    return Signal(kind="uri", chains=(mapped,), confidence=0.95,
                  detail=f"CAIP-2 标识 {namespace}:{reference} → {chains.label(mapped)}")


def extract_target(text: str) -> str | None:
    """从 URI 里取出地址部分，便于再走一遍地址校验。"""
    caip = _CAIP_RE.match(text.strip())
    if caip and caip.group("addr"):
        return caip.group("addr")
    match = _URI_RE.match(text.strip())
    if not match:
        return None
    target = match.group("target")
    return target or None
