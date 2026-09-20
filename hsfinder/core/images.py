# -*- coding: utf-8 -*-
"""图片解码与缩放。

这里有两条路，目的是**不强迫用户安装任何东西**：

1. 有 Pillow：它解码质量好、缩放快，优先用；
2. 没有 Pillow：用 Windows 自带的 ``gdiplus.dll``（系统组件，必然存在）
   解码 JPEG 并做高质量缩放，最后手写成 PNG 交给 tkinter。

tkinter 的 ``PhotoImage`` 只认 GIF/PNG/PPM，而 wiki 原画全是 JPEG，
所以无论哪条路都必须先转码。
"""
import base64
import struct
import zlib


# ---------------------------------------------------------------------------
# Pillow（可选）
# ---------------------------------------------------------------------------
def has_pillow():
    try:
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


def decode_pil(data):
    """字节 -> PIL Image；没有 Pillow 或解码失败时返回 None。"""
    try:
        import io
        from PIL import Image
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None


def fit_pil(im, box_w, box_h):
    """按比例缩放到铺满 box 宽（高度不够时以高度为准）。

    只缩小不放大：小图放大只会发虚。
    用 LANCZOS 精确缩放，而不是 tk 的 subsample —— 后者只能按 1/n 整数倍
    缩小，结果常常比面板窄一截，看着就像没对齐。
    """
    try:
        from PIL import Image
    except Exception:
        return im
    w, h = im.size
    box_w = max(40, int(box_w))
    box_h = max(40, int(box_h))
    scale = min(box_w / w, box_h / h, 1.0)
    if scale >= 0.999:
        return im
    return im.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                     Image.LANCZOS)


def pil_to_photoimage(im):
    """PIL Image -> tk PhotoImage。失败返回 None。"""
    try:
        from PIL import ImageTk
        return ImageTk.PhotoImage(im)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 裸像素 -> PNG（两条路共用）
# ---------------------------------------------------------------------------
def rgb_to_png_b64(w, h, rgb):
    """裸 RGB 像素 -> PNG 的 base64（``tk.PhotoImage(data=...)`` 直接可吃）。"""
    png = bytearray(b"\x89PNG\r\n\x1a\n")

    def chunk(tag, payload):
        png.extend(struct.pack(">I", len(payload)))
        png.extend(tag)
        png.extend(payload)
        png.extend(struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)
        raw.extend(rgb[y * stride:(y + 1) * stride])
    chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    chunk(b"IEND", b"")
    return base64.b64encode(bytes(png))


