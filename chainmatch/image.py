"""从图片里读出文字和二维码。

图片能力是"可选增强"：装了 OCR / 二维码库就自动启用，没装也不会让整个工具
报错退出，而是明确告诉用户缺什么、怎么装、以及当下可以怎么绕过。

后端按可用性依次尝试：
    二维码：pyzbar → OpenCV → zbarimg 命令行
    文字：  pytesseract → tesseract 命令行
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field

IMAGE_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".heic",
})

INSTALL_HINT = """图片识别需要额外的库（核心的名称/地址对比不需要）：

  文字识别(OCR)   pip install pytesseract pillow
                  再装 tesseract 引擎与中文包：
                    Ubuntu/Debian  sudo apt install tesseract-ocr tesseract-ocr-chi-sim
                    macOS          brew install tesseract tesseract-lang
                    Windows        https://github.com/UB-Mannheim/tesseract/wiki

  二维码识别      pip install pyzbar pillow       （Linux 还需 sudo apt install libzbar0）
                  或  pip install opencv-python-headless

或者直接一次装齐：pip install -r requirements-optional.txt

暂时不想装也没关系：把截图里的网络名或地址复制出来，直接作为文本参数传给本工具，
识别与对比效果完全相同。"""


@dataclass
class ImageRead:
    """一张图片的读取结果。"""

    path: str
    ok: bool = False
    qr_payloads: list[str] = field(default_factory=list)
    text: str = ""
    backends: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def has_content(self) -> bool:
        return bool(self.qr_payloads or self.text.strip())


def is_image_path(value: str) -> bool:
    """判断一个命令行参数是不是图片文件。"""
    if not value or len(value) > 4096:
        return False
    if os.path.isfile(value):
        return os.path.splitext(value)[1].lower() in IMAGE_EXTS
    return False


def capabilities() -> dict[str, bool]:
    """当前环境具备哪些图片能力。"""
    return {
        "pyzbar": _can_import("pyzbar.pyzbar") and _can_import("PIL.Image"),
        "opencv": _can_import("cv2"),
        "zbarimg": shutil.which("zbarimg") is not None,
        "pytesseract": _can_import("pytesseract") and _can_import("PIL.Image"),
        "tesseract": shutil.which("tesseract") is not None,
    }


def _can_import(module: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def read(path: str) -> ImageRead:
    """读取图片，取出二维码内容和文字。"""
    result = ImageRead(path=path)
    if not os.path.isfile(path):
        result.error = f"找不到图片文件：{path}"
        return result

    caps = capabilities()
    result.qr_payloads = _read_qr(path, caps, result)
    result.text = _read_text(path, caps, result)

    if not caps["pyzbar"] and not caps["opencv"] and not caps["zbarimg"]:
        result.missing.append("二维码识别")
    if not caps["pytesseract"] and not caps["tesseract"]:
        result.missing.append("文字识别(OCR)")

    result.ok = result.has_content
    if not result.ok and not result.error:
        if result.missing:
            result.error = "当前环境缺少：" + "、".join(result.missing)
        else:
            result.error = "图片里没有读出二维码或可识别的文字"
    return result


# --------------------------------------------------------------------------
# 二维码
# --------------------------------------------------------------------------

def _read_qr(path: str, caps: dict[str, bool], result: ImageRead) -> list[str]:
    payloads: list[str] = []

    if caps["pyzbar"]:
        try:
            from PIL import Image
            from pyzbar.pyzbar import decode
            with Image.open(path) as img:
                for item in decode(img):
                    payloads.append(item.data.decode("utf-8", "replace"))
            result.backends.append("pyzbar")
        except Exception as exc:                      # 库装了但跑不起来
            result.backends.append(f"pyzbar(失败:{type(exc).__name__})")

    if not payloads and caps["opencv"]:
        try:
            import cv2
            image = cv2.imread(path)
            if image is not None:
                detector = cv2.QRCodeDetector()
                ok, decoded, _, _ = detector.detectAndDecodeMulti(image)
                if ok:
                    payloads.extend(d for d in decoded if d)
                else:
                    single, _, _ = detector.detectAndDecode(image)
                    if single:
                        payloads.append(single)
            result.backends.append("opencv")
        except Exception as exc:
            result.backends.append(f"opencv(失败:{type(exc).__name__})")

    if not payloads and caps["zbarimg"]:
        try:
            proc = subprocess.run(
                ["zbarimg", "-q", "--raw", path],
                capture_output=True, text=True, timeout=30, check=False,
            )
            payloads.extend(line for line in proc.stdout.splitlines() if line.strip())
            result.backends.append("zbarimg")
        except Exception as exc:
            result.backends.append(f"zbarimg(失败:{type(exc).__name__})")

    return [p.strip() for p in payloads if p.strip()]


# --------------------------------------------------------------------------
# OCR
# --------------------------------------------------------------------------

def _read_text(path: str, caps: dict[str, bool], result: ImageRead) -> str:
    if caps["pytesseract"]:
        try:
            import pytesseract
            from PIL import Image
            with Image.open(path) as img:
                image = img.convert("L")            # 转灰度，截图识别更稳
                for lang in ("chi_sim+eng", "eng"):
                    try:
                        text = pytesseract.image_to_string(image, lang=lang)
                    except Exception:
                        continue
                    if text.strip():
                        result.backends.append(f"pytesseract({lang})")
                        return text
            result.backends.append("pytesseract(无文字)")
            return ""
        except Exception as exc:
            result.backends.append(f"pytesseract(失败:{type(exc).__name__})")

    if caps["tesseract"]:
        for lang in ("chi_sim+eng", "eng"):
            try:
                proc = subprocess.run(
                    ["tesseract", path, "stdout", "-l", lang],
                    capture_output=True, text=True, timeout=60, check=False,
                )
            except Exception as exc:
                result.backends.append(f"tesseract(失败:{type(exc).__name__})")
                break
            if proc.returncode == 0 and proc.stdout.strip():
                result.backends.append(f"tesseract({lang})")
                return proc.stdout
    return ""
