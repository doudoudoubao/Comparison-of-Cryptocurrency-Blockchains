"""真实图片的端到端测试。

和 test_image.py 的 mock 不同，这里真的生成图片、真的跑 OCR 和二维码解码。
装了可选依赖的机器上才会执行，否则整体跳过——核心功能本来就不依赖它们。

跑这些用例需要：
    pip install pillow qrcode pytesseract
    sudo apt install tesseract-ocr tesseract-ocr-chi-sim
    # 二维码还需要 pyzbar + libzbar0，或 opencv-python-headless
"""

import os
import tempfile
import unittest

from chainmatch import compare_inputs, identify, image

TRON_ADDR = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
EVM_ADDR = "0xdAC17F958D2ee523a2206206994597C13D831ec7"

_CAPS = image.capabilities()
_OCR_READY = _CAPS["pytesseract"] or _CAPS["tesseract"]
_QR_READY = _CAPS["pyzbar"] or _CAPS["opencv"] or _CAPS["zbarimg"]

try:
    from PIL import Image, ImageDraw
    _PIL_READY = True
except ImportError:
    _PIL_READY = False

try:
    import qrcode
    _QRGEN_READY = True
except ImportError:
    _QRGEN_READY = False


def _screenshot(lines, path, width=520):
    """画一张模拟的交易所提币页截图。"""
    img = Image.new("RGB", (width, 26 * len(lines) + 30), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((14, 14 + 26 * i), line, fill="black")
    img.resize((width * 2, img.height * 2), Image.LANCZOS).save(path)
    return path


@unittest.skipUnless(_PIL_READY and _OCR_READY, "需要 pillow + tesseract")
class TestRealOcr(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_withdraw_screenshot_resolves_network(self):
        path = _screenshot([
            "Withdraw USDT",
            "Network   TRC20",
            f"Address   {TRON_ADDR}",
            "Amount    100.00 USDT",
        ], os.path.join(self.tmp.name, "withdraw.png"))
        result = identify(path)
        self.assertEqual(result.source, "image")
        self.assertEqual(result.top, "tron")

    def test_two_screenshots_are_compared(self):
        left = _screenshot(["Withdraw USDT", "Network   TRC20", f"Address   {TRON_ADDR}"],
                           os.path.join(self.tmp.name, "a.png"))
        right = _screenshot(["Deposit USDT", "Network   ERC20", f"Address   {EVM_ADDR}"],
                            os.path.join(self.tmp.name, "b.png"))
        result = compare_inputs(left, right)
        self.assertEqual(result.verdict, "different")
        self.assertEqual(result.a.top, "tron")
        self.assertEqual(result.b.top, "ethereum")

    def test_misread_address_is_admitted_not_hidden(self):
        """OCR 认错地址里的字符时，必须说出来。

        实测 tesseract 会把 TR7NHqjeKQx… 读成 TR7 NHgjeKOx…（q→g、Q→O）。
        校验和挡住了错误地址，但用户需要知道"这次没核对地址"，不能默默略过。
        """
        path = _screenshot([
            "Withdraw USDT", "Network   TRC20", f"Address   {TRON_ADDR}",
        ], os.path.join(self.tmp.name, "misread.png"))
        result = identify(path)
        # 要么准确读出了地址，要么明确承认没读准——不允许两者皆非
        read_correctly = TRON_ADDR in result.addresses
        admitted = any("可靠读出" in w for w in result.warnings)
        self.assertTrue(read_correctly or admitted,
                        f"地址既没读对也没承认读不准：{result.addresses} / {result.warnings}")

    def test_never_reports_a_wrong_address(self):
        """宁可读不出，也不能报出一个错的地址。"""
        path = _screenshot([
            "Network TRC20", f"Address {TRON_ADDR}",
        ], os.path.join(self.tmp.name, "addr.png"))
        for found in identify(path).addresses:
            self.assertEqual(found, TRON_ADDR, f"报出了一个图里没有的地址：{found}")


@unittest.skipUnless(_QRGEN_READY and _QR_READY, "需要 qrcode + 二维码识别后端")
class TestRealQrCode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _qr(self, payload, name="qr.png"):
        path = os.path.join(self.tmp.name, name)
        qrcode.make(payload).save(path)
        return path

    def test_eip681_chain_id_beats_the_scheme(self):
        """收款码写 ethereum: 但 @56 说明是 BSC——必须按 chainId 来。"""
        path = self._qr(f"ethereum:{EVM_ADDR}@56")
        result = identify(path)
        self.assertEqual(result.top, "bsc")
        self.assertTrue(result.certain)

    def test_qr_versus_wrong_network_name(self):
        result = compare_inputs(self._qr(f"ethereum:{EVM_ADDR}@56"), "ERC20")
        self.assertEqual(result.verdict, "different")

    def test_tron_uri_qr(self):
        result = compare_inputs(self._qr(f"tron:{TRON_ADDR}"), "波场")
        self.assertEqual(result.verdict, "same")

    def test_bitcoin_uri_qr_with_amount(self):
        addr = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
        result = compare_inputs(self._qr(f"bitcoin:{addr}?amount=0.01"), "比特币")
        self.assertEqual(result.verdict, "same")


class TestCapabilityReporting(unittest.TestCase):
    def test_capabilities_reflect_real_importability(self):
        """--check 不能把"装了但跑不起来"的后端报成可用。

        pyzbar 装了却缺 libzbar0 时，包找得到、导入会抛 ImportError。
        """
        caps = image.capabilities()
        if caps["pyzbar"]:
            from pyzbar.pyzbar import decode        # noqa: F401  能报可用就必须能导入
        if caps["pytesseract"]:
            import pytesseract                      # noqa: F401
        if caps["opencv"]:
            import cv2                              # noqa: F401


if __name__ == "__main__":
    unittest.main()
