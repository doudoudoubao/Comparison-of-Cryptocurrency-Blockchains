"""识别结果的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import chains

# 技术家族的中文叫法，用于"只能确定到家族"的场景
FAMILY_NAMES = {
    "evm": "EVM 兼容链",
    "cosmos": "Cosmos 生态链",
    "move": "Move 系链",
    "utxo": "UTXO 系链",
    "substrate": "Substrate 系链",
}


@dataclass
class Signal:
    """一条证据，例如"文本里出现了 TRC20"或"地址通过了 Base58Check"。"""

    kind: str                       # alias / standard / address / uri / qr / filename / fuzzy
    detail: str                     # 给人看的说明
    chains: tuple[str, ...]         # 该证据指向的链
    confidence: float               # 0~1
    warning: str = ""               # 需要提醒用户的问题
    family: str | None = None       # 该证据只能确定到某个技术家族时填（如 evm）


@dataclass
class Resolution:
    """一个输入（文本或图片）的识别结果。"""

    raw: str
    source: str = "text"            # text / image
    label: str = ""                 # 展示用的输入标签
    signals: list[Signal] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    candidates: tuple[str, ...] = ()
    family_hint: str | None = None  # 只能确定家族（如 evm）时填
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extracted_text: str = ""        # 图片 OCR / 二维码解出来的内容
    addresses: list[str] = field(default_factory=list)  # 输入里出现的地址
    conflicts: tuple[str, ...] = ()  # 互相矛盾的强证据，已是人话描述

    @property
    def confidence(self) -> float:
        """最高候选的置信度。

        内部分数保留完整精度（多条证据叠加后会非常接近 1），对外展示时封顶
        在 0.99：这类判断永远不该宣称 100% 确定。
        """
        if not self.candidates:
            return 0.0
        return min(max(self.scores.get(c, 0.0) for c in self.candidates), 0.99)

    @property
    def certain(self) -> bool:
        """是否唯一确定了一条链。

        输入里存在互相矛盾的强证据时（例如一张截图上同时有 ERC20 和 TRC20 的
        地址），无论分数多高都不算确定——分数高低不能替用户决定他要用哪一条。
        """
        return len(self.candidates) == 1 and self.confidence >= 0.7 and not self.conflicts

    @property
    def resolved(self) -> bool:
        return bool(self.candidates)

    @property
    def top(self) -> str | None:
        return self.candidates[0] if self.candidates else None

    def describe(self) -> str:
        """一句话描述识别到的链。"""
        if not self.candidates:
            return "无法识别"
        if self.conflicts:
            shown = " / ".join(self.conflicts[:4])
            return f"同时出现了多条链的信息（{shown}），需要你指明用哪一条"
        if len(self.candidates) == 1:
            return chains.label(self.candidates[0])

        family_name = FAMILY_NAMES.get(self.family_hint or "")
        if family_name and len(self.candidates) > 3:
            return f"{family_name}之一（{len(self.candidates)} 条候选，无法确定具体是哪条）"
        shown = "、".join(chains.label(c) for c in self.candidates[:3])
        more = f" 等 {len(self.candidates)} 条" if len(self.candidates) > 3 else ""
        return f"{shown}{more} 之一（无法确定）"
