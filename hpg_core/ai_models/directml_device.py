"""Waehlt einen diskreten DXGI-Adapter fuer ONNX/DirectML aus."""

import ctypes as ct
import sys
from ctypes import wintypes as wt


class _Guid(ct.Structure):
    _fields_ = [("data1", wt.DWORD), ("data2", wt.WORD), ("data3", wt.WORD),
                ("data4", ct.c_ubyte * 8)]


class _Luid(ct.Structure):
    _fields_ = [("low", wt.DWORD), ("high", wt.LONG)]


class _AdapterDesc1(ct.Structure):
    _fields_ = [("name", wt.WCHAR * 128), ("vendor", wt.UINT),
                ("device", wt.UINT), ("subsystem", wt.UINT),
                ("revision", wt.UINT), ("dedicated_video", ct.c_size_t),
                ("dedicated_system", ct.c_size_t), ("shared_system", ct.c_size_t),
                ("luid", _Luid), ("flags", wt.UINT)]


def _method(obj, index, result_type, *arg_types):
    table = ct.cast(obj, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
    return ct.WINFUNCTYPE(result_type, ct.c_void_p, *arg_types)(table[index])


def list_adapters():
    """Liest DXGI-Index, Name und dedizierten Speicher ohne GPU-Session."""
    if sys.platform != "win32":
        return []
    iid = _Guid(0x770aae78, 0xf26f, 0x4dba,
                (ct.c_ubyte * 8)(0xa8, 0x29, 0x25, 0x3c, 0x83, 0xd1, 0xb3, 0x87))
    create = ct.WinDLL("dxgi.dll").CreateDXGIFactory1
    create.argtypes = [ct.POINTER(_Guid), ct.POINTER(ct.c_void_p)]
    create.restype = wt.LONG
    factory = ct.c_void_p()
    if create(ct.byref(iid), ct.byref(factory)) != 0:
        return []
    adapters = []
    try:
        enum = _method(factory, 12, wt.LONG, wt.UINT, ct.POINTER(ct.c_void_p))
        for index in range(16):
            adapter = ct.c_void_p()
            status = enum(factory, index, ct.byref(adapter))
            if status & 0xffffffff == 0x887a0002:  # DXGI_ERROR_NOT_FOUND
                break
            if status != 0:
                break
            try:
                desc = _AdapterDesc1()
                if _method(adapter, 10, wt.LONG, ct.POINTER(_AdapterDesc1))(
                        adapter, ct.byref(desc)) == 0:
                    adapters.append({"index": index, "name": desc.name,
                                     "dedicated_video": desc.dedicated_video,
                                     "vendor": desc.vendor, "device": desc.device,
                                     "flags": desc.flags})
            finally:
                _method(adapter, 2, wt.ULONG)(adapter)
    finally:
        _method(factory, 2, wt.ULONG)(factory)
    return adapters


def choose_device_id(adapters=None):
    """Bevorzugt RX 7800 XT, sonst die groesste Karte mit mindestens 1 GiB VRAM.

    Keine passende Karte ergibt ``None``; der Aufrufer verwendet dann CPU.
    """
    if adapters is None:
        adapters = list_adapters()
    candidates = [adapter for adapter in adapters
                  if adapter["vendor"] != 0x1414
                  and not (adapter["flags"] & 2)  # DXGI_ADAPTER_FLAG_SOFTWARE
                  and not _is_integrated(adapter["name"])
                  and adapter["dedicated_video"] >= 1024 ** 3]
    if not candidates:
        return None
    target = [adapter for adapter in candidates
              if adapter["name"].strip().casefold() == "amd radeon rx 7800 xt"]
    selected = max(target or candidates,
                   key=lambda adapter: (adapter["dedicated_video"], -adapter["index"]))
    return selected["index"]


def _is_integrated(name):
    """Bekannte iGPU-Bezeichnungen auch bei reserviertem VRAM ausschließen."""
    normalized = name.strip().casefold()
    return (normalized == "amd radeon(tm) graphics"
            or normalized.startswith(("intel(r) uhd graphics", "intel(r) iris",
                                      "intel(r) arc(tm) graphics")))
