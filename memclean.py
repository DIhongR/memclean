# -*- coding: utf-8 -*-
"""
内存清理小工具 (Windows 10/11)

功能:
  * 平时完全隐藏, 只在系统托盘显示一个图标
  * 托盘图标实时显示当前内存占用百分比 (绿/黄/红三色)
  * 双击 Alt 键 (0.45 秒内连按两下) 立即清理内存
  * 右键托盘图标: 手动清理 / 自动清理开关 / 清理强度 / 开机自启 / 详情 / 退出
  * 鼠标悬停托盘图标显示详细内存信息

依赖: Python 3.8+ ; Pillow(绘图) ; psutil(可选, 没有则用 EnumProcesses)
用法: pythonw.exe memclean.py     (无控制台窗口运行)
      python  memclean.py --help  (查看命令行参数)
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import threading
import time
from ctypes import wintypes as wt

if sys.platform != "win32":
    raise SystemExit("本工具仅支持 Windows")

APP_NAME = "内存清理工具"
APP_ID = "MemCleanTray"
APP_AUMID = "MemCleanTray.MemoryCleaner"      # 本进程通知使用的 AppUserModelID
APP_VERSION = "1.0"
MUTEX_NAME = r"Local\MemCleanTray_9F2A4C7B"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(SCRIPT_DIR, "settings.json")
LOG_PATH = os.path.join(SCRIPT_DIR, "memclean.log")
_DEBUG = bool(os.environ.get("MEMCLEAN_DEBUG"))
_log_lock = threading.Lock()


def log(msg):
    """设置环境变量 MEMCLEAN_DEBUG=1 时把诊断信息写入 memclean.log。"""
    if not _DEBUG:
        return
    try:
        with _log_lock:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass

# ---------------------------------------------------------------- win32 常量
WM_APP = 0x8000
WM_TRAYICON = WM_APP + 1
WM_CLEAN_DONE = WM_APP + 2
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_TIMER = 0x0113
WM_HOTKEY = 0x0312
WM_RBUTTONUP = 0x0205
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_CONTEXTMENU = 0x007B
WM_NULL = 0x0000
NIN_SELECT = 0x0400
NIN_KEYSELECT = 0x0401
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIM_SETVERSION = 0x00000004

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010

NIIF_INFO = 0x00000001
NIIF_WARNING = 0x00000002
NIIF_ERROR = 0x00000003

NOTIFYICON_VERSION_3 = 3

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
MF_POPUP = 0x00000010

TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

WH_KEYBOARD_LL = 13

VK_MENU = 0x12
VK_LMENU = 0xA4
VK_RMENU = 0xA5
ALT_VKS = (VK_MENU, VK_LMENU, VK_RMENU)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_SET_QUOTA = 0x0100

TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_QUERY = 0x0008
SE_PRIVILEGE_ENABLED = 0x00000002

SystemMemoryListInformation = 0x50
MemoryEmptyWorkingSets = 2
MemoryFlushModifiedList = 3
MemoryPurgeStandbyList = 4

ERROR_ALREADY_EXISTS = 183
ERROR_NOT_ALL_ASSIGNED = 1300
MB_ICONINFORMATION = 0x00000040
MB_ICONWARNING = 0x00000030

# 菜单命令 ID
CMD_CLEAN = 1001
CMD_AUTO_TOGGLE = 1002
CMD_LEVEL_NORMAL = 1003
CMD_LEVEL_DEEP = 1004
CMD_DETAIL = 1005
CMD_AUTOSTART = 1006
CMD_ABOUT = 1007
CMD_EXIT = 1008
CMD_NOTIFY_OFF = 1009
CMD_NOTIFY_SELF = 1010
CMD_NOTIFY_ALL = 1011
NOTIFY_MODE_TEXT = {"off": "不处理", "self": "只清本程序的提示", "all": "清空整个通知中心"}
HOTKEY_ID_FALLBACK = 1

# ---------------------------------------------------------------- win32 类型
ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t
BYTE = ctypes.c_ubyte


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
                ("uFlags", wt.UINT), ("uCallbackMessage", wt.UINT), ("hIcon", wt.HICON),
                ("szTip", wt.WCHAR * 128), ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD),
                ("szInfo", wt.WCHAR * 256), ("uVersion", wt.UINT), ("szInfoTitle", wt.WCHAR * 64),
                ("dwInfoFlags", wt.DWORD), ("guidItem", GUID), ("hBalloonIcon", wt.HICON)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
                ("guidItem", ctypes.c_ubyte * 16)]


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wt.DWORD), ("HighPart", wt.LONG)]


class LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", LUID), ("Attributes", wt.DWORD)]


class TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [("PrivilegeCount", wt.DWORD), ("Privileges", LUID_AND_ATTRIBUTES * 1)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wt.BOOL), ("xHotspot", wt.DWORD), ("yHotspot", wt.DWORD),
                ("hbmMask", wt.HBITMAP), ("hbmColor", wt.HBITMAP)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", ctypes.c_void_p), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wt.HWND), ("message", wt.UINT), ("wParam", wt.WPARAM),
                ("lParam", wt.LPARAM), ("time", wt.DWORD), ("pt", wt.POINT)]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

# 函数原型 (64 位下必须显式声明 restype, 否则句柄会被截断成 32 位)
kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MEMORYSTATUSEX)]
kernel32.GlobalMemoryStatusEx.restype = wt.BOOL
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL
kernel32.GetCurrentProcess.restype = wt.HANDLE
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
kernel32.CreateMutexW.restype = wt.HANDLE
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HMODULE
kernel32.SetProcessWorkingSetSizeEx.argtypes = [wt.HANDLE, ctypes.c_size_t, ctypes.c_size_t,
                                                wt.DWORD]
kernel32.SetProcessWorkingSetSizeEx.restype = wt.BOOL
try:
    kernel32.K32EmptyWorkingSet.argtypes = [wt.HANDLE]
    kernel32.K32EmptyWorkingSet.restype = wt.BOOL
except AttributeError:
    pass

advapi32.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
advapi32.OpenProcessToken.restype = wt.BOOL
advapi32.LookupPrivilegeValueW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, ctypes.POINTER(LUID)]
advapi32.LookupPrivilegeValueW.restype = wt.BOOL
advapi32.AdjustTokenPrivileges.argtypes = [wt.HANDLE, wt.BOOL, ctypes.POINTER(TOKEN_PRIVILEGES),
                                           wt.DWORD, ctypes.c_void_p, ctypes.c_void_p]
advapi32.AdjustTokenPrivileges.restype = wt.BOOL

user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wt.ATOM
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU,
                                   wt.HINSTANCE, ctypes.c_void_p]
user32.CreateWindowExW.restype = wt.HWND
user32.DestroyWindow.argtypes = [wt.HWND]
user32.DestroyWindow.restype = wt.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wt.HWND, wt.UINT, wt.UINT]
user32.GetMessageW.restype = wt.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostMessageW.restype = wt.BOOL
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.SetTimer.argtypes = [wt.HWND, ULONG_PTR, wt.UINT, ctypes.c_void_p]
user32.SetTimer.restype = ULONG_PTR
user32.KillTimer.argtypes = [wt.HWND, ULONG_PTR]
user32.KillTimer.restype = wt.BOOL
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
user32.UnhookWindowsHookEx.restype = wt.BOOL
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.CreatePopupMenu.restype = wt.HMENU
user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ULONG_PTR, wt.LPCWSTR]
user32.AppendMenuW.restype = wt.BOOL
user32.DestroyMenu.argtypes = [wt.HMENU]
user32.DestroyMenu.restype = wt.BOOL
user32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wt.HWND, ctypes.c_void_p]
user32.TrackPopupMenu.restype = wt.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.GetCursorPos.restype = wt.BOOL
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.SetForegroundWindow.restype = wt.BOOL
user32.DestroyIcon.argtypes = [wt.HICON]
user32.DestroyIcon.restype = wt.BOOL
user32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
user32.CreateIconIndirect.restype = wt.HICON
user32.RegisterWindowMessageW.argtypes = [wt.LPCWSTR]
user32.RegisterWindowMessageW.restype = wt.UINT
user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
user32.RegisterHotKey.restype = wt.BOOL
user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wt.BOOL
user32.MessageBoxW.argtypes = [wt.HWND, wt.LPCWSTR, wt.LPCWSTR, wt.UINT]
user32.MessageBoxW.restype = ctypes.c_int
try:
    shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [wt.LPCWSTR]
    shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
except AttributeError:
    pass
try:
    user32.GetDpiForSystem.restype = wt.UINT
except AttributeError:
    pass

gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.DeleteDC.restype = wt.BOOL
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.POINTER(BITMAPINFO), wt.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, wt.UINT, wt.UINT, ctypes.c_void_p]
gdi32.CreateBitmap.restype = wt.HBITMAP
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteObject.restype = wt.BOOL

shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wt.BOOL
try:
    shell32.Shell_NotifyIconGetRect.argtypes = [ctypes.POINTER(NOTIFYICONIDENTIFIER),
                                                ctypes.POINTER(wt.RECT)]
    shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long
except AttributeError:
    shell32.Shell_NotifyIconGetRect = None


def probe_icon_rect(hwnd, uid=1):
    """查询托盘图标位置。返回 (hr, rect)。hr==0 表示在可见通知区, 1(S_FALSE) 表示在隐藏区。"""
    if not shell32.Shell_NotifyIconGetRect or not hwnd:
        return None, None
    nid = NOTIFYICONIDENTIFIER()
    nid.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
    nid.hWnd = hwnd
    nid.uID = uid
    rect = wt.RECT()
    hr = shell32.Shell_NotifyIconGetRect(ctypes.byref(nid), ctypes.byref(rect))
    return hr & 0xFFFFFFFF, (rect.left, rect.top, rect.right, rect.bottom)


def _last_error():
    return ctypes.get_last_error()


# ---------------------------------------------------------------- 内存信息
class MemInfo(object):
    __slots__ = ("total", "avail", "used", "load")

    def __init__(self, total=0, avail=0, used=0, load=0):
        self.total = total
        self.avail = avail
        self.used = used
        self.load = load

    @property
    def total_gb(self):
        return self.total / (1024.0 ** 3)

    @property
    def used_gb(self):
        return self.used / (1024.0 ** 3)

    @property
    def avail_gb(self):
        return self.avail / (1024.0 ** 3)

    def text(self):
        return "%d%%  (已用 %.2f / %.2f GB)" % (self.load, self.used_gb, self.total_gb)


def get_mem_info():
    st = MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
        return MemInfo()
    return MemInfo(st.ullTotalPhys, st.ullAvailPhys,
                   st.ullTotalPhys - st.ullAvailPhys, int(st.dwMemoryLoad))


# ---------------------------------------------------------------- 清理内存
def _enable_privilege(name):
    """尝试启用一个令牌权限(通常需要管理员)。返回是否真的拥有该权限。"""
    token = wt.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(),
                                     TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
                                     ctypes.byref(token)):
        return False
    try:
        luid = LUID()
        if not advapi32.LookupPrivilegeValueW(None, name, ctypes.byref(luid)):
            return False
        tp = TOKEN_PRIVILEGES()
        tp.PrivilegeCount = 1
        tp.Privileges[0].Luid = luid
        tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
        ctypes.set_last_error(0)
        if not advapi32.AdjustTokenPrivileges(token, False, ctypes.byref(tp), 0, None, None):
            return False
        return _last_error() != ERROR_NOT_ALL_ASSIGNED
    finally:
        kernel32.CloseHandle(token)


def is_admin():
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


def _nt_set_memory_list(command):
    """NtSetSystemInformation(SystemMemoryListInformation, command) 系统级清理。"""
    try:
        ntdll = ctypes.WinDLL("ntdll")
    except OSError:
        return False
    try:
        ntdll.NtSetSystemInformation.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]
        ntdll.NtSetSystemInformation.restype = ctypes.c_long
        cmd = ctypes.c_int(command)
        status = ntdll.NtSetSystemInformation(SystemMemoryListInformation,
                                              ctypes.byref(cmd), ctypes.sizeof(cmd))
        return status == 0
    except Exception:
        return False


def _empty_working_set(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, False, pid)
    if not h:
        return False
    try:
        try:
            return bool(kernel32.K32EmptyWorkingSet(h))
        except AttributeError:
            psapi = ctypes.WinDLL("psapi")
            psapi.EmptyWorkingSet.argtypes = [wt.HANDLE]
            psapi.EmptyWorkingSet.restype = wt.BOOL
            return bool(psapi.EmptyWorkingSet(h))
    except Exception:
        return False
    finally:
        kernel32.CloseHandle(h)


def _iter_pids():
    try:
        import psutil
        return sorted(p.pid for p in psutil.process_iter(["pid"]))
    except Exception:
        pass
    try:
        psapi = ctypes.WinDLL("psapi")
        psapi.EnumProcesses.argtypes = [ctypes.POINTER(wt.DWORD), wt.DWORD,
                                        ctypes.POINTER(wt.DWORD)]
        psapi.EnumProcesses.restype = wt.BOOL
        buf = (wt.DWORD * 4096)()
        needed = wt.DWORD()
        if not psapi.EnumProcesses(buf, ctypes.sizeof(buf), ctypes.byref(needed)):
            return []
        n = needed.value // ctypes.sizeof(wt.DWORD)
        return [buf[i] for i in range(min(n, len(buf))) if buf[i]]
    except Exception:
        return []


def clean_memory(level="normal", on_progress=None):
    """清理内存。

    level='normal': 逐个清空进程工作集 (EmptyWorkingSet)
    level='deep'  : 额外调用 NtSetSystemInformation 清空系统工作集/待机列表(需管理员)

    返回 {'before','after','freed','processes','deep_ok','admin','seconds'}
    """
    t0 = time.time()
    before = get_mem_info()
    if on_progress:
        on_progress("正在清理进程工作集…")

    done = 0
    for pid in _iter_pids():
        try:
            if _empty_working_set(pid):
                done += 1
        except Exception:
            continue

    try:
        kernel32.SetProcessWorkingSetSizeEx(kernel32.GetCurrentProcess(),
                                            ctypes.c_size_t(-1).value & 0xFFFFFFFFFFFFFFFF,
                                            ctypes.c_size_t(-1).value & 0xFFFFFFFFFFFFFFFF, 0)
    except Exception:
        pass

    deep_ok = None
    if level == "deep":
        if on_progress:
            on_progress("正在执行系统级深度清理…")
        _enable_privilege("SeProfileSingleProcessPrivilege")
        _enable_privilege("SeIncreaseQuotaPrivilege")
        results = []
        for cmd in (MemoryEmptyWorkingSets, MemoryFlushModifiedList, MemoryPurgeStandbyList):
            results.append(_nt_set_memory_list(cmd))
        deep_ok = any(results)

    time.sleep(0.35)                      # 等系统统计刷新
    after = get_mem_info()
    return {
        "before": before,
        "after": after,
        "freed": after.avail - before.avail,
        "processes": done,
        "deep_ok": deep_ok,
        "admin": is_admin(),
        "seconds": time.time() - t0,
    }


def effective_level(settings_level, manual):
    """决定本次清理用哪一档强度。

    深度清理会清空系统待机列表(文件缓存), 定时反复执行反而拖慢系统,
    所以: 自动清理永远只用"常规", 深度只允许手动触发(双击 Alt / 菜单)。
    """
    if manual and settings_level == "deep":
        return "deep"
    return "normal"


def format_result(res):
    before, after = res["before"], res["after"]
    freed = res["freed"]
    head = ("已释放约 %.0f MB" % (freed / 1024.0 / 1024.0)) if freed > 0 \
        else "清理完成(当前内存状态良好)"
    body = "\n内存占用: %d%% → %d%%   可用 %.2f → %.2f GB\n已处理进程 %d 个, 耗时 %.1f 秒" % (
        before.load, after.load, before.avail_gb, after.avail_gb,
        res["processes"], res["seconds"])
    if res.get("deep_ok") is False and not res.get("admin"):
        body += "\n(深度清理需要以管理员身份运行才能生效)"
    return head, body


# ---------------------------------------------------------------- 双击 Alt 检测
class DoubleAltDetector(object):
    """0.45 秒内连按两次 Alt 返回 True。

    * 按住不放产生的自动重复不会误触发
    * Alt 期间按了其它键 (Alt+Tab / Alt+F4 等) 则本次计时作废
    * 左右 Alt 混合连按也算
    """

    def __init__(self, interval=0.45, now=None):
        self.interval = interval
        self._now = now or time.monotonic
        self._pressed = set()
        self._taps = []

    def reset(self):
        self._pressed.clear()
        del self._taps[:]

    def feed(self, vk, is_down):
        if vk in ALT_VKS:
            if is_down:
                if vk in self._pressed:         # 自动重复
                    return False
                self._pressed.add(vk)
                now = self._now()
                self._taps = [t for t in self._taps if now - t <= self.interval]
                self._taps.append(now)
                if len(self._taps) >= 2:
                    del self._taps[:]
                    return True
            else:
                self._pressed.discard(vk)
        elif is_down and self._pressed:
            del self._taps[:]                    # Alt 被当成组合键, 作废
        return False


# ---------------------------------------------------------------- 图标绘制
def _load_font(size):
    from PIL import ImageFont
    names = ["arialbd.ttf", "seguisb.ttf", "msyhbd.ttc", "simhei.ttf",
             os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arialbd.ttf")]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def usage_color(load):
    if load >= 85:
        return (214, 48, 40)      # 红: 内存紧张
    if load >= 65:
        return (232, 145, 20)     # 橙: 偏高
    return (34, 158, 74)          # 绿: 正常


def render_icon(load, size=16):
    """绘制 size×size 的 RGBA 图标: 圆角底色 + 内存占用数字。"""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(0, int(round(size * 0.04)))
    radius = max(2, int(round(size * 0.26)))
    base = usage_color(load)
    d.rounded_rectangle([pad, pad, size - 1 - pad, size - 1 - pad], radius=radius,
                        fill=base + (255,))
    if size >= 24:                                     # 顶部一点点高光(直接算混色,避免盖住数字)
        hi = tuple(int(c + (255 - c) * 0.22) for c in base)
        d.rounded_rectangle([pad + 1, pad + 1, size - 2 - pad, int(size * 0.45)],
                            radius=max(2, radius - 1), fill=hi + (255,))
    text = "%d" % min(99, max(0, int(load)))
    font = _load_font(max(6, int(round(size * (0.68 if len(text) < 3 else 0.54)))))
    try:
        box = d.textbbox((0, 0), text, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        d.text(((size - tw) / 2.0 - box[0], (size - th) / 2.0 - box[1]), text,
               font=font, fill=(255, 255, 255, 255))
    except Exception:
        d.text((size * 0.18, size * 0.18), text, font=font, fill=(255, 255, 255, 255))
    return img


def pil_to_hicon(img):
    """PIL RGBA 图 -> HICON (返回的句柄需要 DestroyIcon 释放)。"""
    img = img.convert("RGBA")
    w, h = img.size
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h            # 负数 = 自上而下
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0        # BI_RGB

    hdc = gdi32.CreateCompatibleDC(None)
    bits = ctypes.c_void_p()
    hbm_color = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    hbm_mask = gdi32.CreateBitmap(w, h, 1, 1, None)
    try:
        if not hbm_color or not bits.value:
            raise OSError("CreateDIBSection 失败")
        data = img.tobytes("raw", "BGRA")
        ctypes.memmove(bits, data, len(data))
        ii = ICONINFO()
        ii.fIcon = True
        ii.hbmMask = hbm_mask
        ii.hbmColor = hbm_color
        hicon = user32.CreateIconIndirect(ctypes.byref(ii))
        if not hicon:
            raise OSError("CreateIconIndirect 失败")
        return hicon
    finally:
        if hbm_color:
            gdi32.DeleteObject(hbm_color)
        if hbm_mask:
            gdi32.DeleteObject(hbm_mask)
        if hdc:
            gdi32.DeleteDC(hdc)


def icon_pixel_size():
    env = os.environ.get("MEMCLEAN_ICON_SIZE")
    if env and env.isdigit():
        return max(16, min(128, int(env)))
    try:
        dpi = user32.GetDpiForSystem()
    except Exception:
        dpi = 96
    return max(16, min(64, int(round(16 * (dpi or 96) / 96.0))))


# ---------------------------------------------------------------- 配置
DEFAULT_SETTINGS = {
    "auto_enabled": True,        # 自动清理
    "auto_interval_min": 30,     # 自动清理间隔(分钟)
    "auto_min_load": 70,         # 自动清理触发阈值(内存占用 %)
    "level": "normal",           # normal 常规 | deep 深度 (深度只对"手动"清理生效)
    "balloon_on_manual": True,   # 手动清理后弹气泡
    "hotkey_double_alt": True,   # 双击 Alt 热键
    "autostart": False,
    "clear_notify": "self",      # 清理内存后如何处理系统消息: off | self | all
    "notify_aumid": "",          # 自动识别到的"本程序通知"的 AppUserModelID
}


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                s.update(data)
    except Exception:
        pass
    return s


def save_settings(s):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _run_key():
    return r"Software\Microsoft\Windows\CurrentVersion\Run"


def _run_command():
    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(exe):
        exe = sys.executable
    return '"%s" "%s"' % (exe, os.path.abspath(__file__))


def get_autostart():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _run_key()) as k:
            val, _ = winreg.QueryValueEx(k, APP_ID)
            return bool(val)
    except OSError:
        return False


def set_autostart(enable):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _run_key()) as k:
        if enable:
            winreg.SetValueEx(k, APP_ID, 0, winreg.REG_SZ, _run_command())
        else:
            try:
                winreg.DeleteValue(k, APP_ID)
            except OSError:
                pass
    return get_autostart()


# ---------------------------------------------------------------- 系统通知(消息)清理
# Windows 只提供了 WinRT 的 ToastNotificationManager.History.Clear(appUserModelId)
# 来删除"通知中心"里的记录。Python 侧没有现成的 WinRT 绑定, 直接 ctypes 调 vtable
# 在这个系统上拿不到 History 接口(实测 vtable 布局与 winmd 元数据对不上), 所以这里
# 借 Windows PowerShell 自带的 WinRT 投影来完成 —— 启动约 2 秒, 放在后台线程里跑,
# 不阻塞托盘和气泡。
NOTIFY_SETTINGS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"
EXPLORER_NOTIFY_PREFIX = "Microsoft.Explorer.Notification."
_CREATE_NO_WINDOW = 0x08000000

_PS_PREAMBLE = (
    "[void][Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,"
    "ContentType=WindowsRuntime];"
    "$h=[Windows.UI.Notifications.ToastNotificationManager]::History;"
)


def _ps_quote(text):
    return "'%s'" % str(text).replace("'", "''")


def _ps_clear_script(mode, aumid=None):
    """生成清理用的 PowerShell 脚本; 最后一行输出被清掉的消息条数。"""
    if mode == "self":
        a = _ps_quote(aumid)
        return _PS_PREAMBLE + (
            "$c=0;try{$c=@($h.GetHistory(%s)).Count;$h.Clear(%s)}catch{};Write-Output $c" % (a, a))
    root_hkcu = _ps_quote("HKCU:\\" + NOTIFY_SETTINGS_KEY)
    root_hklm = _ps_quote("HKLM:\\" + NOTIFY_SETTINGS_KEY)
    return _PS_PREAMBLE + (
        "$ids=@();foreach($r in @(%s,%s)){" % (root_hkcu, root_hklm) +
        "Get-ChildItem $r -ErrorAction SilentlyContinue|ForEach-Object{$ids+=$_.PSChildName}};"
        "$ids=$ids|Sort-Object -Unique;$t=0;foreach($i in $ids){"
        "try{$c=@($h.GetHistory($i)).Count;if($c -gt 0){$h.Clear($i);$t+=$c}}catch{}};"
        "Write-Output $t")


def clear_system_notifications(mode, aumid=None, timeout=120):
    """清理系统消息。mode='self' 只清 aumid 这个应用, mode='all' 清空整个通知中心。

    返回 (清掉的消息条数, 错误信息)。
    """
    import subprocess
    if mode == "self" and not aumid:
        return 0, None
    script = _ps_clear_script(mode, aumid)
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
           "-WindowStyle", "Hidden", "-Command", script]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout,
                              creationflags=_CREATE_NO_WINDOW)
    except Exception as e:                               # noqa: BLE001
        return 0, "调用 PowerShell 失败: %s" % e
    text = (proc.stdout or b"").decode("utf-8", "ignore").strip().splitlines()
    for line in reversed(text):
        line = line.strip()
        if line.isdigit():
            return int(line), None
    err = (proc.stderr or b"").decode("utf-8", "ignore").strip()
    return 0, (err.splitlines()[-1] if err else "PowerShell 没有返回结果")


def enumerate_notification_aumids():
    """列出所有登记过通知的应用 ID (仅用于诊断/命令行)。"""
    import winreg
    ids = []
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, NOTIFY_SETTINGS_KEY) as k:
                i = 0
                while True:
                    try:
                        ids.append(winreg.EnumKey(k, i))
                    except OSError:
                        break
                    i += 1
        except OSError:
            continue
    if APP_AUMID not in ids:
        ids.append(APP_AUMID)
    return sorted(set(ids))


def snapshot_explorer_notify_keys():
    """记录传统气泡(traditional balloon)在注册表里的时间戳快照。"""
    import winreg
    snap = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, NOTIFY_SETTINGS_KEY) as k:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                if not name.startswith(EXPLORER_NOTIFY_PREFIX):
                    continue
                try:
                    with winreg.OpenKey(k, name) as sub:
                        t, _ = winreg.QueryValueEx(sub, "LastNotificationAddedTime")
                    snap[name] = int(t)
                except OSError:
                    continue
    except OSError:
        pass
    return snap


def find_own_aumid(before_snapshot=None, max_age_sec=120):
    """找出"本程序刚弹出的气泡"对应的 AppUserModelID。

    Windows 给传统气泡分配的是一串随机的 Microsoft.Explorer.Notification.{GUID},
    只能靠注册表里 LastNotificationAddedTime 的变化来识别(每个发送者一个固定 GUID)。
    """
    after = snapshot_explorer_notify_keys()
    now_ft = int((time.time() + 11644473600) * 10 ** 7)      # FILETIME
    limit = max_age_sec * 10 ** 7
    best, best_t = None, 0
    for name, t in after.items():
        if before_snapshot is not None and before_snapshot.get(name) == t:
            continue                                          # 时间戳没变, 不是刚发的
        if not 0 <= now_ft - t <= limit:
            continue
        if t > best_t:
            best, best_t = name, t
    return best


# ---------------------------------------------------------------- 托盘程序
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class TrayApp(object):
    def __init__(self, settings=None):
        self.settings = settings or load_settings()
        self.hwnd = None
        self.hicon = None
        self.tray_added = False
        self.class_name = "MemCleanTrayWnd_%d" % os.getpid()
        self._wndproc = WNDPROC(self._on_message)      # 必须保留引用, 否则被 GC
        self._hookproc = HOOKPROC(self._on_key)
        self.hook = None
        self.detector = DoubleAltDetector()
        self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self._clean_busy = False
        self._pending = None
        self._last_load = -1
        self._icon_size = icon_pixel_size()
        self._stopping = False
        self._last_auto = time.time()
        self._aumid_snapshot = None
        self._aumid_scan_at = 0

    # ---------------- 托盘图标
    def _nid(self, flags=NIF_MESSAGE | NIF_ICON | NIF_TIP, tip=None):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = flags
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self.hicon
        if tip:
            nid.szTip = tip[:127]
        return nid

    def _push_icon(self, tip):
        nid = self._nid(tip=tip)
        if not self.tray_added:
            if shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
                self.tray_added = True
                nid.uVersion = NOTIFYICON_VERSION_3
                shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(nid))
                hr, rect = probe_icon_rect(self.hwnd)
                where = {0: "可见通知区", 1: "隐藏的溢出区(点任务栏 ^ 可看到)"}.get(hr, "hr=0x%X" % hr)
                log("NIM_ADD 成功 hwnd=0x%X uID=1 -> 图标位置: %s %s" % (self.hwnd, where, rect))
                return True
            log("NIM_ADD 失败 GetLastError=%d" % _last_error())
            return False
        return bool(shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid)))

    def _update_icon(self, force=False):
        info = get_mem_info()
        tip = "%s\n内存占用 %s\n双击 Alt 键立即清理内存" % (APP_NAME, info.text())
        if force or info.load != self._last_load or not self.tray_added:
            new = pil_to_hicon(render_icon(info.load, self._icon_size))
            old, self.hicon = self.hicon, new
            self._push_icon(tip)
            if old:
                user32.DestroyIcon(old)
        else:
            self._push_icon(tip)
        self._last_load = info.load
        return info

    def _balloon(self, title, text, flags=NIIF_INFO):
        nid = self._nid(flags=NIF_INFO | NIF_ICON | NIF_TIP)
        nid.szInfoTitle = (title or "")[:63]
        nid.szInfo = (text or "")[:255]
        nid.dwInfoFlags = flags
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _remove_icon(self):
        if self.tray_added and self.hwnd:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid()))
            self.tray_added = False

    # ---------------- 清理
    def trigger_clean(self, manual=True):
        if self._clean_busy:
            log("清理请求被忽略(上一次还在进行中)")
            return False
        self._clean_busy = True
        level = effective_level(self.settings.get("level", "normal"), manual)
        log("开始清理: 强度=%s 触发=%s" % (level, "手动" if manual else "自动"))

        def work():
            try:
                res, err = clean_memory(level), None
            except Exception as e:                       # noqa: BLE001
                res, err = None, str(e)
            note = None
            try:
                note = self._clear_system_messages()
            except Exception as e:                       # noqa: BLE001
                note = "系统消息清理失败: %s" % e
                log(note)
            self._pending = (res, err, manual, level, note)
            if self.hwnd:
                user32.PostMessageW(self.hwnd, WM_CLEAN_DONE, 0, 0)
            self._clean_busy = False

        threading.Thread(target=work, name="memclean-worker", daemon=True).start()
        return True

    def _clear_system_messages(self):
        """按设置清理系统消息(通知中心)。返回一句可以放进气泡的说明。"""
        mode = self.settings.get("clear_notify", "self")
        if mode == "off":
            return None
        t0 = time.time()
        if mode == "all":
            n, err = clear_system_notifications("all")
            log("清空通知中心: 清掉 %d 条消息, 耗时 %.1fs%s" % (
                n, time.time() - t0, ("  错误: %s" % err) if err else ""))
            if err:
                return "系统消息清理失败: %s" % err
            return ("已清空通知中心里其它应用的 %d 条消息" % n) if n else None
        aumid = self.settings.get("notify_aumid")
        if not aumid:
            log("尚未识别出本程序通知的 AUMID, 跳过系统消息清理")
            return None
        n, err = clear_system_notifications("self", aumid)
        log("清理本程序提示: %s -> %d 条, 耗时 %.1fs%s" % (
            aumid, n, time.time() - t0, ("  错误: %s" % err) if err else ""))
        if err:
            return "系统消息清理失败: %s" % err
        return ("已清掉本程序上次的 %d 条提示" % n) if n else None

    # ---------------- 识别本程序通知的 AppUserModelID
    def _arm_aumid_scan(self):
        """在弹气泡之前快照注册表, 2.5 秒后对比找出我们自己的通知 AUMID。"""
        if self.settings.get("clear_notify", "self") != "self":
            return
        if self.settings.get("notify_aumid"):
            return
        self._aumid_snapshot = snapshot_explorer_notify_keys()
        self._aumid_scan_at = time.time() + 2.5

    def _scan_aumid(self):
        if not self._aumid_scan_at or time.time() < self._aumid_scan_at:
            return
        self._aumid_scan_at = 0
        aumid = find_own_aumid(self._aumid_snapshot)
        if aumid:
            self.settings["notify_aumid"] = aumid
            save_settings(self.settings)
            log("已识别本程序通知的 AUMID: %s" % aumid)

    def _on_clean_done(self):
        pending, self._pending = self._pending, None
        if not pending:
            return
        res, err, manual, level, note = pending
        self._update_icon(force=True)
        if res is None:
            log("清理异常: %s" % err)
            self._balloon(APP_NAME, "清理失败: %s" % err, NIIF_ERROR)
            return
        head, body = format_result(res)
        log("清理完成: %s | 内存 %d%% -> %d%% | 可用 %.2f -> %.2f GB | 进程 %d | %.1fs" % (
            head, res["before"].load, res["after"].load, res["before"].avail_gb,
            res["after"].avail_gb, res["processes"], res["seconds"]))
        if note:
            body += "\n" + note
        if manual and self.settings.get("balloon_on_manual", True):
            self._arm_aumid_scan()
            self._balloon("%s · %s清理" % (head, "深度" if level == "deep" else "常规"),
                          body, NIIF_INFO)

    # ---------------- 右键菜单
    def _show_menu(self):
        s = self.settings
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        cmd = 0
        try:
            auto_txt = "自动清理: %s" % ("开" if s.get("auto_enabled") else "关")
            if s.get("auto_enabled"):
                auto_txt += "  (每 %d 分钟, ≥%d%%)" % (int(s.get("auto_interval_min", 30)),
                                                       int(s.get("auto_min_load", 70)))
            deep = s.get("level") == "deep"
            user32.AppendMenuW(menu, MF_STRING, CMD_CLEAN, "立即清理内存  (双击 Alt)")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if s.get("auto_enabled") else 0),
                               CMD_AUTO_TOGGLE, auto_txt)
            user32.AppendMenuW(menu, MF_STRING | (0 if deep else MF_CHECKED),
                               CMD_LEVEL_NORMAL, "清理强度: 常规")
            user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if deep else 0),
                               CMD_LEVEL_DEEP, "清理强度: 深度 (手动清理时用, 需管理员)")
            mode = s.get("clear_notify", "self")
            sub = user32.CreatePopupMenu()
            user32.AppendMenuW(sub, MF_STRING | (MF_CHECKED if mode == "off" else 0),
                               CMD_NOTIFY_OFF, "不处理系统消息")
            user32.AppendMenuW(sub, MF_STRING | (MF_CHECKED if mode == "self" else 0),
                               CMD_NOTIFY_SELF, "只清本程序的提示")
            user32.AppendMenuW(sub, MF_STRING | (MF_CHECKED if mode == "all" else 0),
                               CMD_NOTIFY_ALL, "清空整个通知中心")
            user32.AppendMenuW(menu, MF_POPUP | MF_STRING, sub,
                               "清理后系统消息: %s" % NOTIFY_MODE_TEXT.get(mode, "不处理"))
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, CMD_DETAIL, "查看内存详情…")
            user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if s.get("autostart") else 0),
                               CMD_AUTOSTART, "开机自动启动")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, CMD_ABOUT, "关于 / 使用说明")
            user32.AppendMenuW(menu, MF_STRING, CMD_EXIT, "退出")

            pt = wt.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(self.hwnd)
            cmd = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                                        pt.x, pt.y, 0, self.hwnd, None)
            user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        finally:
            user32.DestroyMenu(menu)
        if cmd:
            self._on_command(int(cmd))

    def _on_command(self, cmd):
        s = self.settings
        if cmd == CMD_CLEAN:
            self.trigger_clean(manual=True)
        elif cmd == CMD_AUTO_TOGGLE:
            s["auto_enabled"] = not s.get("auto_enabled", True)
            save_settings(s)
            self._balloon(APP_NAME, "自动清理已%s。\n(每 %d 分钟检查一次, 内存占用 ≥ %d%% 时用“常规”清理)" % (
                "开启" if s["auto_enabled"] else "关闭", int(s.get("auto_interval_min", 30)),
                int(s.get("auto_min_load", 70))))
        elif cmd == CMD_LEVEL_NORMAL:
            s["level"] = "normal"
            save_settings(s)
            self._balloon(APP_NAME, "已切换为“常规”清理: 清空各进程工作集, 安全无副作用。")
        elif cmd == CMD_LEVEL_DEEP:
            s["level"] = "deep"
            save_settings(s)
            tip = ("已切换为“深度”清理: 清空系统工作集并清空待机内存(文件缓存)。\n"
                   "为避免定时清空缓存拖慢系统, 自动清理仍只使用“常规”, "
                   "深度只在双击 Alt / 菜单手动清理时生效。")
            if is_admin():
                self._balloon(APP_NAME, tip)
            else:
                self._balloon(APP_NAME, tip + "\n注意: 当前不是管理员, 手动清理时深度部分不会生效。",
                              NIIF_WARNING)
        elif cmd in (CMD_NOTIFY_OFF, CMD_NOTIFY_SELF, CMD_NOTIFY_ALL):
            mode = {CMD_NOTIFY_OFF: "off", CMD_NOTIFY_SELF: "self",
                    CMD_NOTIFY_ALL: "all"}[cmd]
            s["clear_notify"] = mode
            if mode == "self" and not s.get("notify_aumid"):
                got = find_own_aumid(None, max_age_sec=300)
                if got:
                    s["notify_aumid"] = got
            save_settings(s)
            if mode == "off":
                self._balloon(APP_NAME, "清理内存后不再处理系统消息。")
            elif mode == "self":
                extra = "" if s.get("notify_aumid") else "\n(还没认准本程序的提示, 下次清理时会自动识别)"
                self._balloon(APP_NAME, "清理内存后会自动清掉本程序自己弹出的提示,\n"
                                        "不让它堆在通知中心里。" + extra)
            else:
                self._balloon(APP_NAME, "清理内存后会清空整个通知中心 ——\n"
                                        "其它应用(微信/QQ/系统等)未读的通知也会一起清掉。\n"
                                        "本次清理结果的提示会在清空之后弹出, 所以会保留。", NIIF_WARNING)
        elif cmd == CMD_DETAIL:
            info = get_mem_info()
            self._balloon(APP_NAME, "当前内存占用 %s\n物理内存共 %.2f GB, 可用 %.2f GB。\n"
                                    "托盘图标数字 = 内存占用百分比。" % (
                                        info.text(), info.total_gb, info.avail_gb))
        elif cmd == CMD_AUTOSTART:
            try:
                s["autostart"] = set_autostart(not s.get("autostart"))
                save_settings(s)
                self._balloon(APP_NAME, "开机自启动已%s。" % ("开启" if s["autostart"] else "关闭"))
            except Exception as e:                        # noqa: BLE001
                self._balloon(APP_NAME, "设置开机自启失败: %s" % e, NIIF_ERROR)
        elif cmd == CMD_ABOUT:
            user32.MessageBoxW(None, (
                "%s v%s\n\n"
                "· 双击 Alt 键 (0.45 秒内连按两下) 立即清理内存\n"
                "· 左键双击托盘图标 = 立即清理\n"
                "· 右键托盘图标 = 打开本菜单\n"
                "· Ctrl+Alt+M 也可以触发清理\n"
                "· 托盘图标上的数字 = 当前内存占用百分比\n"
                "     绿 < 65%% ≤ 橙 < 85%% ≤ 红\n"
                "· 清理强度分“常规”和“深度”, 深度需管理员身份运行\n"
                "     深度只在你手动清理(双击 Alt / 菜单)时生效,\n"
                "     自动清理永远只用常规, 避免定时清空文件缓存拖慢系统\n"
                "· “清理后系统消息”可选: 不处理 / 只清本程序的提示 /\n"
                "     清空整个通知中心(含其它应用的通知)\n\n"
                "配置文件: %s" % (APP_NAME, APP_VERSION, SETTINGS_PATH)
            ), APP_NAME, MB_ICONINFORMATION)
        elif cmd == CMD_EXIT:
            self.quit()

    # ---------------- 消息处理
    def _on_key(self, ncode, wparam, lparam):
        try:
            if ncode == 0 and self.settings.get("hotkey_double_alt", True):
                kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    if self.detector.feed(kb.vkCode, True):
                        log("双击 Alt 命中 -> 开始清理")
                        self.trigger_clean(manual=True)
                elif wparam in (WM_KEYUP, WM_SYSKEYUP):
                    self.detector.feed(kb.vkCode, False)
        except Exception:
            pass
        return user32.CallNextHookEx(None, ncode, wparam, lparam)

    def _on_message(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAYICON:
                if lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._show_menu()
                elif lparam == WM_LBUTTONDBLCLK:
                    self.trigger_clean(manual=True)
                return 0
            if msg == WM_CLEAN_DONE:
                self._on_clean_done()
                return 0
            if msg == WM_TIMER:
                if wparam == 1:
                    self._update_icon()
                    self._maybe_auto_clean()
                    self._scan_aumid()
                return 0
            if msg == WM_HOTKEY:
                self.trigger_clean(manual=True)
                return 0
            if msg == WM_CLOSE:
                self._remove_icon()
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            if self.taskbar_created and msg == self.taskbar_created:
                self.tray_added = False            # 资源管理器重启后重新加图标
                self._push_icon("%s\n内存占用 %s" % (APP_NAME, get_mem_info().text()))
                return 0
        except Exception:
            pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _maybe_auto_clean(self):
        s = self.settings
        if not s.get("auto_enabled") or self._clean_busy:
            return
        if time.time() - self._last_auto < max(60, int(s.get("auto_interval_min", 30)) * 60):
            return
        self._last_auto = time.time()
        if self._last_load < int(s.get("auto_min_load", 70)):
            return
        self.trigger_clean(manual=False)

    # ---------------- 启动 / 退出
    def _create_window(self):
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p)
        wc.hInstance = hinst
        wc.lpszClassName = self.class_name
        if not user32.RegisterClassW(ctypes.byref(wc)):
            err = _last_error()
            if err not in (0, 1410):              # 1410 = 类已存在
                raise OSError("RegisterClassW 失败: %d" % err)
        self.hwnd = user32.CreateWindowExW(0, self.class_name, APP_NAME, 0, 0, 0, 0, 0,
                                           None, None, hinst, None)
        if not self.hwnd:
            raise OSError("CreateWindowExW 失败: %d" % _last_error())

    def _install_hook(self):
        if not self.settings.get("hotkey_double_alt", True):
            return
        self.hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hookproc, None, 0)
        if not self.hook:
            # 键盘钩子失败时退回注册一个常规热键 Ctrl+Alt+M
            user32.RegisterHotKey(self.hwnd, HOTKEY_ID_FALLBACK,
                                  MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("M"))

    def run(self):
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
        # 让本进程的气泡/通知归属于一个固定的 AppUserModelID,
        # 否则 Windows 会给传统气泡分配随机的 Microsoft.Explorer.Notification.{GUID},
        # 之后就没法只清理"我们自己的"通知了。
        try:
            shell32.SetCurrentProcessExplicitAppUserModelID(APP_AUMID)
        except Exception:
            pass
        self._create_window()
        self._install_hook()
        log("启动 pid=%d 图标尺寸=%dpx 键盘钩子=%s 管理员=%s 单实例窗口=0x%X" % (
            os.getpid(), self._icon_size, "已安装" if self.hook else "失败", is_admin(), self.hwnd))
        if not self.hook:
            log("键盘钩子安装失败 GetLastError=%d, 改用 Ctrl+Alt+M 热键" % _last_error())
        self._update_icon(force=True)
        user32.SetTimer(self.hwnd, 1, 2000, None)
        tip = "已在托盘运行: 双击 Alt 键即可清理内存。"
        if not os.path.exists(SETTINGS_PATH):
            tip += "\n若任务栏上找不到本图标, 点任务栏的 ^ 展开, 把它拖到可见区域即可。"
        self._arm_aumid_scan()
        self._balloon(APP_NAME, tip)
        msg = MSG()
        while True:
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r in (0, -1):
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        self.shutdown()

    def quit(self):
        if self._stopping:
            return
        self._stopping = True
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def shutdown(self):
        try:
            if self.hwnd:
                user32.KillTimer(self.hwnd, 1)
            if self.hook:
                user32.UnhookWindowsHookEx(self.hook)
                self.hook = None
            if self.hwnd:
                user32.UnregisterHotKey(self.hwnd, HOTKEY_ID_FALLBACK)
            self._remove_icon()
            if self.hicon:
                user32.DestroyIcon(self.hicon)
                self.hicon = None
        except Exception:
            pass


# ---------------------------------------------------------------- 命令行
def _check(label, actual, expected):
    ok = "√" if actual == expected else "×"
    print("   [%s] %-26s 实际=%s 期望=%s" % (ok, label, actual, expected))
    return actual == expected


def cmd_selftest():
    fails = 0
    print("== 1. 内存信息 ==")
    info = get_mem_info()
    print("   " + info.text())
    fails += 0 if info.total > 0 else 1

    print("== 2. 双击 Alt 检测逻辑 ==")
    clock = [1000.0]
    det = DoubleAltDetector(interval=0.45, now=lambda: clock[0])
    clock[0] = 1000.0
    r = det.feed(VK_LMENU, True)
    clock[0] += 0.05
    r = det.feed(VK_LMENU, False) or r
    fails += 0 if _check("单击一次 Alt", r, False) else 1

    det = DoubleAltDetector(interval=0.45, now=lambda: clock[0])
    clock[0] = 2000.0
    r1 = det.feed(VK_LMENU, True)
    clock[0] += 0.05
    det.feed(VK_LMENU, False)
    clock[0] += 0.10
    r2 = det.feed(VK_LMENU, True)
    fails += 0 if _check("0.15 秒内连按两下", (r1, r2), (False, True)) else 1

    det = DoubleAltDetector(interval=0.45, now=lambda: clock[0])
    clock[0] = 3000.0
    det.feed(VK_LMENU, True)
    clock[0] += 0.02
    r = det.feed(VK_LMENU, True)                 # 自动重复
    fails += 0 if _check("按住不放(自动重复)", r, False) else 1

    det = DoubleAltDetector(interval=0.45, now=lambda: clock[0])
    clock[0] = 4000.0
    det.feed(VK_LMENU, True)
    clock[0] += 0.05
    det.feed(0x09, True)                         # Alt+Tab
    clock[0] += 0.05
    det.feed(0x09, False)
    det.feed(VK_LMENU, False)
    clock[0] += 0.05
    r = det.feed(VK_LMENU, True)
    fails += 0 if _check("Alt+Tab 之后按 Alt", r, False) else 1

    det = DoubleAltDetector(interval=0.45, now=lambda: clock[0])
    clock[0] = 5000.0
    det.feed(VK_LMENU, True)
    clock[0] += 0.10
    det.feed(VK_LMENU, False)
    clock[0] += 1.00
    r = det.feed(VK_LMENU, True)
    fails += 0 if _check("两次间隔 1 秒", r, False) else 1

    det = DoubleAltDetector(interval=0.45, now=lambda: clock[0])
    clock[0] = 6000.0
    det.feed(VK_LMENU, True)
    clock[0] += 0.05
    det.feed(VK_LMENU, False)
    clock[0] += 0.10
    r = det.feed(VK_RMENU, True)                 # 左 Alt + 右 Alt
    fails += 0 if _check("左右 Alt 混合", r, True) else 1

    print("== 3. 清理强度选择 ==")
    fails += 0 if _check("设置=深度 + 手动", effective_level("deep", True), "deep") else 1
    fails += 0 if _check("设置=深度 + 自动", effective_level("deep", False), "normal") else 1
    fails += 0 if _check("设置=常规 + 手动", effective_level("normal", True), "normal") else 1
    fails += 0 if _check("设置=常规 + 自动", effective_level("normal", False), "normal") else 1

    print("== 4. 图标渲染 / HICON ==")
    for size in (16, 24, 32, 48):
        try:
            h = pil_to_hicon(render_icon(42, size))
            ok = bool(h)
            if h:
                user32.DestroyIcon(h)
        except Exception as e:                    # noqa: BLE001
            ok, h = False, e
        fails += 0 if _check("%dx%d 生成 HICON" % (size, size), ok, True) else 1

    print("== 5. 清理内存 ==")
    res = clean_memory("normal")
    head, body = format_result(res)
    print("   " + head)
    print("   " + body.replace("\n", "\n   "))
    print("   已处理进程 %d 个, 管理员=%s" % (res["processes"], res["admin"]))
    fails += 0 if res["processes"] > 0 else 1

    print("== 6. 系统消息(通知)清理 ==")
    ids = enumerate_notification_aumids()
    print("   注册表里登记过通知的应用: %d 个" % len(ids))
    fails += 0 if _check("能列出通知应用", len(ids) > 0, True) else 1
    print("   传统气泡发送者注册表项  : %d 个" % len(snapshot_explorer_notify_keys()))
    n, err = clear_system_notifications("self", None)
    fails += 0 if _check("无 AUMID 时跳过", (n, err), (0, None)) else 1
    aumid = find_own_aumid(None, max_age_sec=3600)
    if aumid:
        t0 = time.time()
        n, err = clear_system_notifications("self", aumid)
        dt = time.time() - t0
        print("   清理本程序(%s…): %d 条, 耗时 %.1f 秒%s" % (
            aumid[:28], n, dt, ("  错误: %s" % err) if err else ""))
        fails += 0 if _check("PowerShell 清理调用成功", err, None) else 1
    else:
        print("   本程序还没弹过气泡, 跳过实际清理测试")

    print("== 7. 配置读写 ==")
    import tempfile
    global SETTINGS_PATH
    old = SETTINGS_PATH
    SETTINGS_PATH = os.path.join(tempfile.gettempdir(), "memclean_selftest.json")
    try:
        s = load_settings()
        s["auto_interval_min"] = 42
        save_settings(s)
        fails += 0 if _check("settings.json 往返", load_settings()["auto_interval_min"], 42) else 1
    finally:
        try:
            os.remove(SETTINGS_PATH)
        except OSError:
            pass
        SETTINGS_PATH = old

    print("\n%s" % ("全部通过 [OK]" if fails == 0 else "有 %d 项未通过 [FAIL]" % fails))
    return 0 if fails == 0 else 1


def cmd_icons(out_path):
    from PIL import Image
    sizes = [16, 24, 32, 48]
    loads = [23, 58, 72, 91]
    scale, margin = 6, 48
    cell = max(sizes) * scale
    W = margin + len(loads) * (cell + margin)
    H = margin + len(sizes) * (cell + margin)
    sheet = Image.new("RGB", (W, H), (243, 244, 246))
    for row, size in enumerate(sizes):
        for col, load in enumerate(loads):
            ic = render_icon(load, size)
            ic = ic.resize((size * scale, size * scale), Image.NEAREST)
            x = margin + col * (cell + margin) + (cell - size * scale) // 2
            y = margin + row * (cell + margin) + (cell - size * scale) // 2
            sheet.paste(ic, (x, y), ic)
    sheet.save(out_path)
    print("图标预览已保存: %s" % out_path)
    return 0


def cmd_tree(pid_of_interest=None):
    """打印进程内存排行(辅助排查, --top N)。"""
    try:
        import psutil
    except ImportError:
        print("需要 psutil")
        return 1
    rows = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            rows.append((p.info["memory_info"].rss, p.info["pid"], p.info["name"]))
        except Exception:
            continue
    rows.sort(reverse=True)
    for rss, pid, name in rows[:pid_of_interest or 15]:
        print("%8.1f MB  pid=%-7d %s" % (rss / 1024.0 / 1024.0, pid, name))
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="%s v%s - 托盘内存清理工具" % (APP_NAME, APP_VERSION))
    ap.add_argument("--selftest", action="store_true", help="自检: 内存信息/热键/图标/清理/配置")
    ap.add_argument("--icons", metavar="PNG", help="导出托盘图标预览图并退出")
    ap.add_argument("--clean", action="store_true", help="清理一次内存后退出")
    ap.add_argument("--deep", action="store_true", help="配合 --clean 使用深度清理")
    ap.add_argument("--top", type=int, metavar="N", help="列出内存占用最高的 N 个进程")
    ap.add_argument("--clear-notify", choices=["self", "all"], help="立即清理系统消息(通知中心)后退出")
    ap.add_argument("--notify-info", action="store_true", help="显示通知/AUMID 识别情况后退出")
    ap.add_argument("--autostart", choices=["on", "off", "status"], help="开机自启设置")
    ap.add_argument("--version", action="store_true", help="打印版本")
    args = ap.parse_args(argv)

    if args.version:
        print("%s v%s" % (APP_NAME, APP_VERSION))
        return 0
    if args.selftest:
        return cmd_selftest()
    if args.icons:
        return cmd_icons(args.icons)
    if args.top:
        return cmd_tree(args.top)
    if args.clear_notify:
        if args.clear_notify == "self":
            aumid = find_own_aumid(None, max_age_sec=3600)
            print("识别到的本程序通知 AUMID: %s" % (aumid or "(没找到)"))
            if not aumid:
                return 1
            mode, target = "self", aumid
        else:
            print("通知中心登记过的应用数: %d" % len(enumerate_notification_aumids()))
            mode, target = "all", None
        t0 = time.time()
        n, err = clear_system_notifications(mode, target)
        print("已清掉 %d 条系统消息, 耗时 %.1f 秒%s" % (
            n, time.time() - t0, ("  错误: %s" % err) if err else ""))
        return 0 if not err else 1
    if args.notify_info:
        s = load_settings()
        snap = snapshot_explorer_notify_keys()
        print("设置里缓存的本程序 AUMID : %s" % (s.get("notify_aumid") or "(未识别)"))
        print("通知设置里登记的应用数   : %d" % len(enumerate_notification_aumids()))
        print("传统气泡发送者注册表项数 : %d" % len(snap))
        own = find_own_aumid(None, max_age_sec=3600)
        print("最近 1 小时内最新气泡的   : %s" % (own or "(无)"))
        return 0
    if args.clean:
        res = clean_memory("deep" if args.deep else "normal")
        head, body = format_result(res)
        print(head)
        print(body)
        return 0
    if args.autostart:
        if args.autostart == "status":
            print("开机自启: %s" % ("已开启" if get_autostart() else "未开启"))
            return 0
        ok = set_autostart(args.autostart == "on")
        print("开机自启: %s" % ("已开启" if ok else "未开启"))
        return 0

    # 单实例
    ctypes.set_last_error(0)
    kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if _last_error() == ERROR_ALREADY_EXISTS:
        user32.MessageBoxW(None, "%s 已经在运行了 (请看屏幕右下角系统托盘)。" % APP_NAME,
                           APP_NAME, MB_ICONINFORMATION)
        return 0

    settings = load_settings()
    try:
        settings["autostart"] = get_autostart()
    except Exception:
        pass
    TrayApp(settings).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
