#!/usr/bin/env python3
"""虚拟币链对比 —— 命令行入口。

    python3 chaincmp.py "USDT-TRC20" "波场"
    python3 chaincmp.py 收款码.png "ERC20"
    python3 chaincmp.py --help
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chainmatch.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
