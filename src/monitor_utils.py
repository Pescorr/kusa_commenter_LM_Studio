"""
モニター解決ユーティリティ

mss のモニター列挙順序は Windows の「メインディスプレイ」設定と
一致しない場合がある。このモジュールはWindows APIを使い、
正しいモニターを特定してmssインデックスに変換する。
"""

import ctypes
import ctypes.wintypes
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def set_dpi_awareness():
    """
    プロセスレベルの Per-Monitor DPI Awareness を設定。

    tkinter メインスレッドと mss キャプチャスレッドが
    同じ物理ピクセル座標系で動作するようにする。

    呼び出しタイミング: main() の最初、tkinter.Tk() より前。
    """
    try:
        result = ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_ssize_t(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
        if result:
            logger.info("DPI awareness set: Per-Monitor Aware V2")
            return
    except (AttributeError, OSError):
        pass

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        logger.info("DPI awareness set: Per-Monitor Aware (shcore)")
        return
    except (AttributeError, OSError):
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
        logger.info("DPI awareness set: System Aware (legacy)")
    except (AttributeError, OSError):
        logger.warning("DPI awareness could not be set")


def get_windows_monitors() -> List[Dict]:
    """
    Windows API (EnumDisplayMonitors + GetMonitorInfoW) を使用して
    全モニターの情報を取得。

    Returns:
        [{'left': x, 'top': y, 'width': w, 'height': h,
          'is_primary': bool, 'device': str}, ...]
        Windows列挙順（1-indexed的に使用される想定）
    """
    MONITORINFOF_PRIMARY = 0x00000001

    class RECT(ctypes.Structure):
        _fields_ = [
            ('left', ctypes.wintypes.LONG),
            ('top', ctypes.wintypes.LONG),
            ('right', ctypes.wintypes.LONG),
            ('bottom', ctypes.wintypes.LONG),
        ]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ('cbSize', ctypes.wintypes.DWORD),
            ('rcMonitor', RECT),
            ('rcWork', RECT),
            ('dwFlags', ctypes.wintypes.DWORD),
            ('szDevice', ctypes.wintypes.WCHAR * 32),
        ]

    monitors = []

    def _monitor_enum_proc(hMonitor, hdcMonitor, lprcMonitor, dwData):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(info)):
            rc = info.rcMonitor
            is_primary = bool(info.dwFlags & MONITORINFOF_PRIMARY)
            mon = {
                'left': rc.left,
                'top': rc.top,
                'width': rc.right - rc.left,
                'height': rc.bottom - rc.top,
                'is_primary': is_primary,
                'device': info.szDevice,
            }
            monitors.append(mon)
            logger.info(
                f"  Windows monitor [{len(monitors)}]: {mon['device']} "
                f"({mon['width']}x{mon['height']} at {mon['left']},{mon['top']}) "
                f"{'[PRIMARY]' if is_primary else ''}"
            )
        return True

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.wintypes.BOOL,
        ctypes.wintypes.HMONITOR,
        ctypes.wintypes.HDC,
        ctypes.POINTER(RECT),
        ctypes.wintypes.LPARAM,
    )

    logger.info("Windows EnumDisplayMonitors:")
    ctypes.windll.user32.EnumDisplayMonitors(
        None, None, MONITORENUMPROC(_monitor_enum_proc), 0
    )

    return monitors


def _match_to_mss_index(win_mon: Dict, mss_monitors: list) -> Optional[int]:
    """
    Windowsモニターの座標をmssモニターリストと照合し、
    一致するmssインデックス(1-based)を返す。
    """
    num_monitors = len(mss_monitors) - 1
    for i in range(1, num_monitors + 1):
        m = mss_monitors[i]
        if (m['left'] == win_mon['left'] and
            m['top'] == win_mon['top'] and
            m['width'] == win_mon['width'] and
            m['height'] == win_mon['height']):
            return i
    return None


def resolve_mss_monitor_index(
    target_monitor_config: str,
    mss_monitors: list
) -> int:
    """
    config.ini の target_monitor 値を実際の mss インデックスに変換。

    すべての指定方法でWindows API経由の座標照合を行う。

    Args:
        target_monitor_config: "primary", "secondary", "1", "2", etc.
        mss_monitors: mss.mss().monitors リスト
                      (monitors[0]=全画面合成, monitors[1..N]=個別)

    Returns:
        mss モニターインデックス (1-based)
    """
    config_val = target_monitor_config.lower().strip()

    # Windows APIで全モニター情報を取得
    win_monitors = get_windows_monitors()

    if not win_monitors:
        logger.warning("Windows API returned no monitors, defaulting to mss index 1")
        return 1

    # --- "primary" ---
    if config_val == "primary":
        for wm in win_monitors:
            if wm['is_primary']:
                mss_idx = _match_to_mss_index(wm, mss_monitors)
                if mss_idx is not None:
                    logger.info(
                        f"Primary monitor -> mss index {mss_idx}: "
                        f"{wm['width']}x{wm['height']} at ({wm['left']},{wm['top']})"
                    )
                    return mss_idx
        logger.warning("Could not match primary monitor to mss, defaulting to mss index 1")
        return 1

    # --- "secondary" ---
    if config_val == "secondary":
        for wm in win_monitors:
            if not wm['is_primary']:
                mss_idx = _match_to_mss_index(wm, mss_monitors)
                if mss_idx is not None:
                    logger.info(
                        f"Secondary monitor -> mss index {mss_idx}: "
                        f"{wm['width']}x{wm['height']} at ({wm['left']},{wm['top']})"
                    )
                    return mss_idx
        logger.warning("Could not find secondary monitor, defaulting to mss index 1")
        return 1

    # --- 数値: Windows列挙順のN番目 → mss座標照合 ---
    try:
        idx = int(config_val)
    except ValueError:
        logger.error(
            f"Invalid target_monitor value: '{target_monitor_config}'. "
            f"Must be 'primary', 'secondary', or a number. Defaulting to 1."
        )
        return 1

    if idx < 1 or idx > len(win_monitors):
        logger.warning(
            f"Monitor {idx} not found (available: 1-{len(win_monitors)}), "
            f"defaulting to primary"
        )
        # フォールバック: プライマリを返す
        for wm in win_monitors:
            if wm['is_primary']:
                mss_idx = _match_to_mss_index(wm, mss_monitors)
                if mss_idx is not None:
                    return mss_idx
        return 1

    # N番目のWindowsモニター (1-based)
    target_win_mon = win_monitors[idx - 1]
    mss_idx = _match_to_mss_index(target_win_mon, mss_monitors)
    if mss_idx is not None:
        logger.info(
            f"Windows monitor [{idx}] ({target_win_mon['device']}) -> mss index {mss_idx}: "
            f"{target_win_mon['width']}x{target_win_mon['height']} "
            f"at ({target_win_mon['left']},{target_win_mon['top']})"
        )
        return mss_idx

    logger.warning(
        f"Windows monitor [{idx}] coordinates did not match any mss monitor. "
        f"Defaulting to mss index 1."
    )
    return 1
