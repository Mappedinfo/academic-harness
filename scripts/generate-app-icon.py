#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import struct
import zlib
from pathlib import Path

RGBA = tuple[int, int, int, int]


ICNS_ENTRIES = [
    (16, b"icp4"),
    (32, b"icp5"),
    (64, b"icp6"),
    (128, b"ic07"),
    (256, b"ic08"),
    (512, b"ic09"),
    (1024, b"ic10"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Academic Harness .icns")
    parser.add_argument("output", type=Path, help="Destination .icns path")
    parser.add_argument("--preview-png", type=Path, help="Optional 1024px preview PNG")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    master = draw_icon(1024)
    if args.preview_png:
        args.preview_png.parent.mkdir(parents=True, exist_ok=True)
        write_png(args.preview_png, 1024, 1024, master)
    write_icns(args.output, master)
    return 0


def draw_icon(size: int) -> bytearray:
    pixels = bytearray(size * size * 4)
    shadow = (33, 41, 51, 58)
    fill_rounded_rect(pixels, size, 70, 78, 884, 876, 214, shadow)
    for y in range(0, size):
        t = y / max(1, size - 1)
        top = mix((251, 253, 248, 255), (238, 247, 242, 255), min(1.0, t * 1.7))
        bottom = mix((238, 247, 242, 255), (231, 240, 255, 255), max(0.0, t - 0.45) / 0.55)
        color = mix(top, bottom, max(0.0, t - 0.45))
        fill_rounded_rect_row(pixels, size, 82, 70, 860, 860, 208, y, color)

    dark_top = (31, 41, 51, 255)
    dark_bottom = (51, 65, 85, 255)
    fill_rounded_rect(pixels, size, 268, 240, 142, 544, 50, dark_top)
    fill_rounded_rect(pixels, size, 614, 240, 142, 544, 50, dark_bottom)
    fill_rounded_rect(pixels, size, 364, 428, 296, 156, 78, (38, 51, 65, 255))
    fill_rounded_rect(pixels, size, 381, 479, 262, 84, 42, (0, 168, 150, 255))

    stroke_polyline(pixels, size, [(284, 314), (524, 420), (742, 577)], 34, (47, 128, 237, 255))
    stroke_polyline(pixels, size, [(281, 723), (520, 596), (742, 451)], 28, (242, 201, 76, 242))

    fill_circle(pixels, size, 282, 312, 58, (47, 128, 237, 255))
    fill_circle(pixels, size, 742, 451, 52, (235, 87, 87, 255))
    fill_circle(pixels, size, 282, 722, 58, (242, 201, 76, 255))
    fill_circle(pixels, size, 742, 578, 54, (0, 168, 150, 255))
    fill_circle(pixels, size, 512, 521, 42, (255, 255, 255, 255))
    fill_circle(pixels, size, 512, 521, 22, (31, 41, 51, 255))
    return pixels


def fill_rounded_rect(pixels: bytearray, canvas: int, x: int, y: int, w: int, h: int, r: int, color: RGBA) -> None:
    for yy in range(y, y + h):
        fill_rounded_rect_row(pixels, canvas, x, y, w, h, r, yy, color)


def fill_rounded_rect_row(pixels: bytearray, canvas: int, x: int, y: int, w: int, h: int, r: int, yy: int, color: RGBA) -> None:
    if yy < y or yy >= y + h:
        return
    for xx in range(x, x + w):
        alpha = rounded_rect_coverage(xx + 0.5, yy + 0.5, x, y, w, h, r)
        if alpha > 0:
            blend(pixels, canvas, xx, yy, color, alpha)


def rounded_rect_coverage(px: float, py: float, x: int, y: int, w: int, h: int, r: int) -> float:
    cx = min(max(px, x + r), x + w - r)
    cy = min(max(py, y + r), y + h - r)
    distance = math.hypot(px - cx, py - cy) - r
    return clamp(0.5 - distance, 0.0, 1.0)


def fill_circle(pixels: bytearray, canvas: int, cx: int, cy: int, radius: int, color: RGBA) -> None:
    for yy in range(cy - radius - 2, cy + radius + 3):
        if yy < 0 or yy >= canvas:
            continue
        for xx in range(cx - radius - 2, cx + radius + 3):
            if xx < 0 or xx >= canvas:
                continue
            distance = math.hypot(xx + 0.5 - cx, yy + 0.5 - cy) - radius
            alpha = clamp(0.5 - distance, 0.0, 1.0)
            if alpha > 0:
                blend(pixels, canvas, xx, yy, color, alpha)


def stroke_polyline(pixels: bytearray, canvas: int, points: list[tuple[int, int]], width: int, color: RGBA) -> None:
    for start, end in zip(points, points[1:]):
        stroke_segment(pixels, canvas, start, end, width, color)
    radius = width // 2
    for x, y in points:
        fill_circle(pixels, canvas, x, y, radius, color)


def stroke_segment(
    pixels: bytearray,
    canvas: int,
    start: tuple[int, int],
    end: tuple[int, int],
    width: int,
    color: RGBA,
) -> None:
    x1, y1 = start
    x2, y2 = end
    radius = width / 2
    min_x = max(0, math.floor(min(x1, x2) - radius - 2))
    max_x = min(canvas - 1, math.ceil(max(x1, x2) + radius + 2))
    min_y = max(0, math.floor(min(y1, y2) - radius - 2))
    max_y = min(canvas - 1, math.ceil(max(y1, y2) + radius + 2))
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return
    for yy in range(min_y, max_y + 1):
        for xx in range(min_x, max_x + 1):
            t = ((xx + 0.5 - x1) * dx + (yy + 0.5 - y1) * dy) / length_sq
            t = clamp(t, 0.0, 1.0)
            px = x1 + t * dx
            py = y1 + t * dy
            distance = math.hypot(xx + 0.5 - px, yy + 0.5 - py) - radius
            alpha = clamp(0.5 - distance, 0.0, 1.0)
            if alpha > 0:
                blend(pixels, canvas, xx, yy, color, alpha)


def blend(pixels: bytearray, width: int, x: int, y: int, color: RGBA, coverage: float) -> None:
    if x < 0 or y < 0 or x >= width or y >= width:
        return
    sr, sg, sb, sa = color
    alpha = clamp((sa / 255.0) * coverage, 0.0, 1.0)
    i = (y * width + x) * 4
    dr, dg, db, da = pixels[i], pixels[i + 1], pixels[i + 2], pixels[i + 3]
    dst_alpha = da / 255.0
    out_alpha = alpha + dst_alpha * (1 - alpha)
    if out_alpha <= 0:
        return
    pixels[i] = int((sr * alpha + dr * dst_alpha * (1 - alpha)) / out_alpha)
    pixels[i + 1] = int((sg * alpha + dg * dst_alpha * (1 - alpha)) / out_alpha)
    pixels[i + 2] = int((sb * alpha + db * dst_alpha * (1 - alpha)) / out_alpha)
    pixels[i + 3] = int(out_alpha * 255)


def resize_rgba(source: bytearray, source_size: int, target_size: int) -> bytearray:
    factor = source_size // target_size
    if factor <= 1:
        return bytearray(source)
    out = bytearray(target_size * target_size * 4)
    area = factor * factor
    for ty in range(target_size):
        for tx in range(target_size):
            accum = [0, 0, 0, 0]
            for yy in range(ty * factor, (ty + 1) * factor):
                row = yy * source_size
                for xx in range(tx * factor, (tx + 1) * factor):
                    i = (row + xx) * 4
                    accum[0] += source[i]
                    accum[1] += source[i + 1]
                    accum[2] += source[i + 2]
                    accum[3] += source[i + 3]
            j = (ty * target_size + tx) * 4
            out[j:j + 4] = bytes(v // area for v in accum)
    return out


def write_png(path: Path, width: int, height: int, pixels: bytes | bytearray) -> None:
    path.write_bytes(encode_png(width, height, pixels))


def encode_png(width: int, height: int, pixels: bytes | bytearray) -> bytes:
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * stride:(y + 1) * stride])
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + png_chunk(b"IEND", b"")
    )


def write_icns(path: Path, master: bytearray) -> None:
    chunks: list[bytes] = []
    for size, code in ICNS_ENTRIES:
        pixels = master if size == 1024 else resize_rgba(master, 1024, size)
        png = encode_png(size, size, pixels)
        chunks.append(code + struct.pack(">I", len(png) + 8) + png)
    total_size = 8 + sum(len(chunk) for chunk in chunks)
    path.write_bytes(b"icns" + struct.pack(">I", total_size) + b"".join(chunks))


def png_chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)


def mix(a: RGBA, b: RGBA, t: float) -> RGBA:
    t = clamp(t, 0.0, 1.0)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))  # type: ignore[return-value]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


if __name__ == "__main__":
    raise SystemExit(main())
