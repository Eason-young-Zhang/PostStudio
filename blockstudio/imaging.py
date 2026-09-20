"""16-bit straight-alpha sRGB pixels. GUI previews never become master images."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import tifffile
from PySide6.QtCore import Qt
from PySide6.QtGui import QColorSpace, QImage, QImageReader

SRGB = QColorSpace(QColorSpace.NamedColorSpace.SRgb)


def to_qimage(a: np.ndarray) -> QImage:
    a = np.ascontiguousarray(a, dtype=np.uint16)
    h, w = a.shape[:2]
    q = QImage(a.data, w, h, a.strides[0], QImage.Format.Format_RGBA64).copy()
    q.setColorSpace(SRGB)
    return q


def from_qimage(q: QImage) -> np.ndarray:
    q = q.convertToFormat(QImage.Format.Format_RGBA64)
    return np.frombuffer(q.constBits(), np.uint16).reshape(q.height(), q.bytesPerLine() // 2)[:, :q.width()*4].reshape(q.height(), q.width(), 4).copy()


def orient(a, orientation):
    if orientation == 2: return a[:, ::-1].copy()
    if orientation == 3: return a[::-1, ::-1].copy()
    if orientation == 4: return a[::-1].copy()
    if orientation == 5: return a.transpose(1, 0, 2).copy()
    if orientation == 6: return np.rot90(a, -1).copy()
    if orientation == 7: return a.transpose(1, 0, 2)[::-1, ::-1].copy()
    if orientation == 8: return np.rot90(a, 1).copy()
    return a


def read_image(path: Path) -> np.ndarray:
    path = Path(path)
    if path.suffix.lower() in ('.tif', '.tiff'):
        with tifffile.TiffFile(path) as tf:
            if len(tf.pages) != 1:
                raise ValueError('首版只接收单页 TIFF；请先导出需要的页面。')
            page = tf.pages[0]
            if page.photometric not in (0, 1, 2):
                raise ValueError('TIFF 需要 RGB 或灰度格式，请先转换为 sRGB。')
            a = page.asarray()
            if a.dtype not in (np.uint8, np.uint16):
                raise ValueError('TIFF 需要 8 位或 16 位整数格式。')
            if page.planarconfig == 2 and a.ndim == 3:
                a = a.transpose(1, 2, 0)
            if a.ndim == 2: a = a[..., None]
            if a.shape[-1] not in (1, 2, 3, 4):
                raise ValueError('不支持此 TIFF 通道布局。')
            if a.dtype == np.uint8: a = a.astype(np.uint16) * 257
            if page.photometric == 0:
                a = a.copy(); a[..., 0] = 65535 - a[..., 0]
            if a.shape[-1] <= 2:
                rgb = np.repeat(a[..., :1], 3, axis=2)
                alpha = a[..., 1:2] if a.shape[-1] == 2 else np.full((*a.shape[:2], 1), 65535, np.uint16)
                a = np.concatenate((rgb, alpha), axis=2)
            elif a.shape[-1] == 3:
                a = np.concatenate((a, np.full((*a.shape[:2], 1), 65535, np.uint16)), axis=2)
            if page.extrasamples and int(page.extrasamples[0]) == 1:
                a = a.copy()
                for y in range(0, len(a), 128):
                    v = a[y:y+128]
                    alpha = v[..., 3:4].astype(np.float32)
                    v[..., :3] = np.clip(np.rint(v[..., :3].astype(np.float32) * 65535 / np.maximum(alpha, 1)), 0, 65535).astype(np.uint16)
            profile = page.tags.get(34675)
            if profile:
                cs = QColorSpace.fromIccProfile(bytes(profile.value))
                if not cs.isValid(): raise ValueError('无法读取 TIFF 色彩配置，请先转换为 sRGB。')
                if cs != SRGB:
                    q = to_qimage(a); q.setColorSpace(cs)
                    a = from_qimage(q.convertedToColorSpace(SRGB))
            tag = page.tags.get(274)
            return orient(a, int(tag.value) if tag else 1)
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    reader.setAllocationLimit(1024)
    q = reader.read()
    if q.isNull(): raise ValueError(f'无法读取图像：{reader.errorString()}')
    q = q.convertToFormat(QImage.Format.Format_RGBA64)
    if q.colorSpace().isValid() and q.colorSpace() != SRGB:
        q = q.convertedToColorSpace(SRGB)
    return from_qimage(q)


def write_tiff(path: Path, a: np.ndarray, compress=True):
    tifffile.imwrite(path, a, photometric='rgb', extrasamples=['unassalpha'],
                     compression='deflate' if compress else None,
                     predictor=2 if compress else False, metadata=None,
                     iccprofile=bytes(SRGB.iccProfile()), rowsperstrip=64)


def downsample2(a: np.ndarray) -> np.ndarray:
    """2×2 box average, alpha-weighted RGB; odd edge uses available samples."""
    h, w = a.shape[:2]
    out = np.empty(((h+1)//2, (w+1)//2, 4), np.uint16)
    for y in range(0, h, 128):
        band = a[y:y+128].astype(np.float64)
        sums = np.zeros(((len(band)+1)//2, (w+1)//2, 4), np.float64)
        count = np.zeros(sums.shape[:2], np.float64)
        for dy in (0, 1):
            for dx in (0, 1):
                part = band[dy::2, dx::2]
                ph, pw = part.shape[:2]
                sums[:ph, :pw, :3] += part[..., :3] * part[..., 3:4]
                sums[:ph, :pw, 3] += part[..., 3]
                count[:ph, :pw] += 1
        alpha = sums[..., 3].copy()
        sums[..., :3] /= np.maximum(alpha[..., None], 1)
        sums[..., 3] /= count
        out[y//2:y//2+len(sums)] = np.clip(np.rint(sums), 0, 65535).astype(np.uint16)
    return out


def preview(a: np.ndarray, edge=1600) -> QImage:
    q = to_qimage(a)
    if max(q.width(), q.height()) > edge:
        q = q.scaled(edge, edge, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return q.convertToFormat(QImage.Format.Format_RGBA8888)


def thumbnail_file(path: Path, a: np.ndarray):
    if not preview(a, 1100).save(str(path), 'PNG'):
        raise OSError('无法保存预览图。')


def flatten(a: np.ndarray, background='#ffffff') -> np.ndarray:
    color = np.array([int(background[i:i+2], 16)*257 for i in (1, 3, 5)], np.float32)
    out = np.empty_like(a)
    for y in range(0, len(a), 128):
        p = a[y:y+128]; alpha = p[..., 3:4].astype(np.float32)/65535
        out[y:y+128, :,:3] = np.rint(p[...,:3]*alpha + color*(1-alpha)).astype(np.uint16)
    out[...,3] = 65535
    return out


def export_image(path: Path, a: np.ndarray, fmt='JPEG', quality=95, half=False, background='#ffffff', compress=True):
    if half: a = downsample2(a)
    if fmt == 'TIFF':
        write_tiff(path, a, compress)
    elif fmt == 'JPEG':
        q = to_qimage(flatten(a, background)).convertToFormat(QImage.Format.Format_RGB888)
        if not q.save(str(path), 'JPEG', quality): raise OSError('JPEG 导出失败。')
    elif fmt == 'PNG':
        if not to_qimage(a).save(str(path), 'PNG'): raise OSError('PNG 导出失败。')
    else: raise ValueError('未知导出格式。')
