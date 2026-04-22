"""
Post-build icon embedder using the Windows UpdateResource API.

Belt-and-braces layer on top of PyInstaller's --icon flag, which silently
fails when the project path contains spaces. This forces the icon into the
exe after PyInstaller has finished.
"""
import ctypes
import struct
from ctypes import wintypes


# Windows resource types
RT_ICON       = 3
RT_GROUP_ICON = 14


def _read_ico(ico_path: str):
    """Parse .ico file → list of (width, height, color_count, planes, bpp, image_bytes)."""
    with open(ico_path, "rb") as f:
        data = f.read()

    # ICONDIR header
    reserved, type_, count = struct.unpack_from("<HHH", data, 0)
    if type_ != 1:
        raise ValueError("Not a valid ICO file")

    entries = []
    offset = 6
    for i in range(count):
        (width, height, colors, reserved2, planes, bpp,
         size, data_offset) = struct.unpack_from("<BBBBHHLL", data, offset)
        image_bytes = data[data_offset:data_offset + size]
        entries.append({
            "width":  width or 256,
            "height": height or 256,
            "colors": colors,
            "planes": planes,
            "bpp":    bpp,
            "size":   size,
            "bytes":  image_bytes,
        })
        offset += 16

    return entries


def _build_group_icon(entries):
    """Build a GRPICONDIR resource from the parsed .ico entries."""
    out = struct.pack("<HHH", 0, 1, len(entries))
    for i, e in enumerate(entries, start=1):
        # GRPICONDIRENTRY is identical to ICONDIRENTRY except last field is ID (2 bytes)
        # instead of offset (4 bytes)
        out += struct.pack(
            "<BBBBHHLH",
            e["width"]  if e["width"]  < 256 else 0,
            e["height"] if e["height"] < 256 else 0,
            e["colors"],
            0,              # reserved
            e["planes"] or 1,
            e["bpp"]    or 32,
            e["size"],
            i,              # icon ID = sequential
        )
    return out


def embed_icon(exe_path: str, ico_path: str) -> None:
    """Replace the exe's icon with the given .ico file."""
    entries = _read_ico(ico_path)
    group = _build_group_icon(entries)

    k32 = ctypes.windll.kernel32
    k32.BeginUpdateResourceW.argtypes  = [wintypes.LPCWSTR, wintypes.BOOL]
    k32.BeginUpdateResourceW.restype   = wintypes.HANDLE
    k32.UpdateResourceW.argtypes       = [wintypes.HANDLE, wintypes.LPCWSTR,
                                          wintypes.LPCWSTR, wintypes.WORD,
                                          wintypes.LPVOID, wintypes.DWORD]
    k32.UpdateResourceW.restype        = wintypes.BOOL
    k32.EndUpdateResourceW.argtypes    = [wintypes.HANDLE, wintypes.BOOL]
    k32.EndUpdateResourceW.restype     = wintypes.BOOL

    LANG_NEUTRAL = 0  # language-neutral

    handle = k32.BeginUpdateResourceW(exe_path, False)
    if not handle:
        raise OSError(f"BeginUpdateResource failed: {ctypes.WinError()}")

    try:
        # Write each icon as a numbered RT_ICON resource
        for i, entry in enumerate(entries, start=1):
            buf = ctypes.c_buffer(entry["bytes"], len(entry["bytes"]))
            ok = k32.UpdateResourceW(
                handle,
                ctypes.c_wchar_p(RT_ICON),
                ctypes.cast(i, ctypes.c_wchar_p),  # Resource name = numeric ID
                LANG_NEUTRAL,
                ctypes.addressof(buf),
                len(entry["bytes"]),
            )
            if not ok:
                raise OSError(f"UpdateResource RT_ICON {i} failed")

        # Write the group-icon resource named "MAINICON"
        buf = ctypes.c_buffer(group, len(group))
        ok = k32.UpdateResourceW(
            handle,
            ctypes.c_wchar_p(RT_GROUP_ICON),
            ctypes.c_wchar_p("MAINICON"),
            LANG_NEUTRAL,
            ctypes.addressof(buf),
            len(group),
        )
        if not ok:
            raise OSError("UpdateResource RT_GROUP_ICON failed")

        if not k32.EndUpdateResourceW(handle, False):
            raise OSError(f"EndUpdateResource failed: {ctypes.WinError()}")

    except Exception:
        k32.EndUpdateResourceW(handle, True)  # discard on error
        raise
