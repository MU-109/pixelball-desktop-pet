"""从 idle.json 像素数据生成应用图标 pixelpet.ico"""
import json
import struct
import os

EXPR_DIR = os.path.dirname(os.path.abspath(__file__))

def generate_icon():
    # 读取 idle 表情的像素网格
    with open(os.path.join(EXPR_DIR, "expressions", "idle.json"), "r") as f:
        data = json.load(f)

    grid = data["grid"]  # 16x16, 每个元素是 [R,G,B] 或 null

    # 渲染为 RGBA 像素数组（16x16）
    pixels = []
    for row in grid:
        for cell in row:
            if cell is None:
                pixels.extend([0, 0, 0, 0])  # 透明
            else:
                pixels.extend([cell[0], cell[1], cell[2], 255])

    # 写入 ICO 文件（包含 16/32/48/64/256 五种尺寸）
    sizes = [16, 32, 48, 64, 256]
    icon_path = os.path.join(EXPR_DIR, "pixelpet.ico")
    _write_ico(icon_path, pixels, 16, 16, sizes)
    print(f"Icon generated: {icon_path}")
    return icon_path


def _write_ico(path, rgba, w, h, sizes):
    """将 RGBA 原始像素写入多尺寸 ICO 文件"""
    images = []
    for size in sizes:
        # 用最近邻放大
        scale = size // w
        scaled = _scale_rgba(rgba, w, h, scale)
        # 转换为 BMP + PNG 数据
        bmp_data = _rgba_to_bmp(scaled, size, size)
        png_data = _rgba_to_png(scaled, size, size)
        images.append((size, size, bmp_data, png_data))

    # ICO 文件头
    with open(path, "wb") as f:
        # ICONDIR
        f.write(struct.pack("<HHH", 0, 1, len(images)))
        # ICONDIRENTRY 数组
        offset = 6 + 16 * len(images)
        entries = []
        for sw, sh, bmp, png in images:
            entry_offset = offset
            # 用 PNG 数据以获得透明支持
            entry_size = len(png)
            entries.append((sw, sh, entry_offset, entry_size))
            offset += entry_size

        for sw, sh, entry_offset, entry_size in entries:
            w_val = 256 if sw == 256 else sw
            h_val = 256 if sh == 256 else sh
            f.write(struct.pack("<BBBBHHII",
                w_val, h_val, 0, 0, 1, 32, entry_size, entry_offset))

        # 写入图片数据
        for sw, sh, bmp, png in images:
            f.write(png)


def _scale_rgba(rgba, w, h, scale):
    """最近邻放大"""
    new_w, new_h = w * scale, h * scale
    new = bytearray(new_w * new_h * 4)
    for y in range(new_h):
        for x in range(new_w):
            sx, sy = x // scale, y // scale
            src_idx = (sy * w + sx) * 4
            dst_idx = (y * new_w + x) * 4
            new[dst_idx:dst_idx+4] = rgba[src_idx:src_idx+4]
    return bytes(new)


def _rgba_to_bmp(rgba, w, h):
    """RGBA → BMP (BGRA, bottom-up)"""
    row_size = ((w * 32 + 31) // 32) * 4
    pixel_data_size = row_size * h
    file_size = 40 + pixel_data_size

    # BITMAPINFOHEADER
    header = struct.pack("<IiiHHIIiiII",
        40, w, h * 2, 1, 32, 0,
        pixel_data_size, 0, 0, 0, 0)

    # 像素数据 (bottom-up, BGRA)
    pixel_data = bytearray()
    for y in range(h - 1, -1, -1):
        row = bytearray(row_size)
        for x in range(w):
            src = (y * w + x) * 4
            dst = x * 4
            row[dst] = rgba[src + 2]      # B
            row[dst + 1] = rgba[src + 1]   # G
            row[dst + 2] = rgba[src]        # R
            row[dst + 3] = rgba[src + 3]    # A
        pixel_data.extend(row)

    return header + bytes(pixel_data)


def _rgba_to_png(rgba, w, h):
    """RGBA → minimal PNG (zlib-compressed)"""
    import zlib

    def chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    # PNG 签名
    signature = b"\x89PNG\r\n\x1a\n"

    # IHDR
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)

    # IDAT: 每行加 filter byte 0 (None)，然后 zlib 压缩
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter: None
        raw.extend(rgba[y * w * 4:(y + 1) * w * 4])
    compressed = zlib.compress(bytes(raw))

    # IEND
    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")


if __name__ == "__main__":
    generate_icon()
