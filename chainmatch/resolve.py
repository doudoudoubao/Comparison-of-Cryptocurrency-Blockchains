"""把任意输入（链名 / 代币标准 / 地址 / 二维码 / 图片）解析成一个链的判断。

证据用"概率合成"的方式累加：多条独立证据指向同一条链时置信度上升，
p = 1 - Π(1 - pᵢ)。只指向一个家族的证据（比如 0x 地址指向所有 EVM 链）
会让候选保持为多条，从而如实反映"这个信息不足以确定链"。
"""

from __future__ import annotations

import os

from . import address, chains, image, textmatch, uri
from .model import Resolution, Signal

# 候选保留阈值：分数达到最高分的这个比例才算并列候选
_RELATIVE_KEEP = 0.93
_ABSOLUTE_FLOOR = 0.35

# 展示顺序：知识库里声明得越早越主流
_CHAIN_ORDER = {chain.id: i for i, chain in enumerate(chains.CHAINS)}


def resolve(value: str, label: str | None = None) -> Resolution:
    """解析一个输入。自动判断它是图片还是文本。"""
    raw = value.strip()
    forced_image = False
    forced_text = False
    for prefix in ("img:", "image:", "图片:"):
        if raw.lower().startswith(prefix):
            raw, forced_image = raw[len(prefix):].strip(), True
            break
    for prefix in ("text:", "文本:"):
        if raw.lower().startswith(prefix):
            raw, forced_text = raw[len(prefix):].strip(), True
            break

    if not forced_text and (forced_image or image.is_image_path(raw) or _names_an_image(raw)):
        return _resolve_image(raw, label or raw)
    return _resolve_text(raw, label or raw)


def _names_an_image(value: str) -> bool:
    """看起来是图片文件名但文件不存在。

    这种情况要明确报"找不到图片"，而不是把路径当成链名去匹配——
    "./qr-eth.png" 里的 "eth" 会让人以为工具真的读懂了那张图。
    """
    return os.path.splitext(value)[1].lower() in image.IMAGE_EXTS


# --------------------------------------------------------------------------
# 文本
# --------------------------------------------------------------------------

def _resolve_text(raw: str, label: str) -> Resolution:
    result = Resolution(raw=raw, source="text", label=label)
    result.signals.extend(_signals_from_text(raw))
    result.addresses = collect_addresses(raw)
    _finalize(result)
    return result


def collect_addresses(text: str) -> list[str]:
    """列出文本里出现过的、能被识别的地址。"""
    found: list[str] = []
    target = uri.extract_target(text.strip()) if ":" in text else None
    if target and address.identify(target):
        found.append(target)
    if _is_single_token(text.strip()) and address.identify(text.strip()):
        found.append(text.strip())
    for candidate, hits in address.scan(text):
        if any(hit.chains for hit in hits) and candidate not in found:
            found.append(candidate)
    return found


def _signals_from_text(raw: str, weight: float = 1.0, origin: str = "") -> list[Signal]:
    """从一段文本里提取所有链证据。weight 用于给弱来源（如文件名）降权。"""
    signals: list[Signal] = []
    text = raw.strip()
    if not text:
        return signals

    handled: set[str] = set()      # 同一个地址只作为一条证据，避免重复计分

    # 1) 整串是不是支付 URI / CAIP 标识
    uri_signals = uri.parse(text)
    signals.extend(uri_signals)
    target = uri.extract_target(text) if uri_signals else None
    if target:
        handled.add(target)
        signals.extend(_signals_from_address(target, note="URI 中的地址"))

    # 2) 整串是不是地址
    whole_address = not uri_signals and _is_single_token(text)
    if whole_address:
        handled.add(text)
        signals.extend(_signals_from_address(text))

    # 3) 文本里嵌着的地址（OCR 结果、聊天记录粘贴）
    if not whole_address:
        for found, hits in address.scan(text):
            if found in handled:
                continue
            handled.add(found)
            signals.extend(_hits_to_signals(hits, note=f"文本中的地址 {_short(found)}"))

    # 4) 名称 / 代币标准；整串已确认是地址时跳过，避免地址字符误命中
    if not (whole_address and any(s.confidence >= 0.8 for s in signals)):
        # URI 的 scheme 不算链名："ethereum:0x…@56" 是 BSC，chainId 才作数
        naming_text = text.split(":", 1)[1] if uri_signals else text
        signals.extend(textmatch.match_text(naming_text))

    if weight != 1.0 or origin:
        signals = [
            Signal(
                kind=s.kind,
                detail=f"{origin}{s.detail}" if origin else s.detail,
                chains=s.chains,
                confidence=min(s.confidence * weight, s.confidence),
                warning=s.warning,
                family=s.family,
            )
            for s in signals
        ]
    return signals


