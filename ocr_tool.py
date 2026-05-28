"""OCR tool module — recognize text from images using Tesseract portable version"""

import os
import pytesseract
from PIL import Image

# Tesseract portable path (inside project)
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_TESSERACT_EXE = os.path.join(_PROJECT_DIR, "tesseract-portable", "tesseract.exe")
_TESSDATA_DIR = os.path.join(_PROJECT_DIR, "tesseract-portable", "tessdata")

# Configure pytesseract
if os.path.exists(_TESSERACT_EXE):
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_EXE
os.environ.setdefault("TESSDATA_PREFIX", _TESSDATA_DIR)


def image_to_text(image_path: str = None, image_bytes: bytes = None,
                  languages: str = "chi_sim+eng") -> str:
    """Recognize text from image

    Args:
        image_path: Image file path
        image_bytes: Image byte data (use one of image_path or image_bytes)
        languages: Recognition language, default chi_sim+eng (Simplified Chinese + English)

    Returns:
        Recognized text string, empty string on failure
    """
    try:
        if image_bytes:
            img = Image.open(__import__('io').BytesIO(image_bytes))
        elif image_path:
            img = Image.open(image_path)
        else:
            return ""

        text = pytesseract.image_to_string(img, lang=languages)
        return text.strip()
    except Exception as e:
        return f"[OCR failed] {e}"


def pixmap_to_text(pixmap, languages: str = "chi_sim+eng") -> str:
    """Recognize text from QPixmap

    Args:
        pixmap: QPixmap object
        languages: Recognition language

    Returns:
        Recognized text string
    """
    try:
        from PyQt5.QtCore import QBuffer, QByteArray, QIODevice

        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        pixmap.save(buf, "PNG")
        buf.close()

        return image_to_text(image_bytes=ba.data(), languages=languages)
    except Exception as e:
        return f"[OCR failed] {e}"
