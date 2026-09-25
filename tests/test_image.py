"""图片输入的测试。

本机不一定装了 OCR / 二维码库，所以这里分两部分：
1. 降级路径必须稳（缺库时给提示，而不是崩溃）；
2. 有后端时的解析逻辑用 mock 驱动，不依赖真实的 tesseract。
"""

import os
import subprocess
import tempfile
import unittest
from unittest import mock

from chainmatch import compare_inputs, identify, image, resolve


class TestImageDetection(unittest.TestCase):
    def test_is_image_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = os.path.join(tmp, "a.png")
            open(png, "wb").close()
            txt = os.path.join(tmp, "a.txt")
            open(txt, "wb").close()
            self.assertTrue(image.is_image_path(png))
            self.assertFalse(image.is_image_path(txt))
            self.assertFalse(image.is_image_path(os.path.join(tmp, "missing.png")))
            self.assertFalse(image.is_image_path("ERC20"))
            self.assertFalse(image.is_image_path(""))

    def test_capabilities_returns_flags(self):
        caps = image.capabilities()
        self.assertEqual(set(caps), {"pyzbar", "opencv", "zbarimg", "pytesseract", "tesseract"})
        self.assertTrue(all(isinstance(v, bool) for v in caps.values()))


class TestDegradation(unittest.TestCase):
    """缺少 OCR 能力时，必须给出可操作的提示，而不是报错退出。"""

    def test_missing_file(self):
        result = image.read("/definitely/not/here.png")
        self.assertFalse(result.ok)
        self.assertIn("找不到图片", result.error)

    def test_resolve_missing_image_is_graceful(self):
        result = identify("img:/definitely/not/here.png")
        self.assertFalse(result.resolved)
        self.assertTrue(result.warnings)

    def test_compare_with_unreadable_image(self):
        result = compare_inputs("img:/definitely/not/here.png", "TRC20")
        self.assertEqual(result.verdict, "unknown")
        self.assertTrue(result.advice)

    def test_missing_image_path_is_reported_not_silently_matched_as_text(self):
        """"./qr-eth.png" 不存在时要报找不到文件，而不是拿文件名里的 eth 当结论。"""
        result = identify("./qr-eth.png")
        self.assertEqual(result.source, "image")
        self.assertTrue(any("找不到图片" in w for w in result.warnings))
        self.assertFalse(result.certain)

    def test_install_hint_mentions_how_to_work_around_it(self):
        self.assertIn("pytesseract", image.INSTALL_HINT)
        self.assertIn("pyzbar", image.INSTALL_HINT)
        # 没装库的用户也要知道还能怎么用
        self.assertIn("复制", image.INSTALL_HINT)

    def test_filename_is_only_a_weak_hint(self):
        """文件名里的链名可以用作线索，但绝不能当成确定结论。"""
        with tempfile.TemporaryDirectory() as tmp:
            png = os.path.join(tmp, "usdt-trc20收款码.png")
            open(png, "wb").close()
            result = identify(png)
            if result.resolved:                       # 装了 OCR 的机器上读不出内容
                self.assertEqual(result.top, "tron")
                self.assertFalse(result.certain)      # 光靠文件名不能算确定
                self.assertTrue(any("文件名" in w for w in result.warnings))


class TestMockedBackends(unittest.TestCase):
    """用 mock 模拟装了 tesseract / zbarimg 的机器。"""

    def _fake_png(self, tmp, name="shot.png"):
        path = os.path.join(tmp, name)
        open(path, "wb").close()
        return path

    def test_ocr_text_drives_recognition(self):
        ocr_text = "提币\n币种 USDT\n网络 Tron (TRC20)\n地址 TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
        caps = dict.fromkeys(("pyzbar", "opencv", "zbarimg", "pytesseract"), False)
        caps["tesseract"] = True
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fake_png(tmp)
            with mock.patch.object(image, "capabilities", return_value=caps), \
                 mock.patch.object(subprocess, "run",
                                   return_value=subprocess.CompletedProcess(
                                       [], 0, stdout=ocr_text, stderr="")):
                result = resolve.resolve(path)
        self.assertEqual(result.top, "tron")
        self.assertTrue(result.certain)
        self.assertIn("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", result.addresses)

    def test_qr_payload_with_chain_id(self):
        payload = "ethereum:0xdAC17F958D2ee523a2206206994597C13D831ec7@56"
        caps = dict.fromkeys(("pyzbar", "opencv", "pytesseract", "tesseract"), False)
        caps["zbarimg"] = True
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fake_png(tmp)
            with mock.patch.object(image, "capabilities", return_value=caps), \
                 mock.patch.object(subprocess, "run",
                                   return_value=subprocess.CompletedProcess(
                                       [], 0, stdout=payload + "\n", stderr="")):
                result = resolve.resolve(path)
        self.assertEqual(result.top, "bsc")
        self.assertTrue(result.certain)

    def test_two_screenshots_compared(self):
        left = "网络 ERC20\n地址 0xdAC17F958D2ee523a2206206994597C13D831ec7"
        right = "网络 TRC20\n地址 TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
        caps = dict.fromkeys(("pyzbar", "opencv", "zbarimg", "pytesseract"), False)
        caps["tesseract"] = True

        def fake_run(cmd, **kwargs):
            text = left if "a.png" in cmd[1] else right
            return subprocess.CompletedProcess(cmd, 0, stdout=text, stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            a = self._fake_png(tmp, "a.png")
            b = self._fake_png(tmp, "b.png")
            with mock.patch.object(image, "capabilities", return_value=caps), \
                 mock.patch.object(subprocess, "run", side_effect=fake_run):
                result = compare_inputs(a, b)
        self.assertEqual(result.verdict, "different")
        self.assertEqual(result.a.top, "ethereum")
        self.assertEqual(result.b.top, "tron")

    def test_backend_crash_does_not_break_the_run(self):
        caps = dict.fromkeys(("pyzbar", "opencv", "zbarimg", "pytesseract"), False)
        caps["tesseract"] = True
        with tempfile.TemporaryDirectory() as tmp:
            path = self._fake_png(tmp)
            with mock.patch.object(image, "capabilities", return_value=caps), \
                 mock.patch.object(subprocess, "run", side_effect=OSError("boom")):
                result = resolve.resolve(path)
        self.assertFalse(result.resolved)
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