def _signals_from_address(text: str, note: str = "") -> list[Signal]:
    return _hits_to_signals(address.identify(text), note)


def _hits_to_signals(hits: list[address.AddressHit], note: str = "") -> list[Signal]:
    signals: list[Signal] = []
    for hit in hits:
        detail = f"{note}：{hit.detail}" if note else hit.detail
        signals.append(Signal(
            kind="address",
            detail=detail,
            chains=hit.chains,
            confidence=hit.confidence,
            warning=hit.warning,
            family=hit.family,
        ))
    return signals


def _is_single_token(text: str) -> bool:
    return bool(text) and not any(ch.isspace() for ch in text) and len(text) >= 12


def _short(text: str, keep: int = 10) -> str:
    return text if len(text) <= keep * 2 + 3 else f"{text[:keep]}…{text[-keep:]}"


# --------------------------------------------------------------------------
# 图片
# --------------------------------------------------------------------------

def _resolve_image(path: str, label: str) -> Resolution:
    result = Resolution(raw=path, source="image", label=label)
    read = image.read(path)

    if read.backends:
        result.notes.append("图片识别后端：" + "、".join(read.backends))

    for payload in read.qr_payloads:
        result.extracted_text += payload + "\n"
        result.notes.append(f"二维码内容：{_short(payload, 24)}")
        for signal in _signals_from_text(payload):
            signal.detail = f"二维码 → {signal.detail}"
            result.signals.append(signal)

    if read.text.strip():
        result.extracted_text += read.text
        result.signals.extend(_signals_from_text(read.text, origin="图中文字 → "))

    # 文件名只作为弱线索，且不足以单独定链
    stem = os.path.splitext(os.path.basename(path))[0]
    filename_signals = [
        Signal(kind="filename", detail=f"文件名线索 → {s.detail}", chains=s.chains,
               confidence=min(s.confidence, 0.45),
               warning="这条线索来自文件名，不能作为判断依据")
        for s in textmatch.match_text(stem) if s.chains
    ]
    if filename_signals and not result.signals:
        result.signals.extend(filename_signals)
    elif filename_signals:
        result.notes.append(f"文件名里也出现了链名：{stem}")

    result.addresses = collect_addresses(result.extracted_text)

    if read.error:
        result.warnings.append(read.error)
    if read.missing:
        result.warnings.append("缺少图片识别能力，请运行 chaincmp.py --check 查看安装方法")

    _finalize(result)
    return result


# --------------------------------------------------------------------------
# 汇总
# --------------------------------------------------------------------------

def _finalize(result: Resolution) -> None:
    scores: dict[str, float] = {}
    for signal in result.signals:
        for chain_id in signal.chains:
            previous = scores.get(chain_id, 0.0)
            scores[chain_id] = 1.0 - (1.0 - previous) * (1.0 - signal.confidence)
    # 保留完整精度：封顶会让"chainId=56"和"任意 EVM 地址"挤在同一个分数上，
    # 从而丢掉两者的差别。封顶只在展示层做。
    result.scores = {k: round(v, 6) for k, v in scores.items()}

    if result.scores:
        best = max(result.scores.values())
        keep = [
            chain_id for chain_id, score in result.scores.items()
            if score >= max(best * _RELATIVE_KEEP, _ABSOLUTE_FLOOR)
        ]
        # 同分时按知识库里的顺序排（主流链在前），而不是字母序
        keep.sort(key=lambda c: (-result.scores[c], _CHAIN_ORDER.get(c, 9999)))
        result.candidates = tuple(keep)

    if len(result.candidates) > 1:
        result.family_hint = _family_hint(result)

    for signal in result.signals:
        if signal.warning and signal.warning not in result.warnings:
            result.warnings.append(signal.warning)

    for chain_id in result.candidates[:3]:
        chain = chains.BY_ID.get(chain_id)
        if chain and chain.note and chain.note not in result.notes:
            result.notes.append(f"{chain.name_zh or chain.name_en}：{chain.note}")

    if not result.candidates and not result.warnings:
        result.warnings.append("没有识别到任何链信息：请提供网络名（如 TRC20）、收款地址或钱包二维码")


def _family_hint(result: Resolution) -> str | None:
    """候选是多条时，判断它们是不是同属一个技术家族。

    优先相信证据自带的家族标记：0x 地址这类证据本来就只能确定到"EVM 系"，
    哪怕候选里混进了 Injective 这种同时属于 Cosmos 生态的链。
    """
    candidate_set = set(result.candidates)
    for signal in sorted(result.signals, key=lambda s: -s.confidence):
        if signal.family and candidate_set <= set(signal.chains):
            return signal.family
    families = {chains.get(c).family for c in result.candidates if c in chains.BY_ID}
    return families.pop() if len(families) == 1 else None
