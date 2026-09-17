"""零依赖的编码 / 校验工具。

只用 Python 标准库实现地址校验需要的几种算法：

* Keccak-256   —— 以太坊系地址的 EIP-55 大小写校验和
* Base58Check  —— 比特币 / 波场 / 狗狗币等地址
* Bech32(m)    —— 比特币 SegWit、Cosmos 系、Cardano 等地址
* SS58         —— Polkadot / Kusama 系地址

这些校验能把"手抖打错一位的地址"和"真实地址"区分开，属于本工具
防止资产丢失的第一道关卡，因此不依赖任何第三方库。
"""

from __future__ import annotations

import hashlib

_MASK64 = 0xFFFFFFFFFFFFFFFF

# --------------------------------------------------------------------------
# Keccak-256（以太坊使用的原始 Keccak，填充字节是 0x01，不是 SHA3 的 0x06）
# --------------------------------------------------------------------------

_KECCAK_RC = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)

_KECCAK_ROT = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)


def _rol(value: int, shift: int) -> int:
    shift &= 63
    if shift == 0:
        return value & _MASK64
    return ((value << shift) | (value >> (64 - shift))) & _MASK64


def _keccak_f1600(a: list[int]) -> None:
    for rc in _KECCAK_RC:
        # θ
        c = [a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(0, 25, 5):
                a[x + y] ^= d[x]
        # ρ + π
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rol(a[x + 5 * y], _KECCAK_ROT[x][y])
        # χ
        for y in range(0, 25, 5):
            for x in range(5):
                a[x + y] = b[x + y] ^ ((b[(x + 1) % 5 + y] ^ _MASK64) & b[(x + 2) % 5 + y])
        # ι
        a[0] ^= rc


def keccak256(data: bytes) -> bytes:
    """返回 data 的 Keccak-256 摘要（32 字节）。"""
    rate = 136  # 1088 bit
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != 0:
        padded.append(0x00)
    padded[-1] |= 0x80

    state = [0] * 25
    for offset in range(0, len(padded), rate):
        block = padded[offset:offset + rate]
        for i in range(rate // 8):
            state[i] ^= int.from_bytes(block[i * 8:i * 8 + 8], "little")
        _keccak_f1600(state)
    return b"".join(lane.to_bytes(8, "little") for lane in state[:4])


def crc16_xmodem(data: bytes) -> int:
    """CRC16/XMODEM —— 恒星币和 TON 地址的校验和算法。"""
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


# --------------------------------------------------------------------------
# Base58 / Base58Check
# --------------------------------------------------------------------------

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {ch: i for i, ch in enumerate(_B58_ALPHABET)}


def b58decode(text: str) -> bytes | None:
    """Base58 解码，字符非法时返回 None。"""
    if not text:
        return None
    num = 0
    for ch in text:
        index = _B58_INDEX.get(ch)
        if index is None:
            return None
        num = num * 58 + index
    body = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    pad = len(text) - len(text.lstrip("1"))
    return b"\x00" * pad + body


def b58check_decode(text: str) -> bytes | None:
    """校验 Base58Check 并返回去掉校验和的负载（含版本前缀）。

    校验和不正确时返回 None —— 也就是地址被打错了。
    """
    raw = b58decode(text)
    if raw is None or len(raw) < 5:
        return None
    payload, checksum = raw[:-4], raw[-4:]
    digest = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return payload if digest == checksum else None


# --------------------------------------------------------------------------
# Bech32 / Bech32m（BIP-173 / BIP-350）
# --------------------------------------------------------------------------

_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32_CONST = 1
_BECH32M_CONST = 0x2BC830A3


def _bech32_polymod(values) -> int:
    generator = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    chk = 1
    for value in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ value
        for i in range(5):
            chk ^= generator[i] if ((top >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(ch) >> 5 for ch in hrp] + [0] + [ord(ch) & 31 for ch in hrp]


def bech32_decode(text: str) -> tuple[str, list[int], str] | None:
    """解码 bech32 / bech32m，返回 (hrp, 数据部分, 变体)。

    变体为 "bech32" 或 "bech32m"；格式或校验和错误时返回 None。
    """
    if any(ord(ch) < 33 or ord(ch) > 126 for ch in text):
        return None
    if text.lower() != text and text.upper() != text:
        return None  # 不允许大小写混用
    text = text.lower()
    pos = text.rfind("1")
    if pos < 1 or pos + 7 > len(text) or len(text) > 108:
        return None
    hrp, data_part = text[:pos], text[pos + 1:]
    data = []
    for ch in data_part:
        index = _BECH32_CHARSET.find(ch)
        if index == -1:
            return None
        data.append(index)
    checksum = _bech32_polymod(_bech32_hrp_expand(hrp) + data)
    if checksum == _BECH32_CONST:
        variant = "bech32"
    elif checksum == _BECH32M_CONST:
        variant = "bech32m"
    else:
        return None
    return hrp, data[:-6], variant


def _bech32_create_checksum(hrp: str, data: list[int], const: int) -> list[int]:
    values = _bech32_hrp_expand(hrp) + data
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ const
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def bech32_encode(hrp: str, data: list[int], variant: str = "bech32") -> str:
    """bech32 / bech32m 编码。"""
    const = _BECH32_CONST if variant == "bech32" else _BECH32M_CONST
    combined = data + _bech32_create_checksum(hrp, data, const)
    return hrp + "1" + "".join(_BECH32_CHARSET[d] for d in combined)


def convertbits(data, frombits: int, tobits: int, pad: bool = True) -> list[int] | None:
    """BIP-173 的位宽转换（8 位字节 <-> 5 位组）。"""
    acc = 0
    bits = 0
    out: list[int] = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            out.append((acc >> bits) & maxv)
    if pad:
        if bits:
            out.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return out


# --------------------------------------------------------------------------
# SS58（Polkadot / Kusama / Substrate 系）
# --------------------------------------------------------------------------

def ss58_decode(text: str) -> tuple[int, bytes] | None:
    """校验 SS58 地址，返回 (网络前缀, 公钥)；失败返回 None。"""
    raw = b58decode(text)
    if raw is None or len(raw) < 35:
        return None
    first = raw[0]
    if first < 64:
        prefix, prefix_len = first, 1
    elif first < 128:
        lower = ((first & 0x3F) << 2) | (raw[1] >> 6)
        upper = raw[1] & 0x3F
        prefix, prefix_len = lower | (upper << 8), 2
    else:
        return None
    body, checksum = raw[:-2], raw[-2:]
    pubkey = raw[prefix_len:-2]
    if len(pubkey) not in (32, 33):
        return None
    digest = hashlib.blake2b(b"SS58PRE" + body, digest_size=64).digest()
    if digest[:2] != checksum:
        return None
    return prefix, pubkey


# --------------------------------------------------------------------------
# EIP-55（以太坊系地址的大小写校验和）
# --------------------------------------------------------------------------

def eip55_checksum(address: str) -> str:
    """把 0x 开头的十六进制地址转成 EIP-55 大小写形式。"""
    body = address[2:].lower() if address.lower().startswith("0x") else address.lower()
    digest = keccak256(body.encode("ascii")).hex()
    out = "".join(ch.upper() if int(digest[i], 16) >= 8 else ch for i, ch in enumerate(body))
    return "0x" + out


def eip55_is_valid(address: str) -> bool | None:
    """校验 EIP-55。

    返回 True/False 表示校验通过或失败；地址是纯大写或纯小写时无法判断，
    返回 None（这类地址本身也是合法写法）。
    """
    if not address.lower().startswith("0x") or len(address) != 42:
        return None
    body = address[2:]
    if body == body.lower() or body == body.upper():
        return None
    return eip55_checksum(address) == "0x" + body
