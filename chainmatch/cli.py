"""命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys

from . import chains, compare, image, report, resolve

_EPILOG = """\
使用示例
  对比两个网络名          chaincmp.py "USDT-TRC20" "波场"
  网络名 vs 收款地址      chaincmp.py "ERC20" 0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599
  两张收款码截图          chaincmp.py 收款码1.png 收款码2.jpg
  截图 + 文字             chaincmp.py wallet.png "BEP20"
  只识别一个输入          chaincmp.py -i TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t
  看支持哪些链            chaincmp.py --list
  看图片功能是否可用      chaincmp.py --check
  跑一遍内置示例          chaincmp.py --demo

参数是图片路径时会自动走图片识别；也可以用 img: 前缀强制，例如 img:./a.png

退出码：0=同链  1=不同链  2=无法确定  3=信息不足
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chaincmp.py",
        description="虚拟币链对比：给两个输入（链名 / 代币标准 / 地址 / 收款码截图），"
                    "判断它们是不是同一条链，避免转错链丢币。",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("inputs", nargs="*", metavar="输入",
                        help="要对比的两个输入；只给一个时等同于 --identify")
    parser.add_argument("-i", "--identify", metavar="输入",
                        help="只识别一个输入属于哪条链")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出，便于脚本调用")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示全部证据与候选链")
    parser.add_argument("--no-color", action="store_true", help="关闭彩色输出")
    parser.add_argument("--list", nargs="?", const="", metavar="关键字",
                        help="列出支持的链，可带关键字过滤")
    parser.add_argument("--check", action="store_true", help="检查图片识别（OCR/二维码）能力")
    parser.add_argument("--demo", action="store_true", help="运行内置示例")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    color = report.use_color(False if args.no_color else None)

    if args.check:
        return _cmd_check(args, color)
    if args.list is not None:
        return _cmd_list(args.list, args.json, color)
    if args.demo:
        return _cmd_demo(color, args.verbose)

    target = args.identify or (args.inputs[0] if len(args.inputs) == 1 else None)
    if target is not None and len(args.inputs) < 2:
        result = resolve.resolve(target)
        if args.json:
            print(json.dumps(report.resolution_to_dict(result), ensure_ascii=False, indent=2))
        else:
            print(report.render_resolution(result, color=color, verbose=True))
        return 0 if result.resolved else 3

    if len(args.inputs) < 2:
        parser.print_help()
        return 3
    if len(args.inputs) > 2:
        print("一次只能对比两个输入。", file=sys.stderr)
        return 3

    return _cmd_compare(args.inputs[0], args.inputs[1], args, color)


def _cmd_compare(left: str, right: str, args, color: bool) -> int:
    result = compare.compare(resolve.resolve(left), resolve.resolve(right))
    if args.json:
        print(json.dumps(report.comparison_to_dict(result), ensure_ascii=False, indent=2))
    else:
        print(report.render(result, color=color, verbose=args.verbose))
    return report.EXIT_CODES[result.verdict]


def _cmd_list(keyword: str, as_json: bool, color: bool) -> int:
    matched = chains.search(keyword)
    if as_json:
        print(json.dumps([
            {
                "id": c.id, "name_en": c.name_en, "name_zh": c.name_zh,
                "native": c.native, "family": c.family,
                "evm_chain_id": c.evm_chain_id,
                "standards": list(c.standards), "aliases": list(c.aliases),
            } for c in matched
        ], ensure_ascii=False, indent=2))
        return 0

    paint = report.Painter(color)
    print(paint(f"共支持 {len(chains.CHAINS)} 条链" +
                (f"，匹配“{keyword}”的有 {len(matched)} 条" if keyword else ""), "bold"))
    print()
    for chain in matched:
        standards = f"  标准：{'/'.join(chain.standards)}" if chain.standards else ""
        chain_id = f"  chainId={chain.evm_chain_id}" if chain.evm_chain_id else ""
        print(f"  {paint(report.pad(chain.id, 20), 'cyan')}"
              f"{report.pad(chain.label, 34)}{paint(standards + chain_id, 'grey')}")
        aliases = "、".join(chain.aliases[:10])
        print(paint(f"    常见写法：{aliases}", "grey"))
    if not matched:
        print("  没有匹配的链。")
    return 0


def _cmd_check(args, color: bool) -> int:
    caps = image.capabilities()
    if args.json:
        print(json.dumps(caps, ensure_ascii=False, indent=2))
        return 0
    paint = report.Painter(color)
    print(paint("图片识别能力检查", "bold"))
    print()
    labels = {
        "pyzbar": "二维码：pyzbar（推荐）",
        "opencv": "二维码：OpenCV",
        "zbarimg": "二维码：zbarimg 命令行",
        "pytesseract": "文字：pytesseract（推荐）",
        "tesseract": "文字：tesseract 命令行",
    }
    for key, label in labels.items():
        ok = caps[key]
        mark = paint("✓ 可用", "green") if ok else paint("✗ 缺失", "red")
        print(f"  {report.pad(label, 34)}{mark}")
    print()
    qr_ok = caps["pyzbar"] or caps["opencv"] or caps["zbarimg"]
    ocr_ok = caps["pytesseract"] or caps["tesseract"]
    print(f"  二维码识别：{paint('可用', 'green') if qr_ok else paint('不可用', 'yellow')}")
    print(f"  文字识别：  {paint('可用', 'green') if ocr_ok else paint('不可用', 'yellow')}")
    if not (qr_ok and ocr_ok):
        print()
        print(image.INSTALL_HINT)
    return 0 if (qr_ok or ocr_ok) else 1


_DEMO_CASES = [
    ("USDT-TRC20", "波场", "交易所网络名 vs 中文俗称"),
    ("ERC20", "TRC20", "最常见的转错链组合"),
    ("BEP20", "BEP2", "币安两条链，名字只差一位"),
    ("0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
     "0xdAC17F958D2ee523a2206206994597C13D831ec7",
     "两个 EVM 地址：看地址根本无法定链"),
    ("以太坊", "0xdAC17F958D2ee523a2206206994597C13D831ec7", "链名 + EVM 地址"),
    ("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "ERC20", "波场地址 vs 以太坊标准"),
    ("ethereum:0xdAC17F958D2ee523a2206206994597C13D831ec7@56", "BSC",
     "二维码里的 EIP-681 链接"),
    ("USDT", "USDC", "只有币种名，没有链"),
]


def _cmd_demo(color: bool, verbose: bool) -> int:
    for left, right, title in _DEMO_CASES:
        paint = report.Painter(color)
        print(paint(f"\n### {title}", "bold"))
        print(paint(f"    chaincmp.py \"{left}\" \"{right}\"", "grey"))
        print()
        result = compare.compare(resolve.resolve(left), resolve.resolve(right))
        print(report.render(result, color=color, verbose=verbose))
    return 0
