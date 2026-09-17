"""把识别和对比结果渲染成终端文本或 JSON。"""

from __future__ import annotations

import os
import sys
import unicodedata

from . import chains, compare
from .compare import Comparison
from .model import Resolution

_COLORS = {
    "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
    "blue": "\033[34m", "cyan": "\033[36m", "grey": "\033[90m",
    "bold": "\033[1m", "reset": "\033[0m",
}

_VERDICT_COLOR = {
    compare.SAME: "green",
    compare.DIFFERENT: "red",
    compare.POSSIBLY_SAME: "yellow",
    compare.UNKNOWN: "blue",
}

EXIT_CODES = {
    compare.SAME: 0,
    compare.DIFFERENT: 1,
    compare.POSSIBLY_SAME: 2,
    compare.UNKNOWN: 3,
}

WIDTH = 68


def use_color(flag: bool | None = None) -> bool:
    if flag is False:
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if flag is True:
        return True
    return sys.stdout.isatty()


class Painter:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, text: str, *styles: str) -> str:
        if not self.enabled or not styles:
            return text
        prefix = "".join(_COLORS.get(s, "") for s in styles)
        return f"{prefix}{text}{_COLORS['reset']}"


def _display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _display_width(text))


def _ellipsis(text: str, limit: int) -> str:
    text = text.replace("\n", " ").strip()
    if _display_width(text) <= limit:
        return text
    out = ""
    for ch in text:
        if _display_width(out + ch) > limit - 1:
            break
        out += ch
    return out + "…"


# --------------------------------------------------------------------------
# 终端渲染
# --------------------------------------------------------------------------

def render(result: Comparison, color: bool = True, verbose: bool = False) -> str:
    paint = Painter(color)
    lines = [
        paint("━" * WIDTH, "cyan"),
        paint(" 虚拟币链对比 · chaincmp", "bold", "cyan"),
        paint("━" * WIDTH, "cyan"),
        "",
    ]
    lines.extend(_render_input("A", result.a, paint, verbose))
    lines.append("")
    lines.extend(_render_input("B", result.b, paint, verbose))
    lines.append("")
    lines.append(paint("─" * WIDTH, "grey"))

    style = _VERDICT_COLOR[result.verdict]
    lines.append(f" {paint('结论', 'bold')}   {paint(result.verdict_text, style, 'bold')}")
    lines.append(f"        {result.headline}")
    lines.append(f"        {paint(result.reason, 'grey')}")
    if result.verdict != compare.UNKNOWN:
        bar = _confidence_bar(result.confidence)
        lines.append(f" {paint('置信度', 'bold')} {bar} {result.confidence:.0%}")

    if result.risks:
        lines.append("")
        lines.append(f" {paint('⚠ 风险', 'yellow', 'bold')}")
        for risk in result.risks:
            lines.extend(_bullet(risk, paint, "yellow"))

    if result.advice:
        lines.append("")
        lines.append(f" {paint('→ 建议', 'cyan', 'bold')}")
        for item in result.advice:
            lines.extend(_bullet(item, paint, None))

    lines.append(paint("─" * WIDTH, "grey"))
    lines.append(paint(" 本工具只做格式与名称层面的核对，不联网查询，最终请以钱包/交易所显示为准", "grey"))
    return "\n".join(lines)


