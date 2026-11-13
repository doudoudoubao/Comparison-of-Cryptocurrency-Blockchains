"""chainmatch —— 虚拟币链对比。

判断两个输入（链名、代币标准、收款地址、钱包收款码截图）是不是同一条链，
用来避免"USDT 从 ERC20 转到 TRC20 地址"这类会直接丢币的操作。

作为库使用：

    >>> from chainmatch import compare_inputs
    >>> result = compare_inputs("USDT-TRC20", "波场")
    >>> result.verdict
    'same'
    >>> result.headline
    '两边都是 波场 Tron (TRX)'

注意：`chainmatch.compare` 和 `chainmatch.resolve` 是子模块，函数请用
`compare_resolutions()` / `identify()`，避免遮蔽模块名。
"""

from __future__ import annotations

from . import compare as _compare_module
from . import resolve as _resolve_module
from .compare import DIFFERENT, POSSIBLY_SAME, SAME, UNKNOWN, Comparison
from .model import Resolution, Signal

__version__ = "1.0.0"

__all__ = [
    "Comparison", "Resolution", "Signal",
    "SAME", "DIFFERENT", "POSSIBLY_SAME", "UNKNOWN",
    "compare_inputs", "compare_resolutions", "identify",
]

compare_resolutions = _compare_module.compare


def compare_inputs(a: str, b: str) -> Comparison:
    """对比两个输入是否属于同一条链。输入可以是链名、地址或图片路径。"""
    return _compare_module.compare(_resolve_module.resolve(a), _resolve_module.resolve(b))


def identify(value: str) -> Resolution:
    """识别单个输入属于哪条链。"""
    return _resolve_module.resolve(value)