# ---------------------------------------------------------------------------
# GDI+ 兜底（无 Pillow 时）
# ---------------------------------------------------------------------------
class GdiPlus:
    """GDI+ 的最小 ctypes 封装。

    只用它做两件事：解码常见图片格式、做一次高质量缩放。
    单例：GdiplusStartup 全局只需一次。
    """
    _instance = None

    def __init__(self):
        import ctypes
        from ctypes import wintypes as wt

        class StartupInput(ctypes.Structure):
            _fields_ = [("GdiplusVersion", wt.UINT),
                        ("DebugEventCallback", ctypes.c_void_p),
                        ("SuppressBackgroundThread", wt.BOOL),
                        ("SuppressExternalCodecs", wt.BOOL)]

        self.ctypes, self.wt = ctypes, wt
        gdi = ctypes.WinDLL("gdiplus")
        ole = ctypes.WinDLL("ole32")
        sh = ctypes.WinDLL("shlwapi")

        gdi.GdiplusStartup.argtypes = [ctypes.POINTER(ctypes.c_void_p),
                                       ctypes.POINTER(StartupInput), ctypes.c_void_p]
        gdi.GdiplusStartup.restype = ctypes.c_int
        ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wt.DWORD]
        sh.SHCreateMemStream.argtypes = [ctypes.c_char_p, wt.UINT]
        sh.SHCreateMemStream.restype = ctypes.c_void_p

        self.gdi, self.ole, self.sh = gdi, ole, sh
        self.token = ctypes.c_void_p()
        self._input = StartupInput(1, None, False, False)
        self.available = gdi.GdiplusStartup(ctypes.byref(self.token),
                                            ctypes.byref(self._input), None) == 0

    @classmethod
    def get(cls):
        """取单例；初始化失败返回 None（并记住失败，不反复重试）。"""
        if cls._instance is None:
            try:
                cls._instance = cls()
            except Exception:
                cls._instance = False
        return cls._instance or None

    # -- 解码 ---------------------------------------------------------------
    def decode(self, data):
        """图片字节 -> ``(宽, 高, RGB bytes)``；失败返回 None。"""
        ctypes, wt, gdi = self.ctypes, self.wt, self.gdi
        self.ole.CoInitializeEx(None, 2)                  # APARTMENTTHREADED
        stream = self.sh.SHCreateMemStream(data, len(data))
        if not stream:
            return None
        bitmap = ctypes.c_void_p()
        try:
            gdi.GdipCreateBitmapFromStream.argtypes = [ctypes.c_void_p,
                                                       ctypes.POINTER(ctypes.c_void_p)]
            gdi.GdipCreateBitmapFromStream.restype = ctypes.c_int
            if gdi.GdipCreateBitmapFromStream(ctypes.c_void_p(stream),
                                             ctypes.byref(bitmap)) != 0 or not bitmap:
                return None
            gdi.GdipGetImageWidth.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.UINT)]
            gdi.GdipGetImageHeight.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.UINT)]
            w, h = wt.UINT(0), wt.UINT(0)
            gdi.GdipGetImageWidth(bitmap, ctypes.byref(w))
            gdi.GdipGetImageHeight(bitmap, ctypes.byref(h))
            w, h = int(w.value), int(h.value)
            if not (0 < w <= 20000 and 0 < h <= 20000):
                return None
            return self._pixels(bitmap, w, h)
        finally:
            if bitmap:
                gdi.GdipDisposeImage.argtypes = [ctypes.c_void_p]
                gdi.GdipDisposeImage(bitmap)
            self._release_stream(stream)

    def _release_stream(self, stream):
        """IStream::Release（虚表第 3 项）。"""
        ctypes, wt = self.ctypes, self.wt
        try:
            vtbl = ctypes.cast(ctypes.c_void_p(stream),
                               ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            ctypes.WINFUNCTYPE(wt.ULONG, ctypes.c_void_p)(vtbl[2])(ctypes.c_void_p(stream))
        except Exception:
            pass

    def _pixels(self, bitmap, w, h):
        """把 GDI+ 位图读成 RGB bytes（逐行去掉行填充）。"""
        ctypes, wt, gdi = self.ctypes, self.wt, self.gdi
        rect = (ctypes.c_uint32 * 4)(0, 0, w, h)

        class BitmapData(ctypes.Structure):
            _fields_ = [("width", wt.UINT), ("height", wt.UINT),
                        ("stride", ctypes.c_int), ("pixel_format", ctypes.c_int),
                        ("scan0", ctypes.c_void_p), ("reserved", ctypes.c_void_p)]

        gdi.GdipBitmapLockBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.UINT,
                                           ctypes.c_int, ctypes.POINTER(BitmapData)]
        gdi.GdipBitmapUnlockBits.argtypes = [ctypes.c_void_p,
                                             ctypes.POINTER(BitmapData)]
        info = BitmapData()
        # ImageLockModeRead = 1，PixelFormat24bppRGB = 0x00021808
        if gdi.GdipBitmapLockBits(bitmap, rect, 1, 0x00021808,
                                  ctypes.byref(info)) != 0:
            return None
        try:
            stride = info.stride
            buf = ctypes.string_at(info.scan0, stride * h)
        finally:
            gdi.GdipBitmapUnlockBits(bitmap, ctypes.byref(info))
        if stride == w * 3:
            return w, h, buf
        rgb = bytearray(w * h * 3)
        for y in range(h):
            rgb[y * w * 3:(y + 1) * w * 3] = buf[y * stride:y * stride + w * 3]
        return w, h, bytes(rgb)

    # -- 缩放 ---------------------------------------------------------------
    def _resize_rgb(self, w, h, rgb, nw, nh):
        """用 GDI+ 做一次高质量缩放，返回 ``(nw, nh, rgb)``。"""
        ctypes, gdi = self.ctypes, self.gdi
        stride = (w * 3 + 3) & ~3
        if stride != w * 3:
            return None
        buf = ctypes.create_string_buffer(rgb, len(rgb))
        gdi.GdipCreateBitmapFromScan0.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        gdi.GdipCreateBitmapFromScan0.restype = ctypes.c_int
        src, dst, g = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        try:
            # PixelFormat24bppRGB = 0x00021808
            if gdi.GdipCreateBitmapFromScan0(w, h, stride, 0x00021808, buf,
                                             ctypes.byref(src)) != 0 or not src:
                return None
            if gdi.GdipCreateBitmapFromScan0(nw, nh, 0, 0x00021808, None,
                                             ctypes.byref(dst)) != 0 or not dst:
                return None
            gdi.GdipGetImageGraphicsContext.argtypes = [ctypes.c_void_p,
                                                        ctypes.POINTER(ctypes.c_void_p)]
            if gdi.GdipGetImageGraphicsContext(dst, ctypes.byref(g)) != 0 or not g:
                return None
            gdi.GdipSetInterpolationMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
            gdi.GdipSetInterpolationMode(g, 7)            # HighQualityBicubic
            gdi.GdipSetPixelOffsetMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
            gdi.GdipSetPixelOffsetMode(g, 2)              # Half
            gdi.GdipDrawImageRectI.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
            gdi.GdipDrawImageRectI(g, src, 0, 0, nw, nh)
            gdi.GdipDeleteGraphics.argtypes = [ctypes.c_void_p]
            gdi.GdipDeleteGraphics(g)
            g = ctypes.c_void_p()
            return self._pixels(dst, nw, nh)
        finally:
            if g:
                gdi.GdipDeleteGraphics.argtypes = [ctypes.c_void_p]
                gdi.GdipDeleteGraphics(g)
            gdi.GdipDisposeImage.argtypes = [ctypes.c_void_p]
            if src:
                gdi.GdipDisposeImage(src)
            if dst:
                gdi.GdipDisposeImage(dst)

    def load_scaled_png(self, data, box_w, box_h):
        """解码 + 缩放到 box 内 + 编码 PNG，返回 base64；失败返回 None。"""
        got = self.decode(data)
        if not got:
            return None
        w, h, rgb = got
        scale = min(box_w / w, box_h / h, 1.0)
        nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        if (nw, nh) != (w, h):
            resized = self._resize_rgb(w, h, rgb, nw, nh)
            if resized:
                nw, nh, rgb = resized
        return rgb_to_png_b64(nw, nh, rgb)


__all__ = ["has_pillow", "decode_pil", "fit_pil", "pil_to_photoimage",
           "rgb_to_png_b64", "GdiPlus"]