def _render_input(tag: str, res: Resolution, paint: Painter, verbose: bool,
                  show_notes: bool = True) -> list[str]:
    source = "图片" if res.source == "image" else "文本"
    head = f" {paint(tag, 'bold')}  {pad(_ellipsis(res.label, 44), 46)}{paint('[' + source + ']', 'grey')}"
    lines = [head]

    if res.resolved:
        conf = f"{res.confidence:.0%}"
        color = "green" if res.certain else "yellow"
        lines.append(f"    → {paint(res.describe(), color)}   {paint('置信度 ' + conf, 'grey')}")
    else:
        lines.append(f"    → {paint('未能识别出链', 'red')}")

    shown = 0
    for signal in res.signals:
        if not signal.detail or (not verbose and shown >= 3):
            continue
        lines.append(paint(f"      · {_ellipsis(signal.detail, WIDTH - 10)}", "grey"))
        shown += 1

    if verbose:
        if show_notes:
            for note in res.notes:
                lines.append(paint(f"      ℹ {_ellipsis(note, WIDTH - 10)}", "grey"))
        if len(res.candidates) > 1:
            listed = "、".join(chains.label(c) for c in res.candidates[:8])
            more = f" …共 {len(res.candidates)} 条" if len(res.candidates) > 8 else ""
            lines.append(paint(f"      候选：{_ellipsis(listed + more, WIDTH - 12)}", "grey"))
    return lines


def _bullet(text: str, paint: Painter, color: str | None) -> list[str]:
    limit = WIDTH - 6
    words = text
    chunks: list[str] = []
    current = ""
    for ch in words:
        if _display_width(current + ch) > limit:
            chunks.append(current)
            current = ch
        else:
            current += ch
    if current:
        chunks.append(current)
    out = []
    for i, chunk in enumerate(chunks):
        marker = "   · " if i == 0 else "     "
        out.append(paint(marker + chunk, color) if color else marker + chunk)
    return out


def _confidence_bar(value: float, width: int = 20) -> str:
    filled = int(round(value * width))
    return "█" * filled + "░" * (width - filled)


def render_resolution(res: Resolution, color: bool = True, verbose: bool = True) -> str:
    """单个输入的识别结果（--identify）。"""
    paint = Painter(color)
    lines = [paint("━" * WIDTH, "cyan"), paint(" 链识别 · chaincmp", "bold", "cyan"),
             paint("━" * WIDTH, "cyan"), ""]
    lines.extend(_render_input("输入", res, paint, verbose, show_notes=False))
    if res.addresses:
        lines.append("")
        lines.append(f" {paint('地址', 'bold')}")
        for addr in res.addresses:
            lines.append(f"   · {addr}")
    if res.warnings:
        lines.append("")
        lines.append(f" {paint('⚠ 提醒', 'yellow', 'bold')}")
        for warning in res.warnings:
            lines.extend(_bullet(warning, paint, "yellow"))
    if res.notes and verbose:
        lines.append("")
        lines.append(f" {paint('ℹ 说明', 'grey', 'bold')}")
        for note in res.notes:
            lines.extend(_bullet(note, paint, "grey"))
    lines.append(paint("━" * WIDTH, "cyan"))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------

def resolution_to_dict(res: Resolution) -> dict:
    return {
        "input": res.label,
        "source": res.source,
        "chain": res.top,
        "chain_label": chains.label(res.top) if res.top else None,
        "certain": res.certain,
        "confidence": round(res.confidence, 4),
        "family_hint": res.family_hint,
        "candidates": [
            {"id": c, "label": chains.label(c), "score": res.scores.get(c, 0.0)}
            for c in res.candidates
        ],
        "addresses": res.addresses,
        "signals": [
            {
                "kind": s.kind,
                "detail": s.detail,
                "chains": list(s.chains),
                "confidence": round(s.confidence, 4),
                "warning": s.warning,
            }
            for s in res.signals
        ],
        "warnings": res.warnings,
        "notes": res.notes,
    }


def comparison_to_dict(result: Comparison) -> dict:
    return {
        "verdict": result.verdict,
        "same_chain": result.verdict == compare.SAME,
        "safe_to_transfer": result.is_safe,
        "confidence": round(result.confidence, 4),
        "headline": result.headline,
        "reason": result.reason,
        "shared_chains": [
            {"id": c, "label": chains.label(c)} for c in result.shared
        ],
        "risks": result.risks,
        "advice": result.advice,
        "inputs": {
            "a": resolution_to_dict(result.a),
            "b": resolution_to_dict(result.b),
        },
        "exit_code": EXIT_CODES[result.verdict],
    }
