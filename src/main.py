"""
Windows版 Screen Commentator - メインエントリーポイント

弾幕風のスクロールコメントを画面上に表示します。

Phase 2完全版: ペルソナシステム + LLM統合
"""

import configparser
import queue
import sys
import logging
import threading
from pathlib import Path
from typing import Optional

# srcディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent))


def get_base_dir() -> Path:
    """EXE実行時はEXEのフォルダ、開発時はプロジェクトルートを返す"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


from config_utils import SafeConfigParser
from comment_overlay import CommentOverlay
from persona_manager import PersonaManager
from comment_generator import CommentGenerator
from screenshot_capture import ScreenshotCaptureThread, LLMWorkerThread
from llm_client import LMStudioClient
from llama_server_manager import LlamaServerManager

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> SafeConfigParser:
    """
    設定ファイルを読み込み

    Args:
        config_path: config.iniへのパス

    Returns:
        SafeConfigParserオブジェクト（インラインコメント自動除去）
    """
    # BUG-003修正: interpolation=Noneで変数補間を無効化（%記号のエラー回避）
    config = configparser.ConfigParser(interpolation=None)

    if not config_path.exists():
        logger.error(f"設定ファイルが見つかりません: {config_path}")
        raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")

    config.read(config_path, encoding='utf-8')
    logger.info(f"設定ファイル読み込み完了: {config_path}")

    # SafeConfigParserでラップしてインラインコメントを自動除去
    safe_config = SafeConfigParser(config)
    return safe_config


def maybe_start_llama_server(config: SafeConfigParser) -> Optional[LlamaServerManager]:
    """
    config.ini の [llama_server] セクションで auto_start = true なら llama-server.exe を起動。
    起動成功時は LlamaServerManager を返す（atexit で確実に停止）。
    無効化されている、または起動失敗の場合は None を返す。

    Returns:
        LlamaServerManager または None
    """
    if not config._config.has_section('llama_server'):
        return None
    if not config.getboolean('llama_server', 'auto_start', fallback=False):
        logger.info("llama_server.auto_start = false, skip starting llama-server")
        return None

    base_dir = get_base_dir()

    def _resolve(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (base_dir / path)

    exe_path = _resolve(config.get('llama_server', 'executable_path',
                                    fallback='llama_server/llama-server.exe'))
    model_path = _resolve(config.get('llama_server', 'model_path',
                                      fallback='models/Qwen3.5-9B-Q4_K_M.gguf'))
    mmproj_str = config.get('llama_server', 'mmproj_path', fallback='models/mmproj-BF16.gguf')
    mmproj_path = _resolve(mmproj_str) if mmproj_str else None

    manager = LlamaServerManager(
        executable_path=exe_path,
        model_path=model_path,
        mmproj_path=mmproj_path,
        port=config.getint('llama_server', 'port', fallback=8080),
        n_gpu_layers=config.getint('llama_server', 'n_gpu_layers', fallback=-1),
        ctx_size=config.getint('llama_server', 'ctx_size', fallback=8192),
        extra_args=config.get('llama_server', 'extra_args', fallback=''),
    )

    try:
        manager.start()
    except FileNotFoundError as e:
        logger.error("llama-server を起動できませんでした: %s", e)
        try:
            import tkinter.messagebox as mb
            mb.showerror(
                "セットアップ未完了",
                str(e) + "\n\n初回起動時は setup_model.bat を実行してモデルを"
                         "ダウンロードしてください。"
            )
        except Exception:
            pass
        sys.exit(1)

    timeout_sec = config.getfloat('llama_server', 'startup_timeout_sec', fallback=180.0)
    logger.info("llama-server の起動を待機中 (最大 %.0f 秒)...", timeout_sec)
    if not manager.wait_until_ready(timeout=timeout_sec):
        logger.error("llama-server が起動しませんでした。")
        manager.stop()
        try:
            import tkinter.messagebox as mb
            mb.showerror(
                "llama-server 起動失敗",
                f"llama-server が {timeout_sec:.0f} 秒以内に起動しませんでした。\n"
                "config.ini の [llama_server] 設定を確認してください。"
            )
        except Exception:
            pass
        sys.exit(1)

    return manager


def initialize_llm_client(config: SafeConfigParser) -> LMStudioClient:
    """
    LM Studio クライアントを初期化

    Args:
        config: SafeConfigParserオブジェクト

    Returns:
        LMStudioClientインスタンス
    """
    llm_client = LMStudioClient(
        base_url=config.get('llm', 'api_base_url', fallback='http://localhost:1234/v1'),
        vision_model_name=config.get('llm', 'vision_model_name', fallback='local-model'),
        summary_model_name=config.get('llm', 'summary_model_name', fallback='local-model'),
        timeout=config.getint('llm', 'timeout_sec', fallback=60),
        max_retries=config.getint('llm', 'max_retries', fallback=10),
        temperature=config.getfloat('llm', 'temperature', fallback=0.0),
        action_log_max_tokens=config.getint('llm', 'action_log_max_tokens', fallback=150),
        summary_max_tokens=config.getint('llm', 'summary_max_tokens', fallback=2048),
        action_log_system_prompt=config.get('llm', 'action_log_system_prompt', fallback=''),
        summary_system_prompt=config.get('llm', 'summary_system_prompt', fallback=''),
        max_width=config.getint('screenshot', 'max_width', fallback=1280),
        image_quality=config.getint('screenshot', 'image_quality', fallback=90),
        smart_mode_max_tokens=config.getint('llm', 'smart_mode_max_tokens', fallback=300),
        basic_mode_max_tokens=config.getint('llm', 'basic_mode_max_tokens', fallback=100),
        api_error_cooldown_sec=config.getint('llm', 'api_error_cooldown_sec', fallback=300),
        api_token=config.get('llm', 'api_token', fallback=''),
        api_mode=config.get('llm', 'api_mode', fallback='openai'),
        mcp_integrations=config.get('llm', 'mcp_integrations', fallback=''),
    )

    logger.info("LM Studio クライアント初期化完了")
    return llm_client


def initialize_persona_manager(config: SafeConfigParser) -> PersonaManager:
    """
    ペルソナマネージャーを初期化

    Args:
        config: SafeConfigParserオブジェクト

    Returns:
        PersonaManagerインスタンス
    """
    persona_manager = PersonaManager(config)
    logger.info("ペルソナマネージャー初期化完了")
    return persona_manager


def initialize_comment_generator(
    llm_client: LMStudioClient,
    persona_manager: PersonaManager,
    config: SafeConfigParser
) -> CommentGenerator:
    """
    コメントジェネレーターを初期化

    Args:
        llm_client: LMStudioClientインスタンス
        persona_manager: PersonaManagerインスタンス
        config: SafeConfigParserオブジェクト

    Returns:
        CommentGeneratorインスタンス
    """
    comment_generator = CommentGenerator(llm_client, persona_manager, config)
    logger.info("コメントジェネレーター初期化完了")
    return comment_generator


def create_tray_icon(on_exit):
    """
    システムトレイアイコンを作成

    Args:
        on_exit: 終了時に呼ばれるコールバック関数

    Returns:
        pystray.Iconインスタンス
    """
    from PIL import Image, ImageDraw
    import pystray
    import os

    # 簡易アイコン画像を生成（青い四角に白い「C」）
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 背景: 丸い青色
    draw.ellipse([2, 2, size - 2, size - 2], fill=(50, 120, 220, 255))
    # 「C」の文字（Screen Commentator の頭文字）
    draw.text((size // 2, size // 2), "C", fill=(255, 255, 255, 255), anchor="mm")

    def open_config(_icon, _item):
        """config.iniを開く"""
        config_path = get_base_dir() / 'config.ini'
        try:
            os.startfile(str(config_path))
            logger.info(f"設定ファイルを開きました: {config_path}")
        except Exception as e:
            logger.error(f"設定ファイルを開けませんでした: {e}")

    def exit_action(icon, _item):
        """トレイアイコンの終了アクションを実行"""
        logger.info("トレイアイコンから終了が選択されました")
        icon.stop()
        on_exit()

    icon = pystray.Icon(
        name="screen_commentator",
        icon=img,
        title="Screen Commentator",
        menu=pystray.Menu(
            pystray.MenuItem("設定を開く", open_config),
            pystray.MenuItem("終了", exit_action),
        )
    )
    return icon


def main():
    """
    メインエントリーポイント
    """
    logger.info("=" * 60)
    logger.info("Windows版 Screen Commentator 起動中...")
    logger.info("=" * 60)

    # DPI awareness設定（tkinter.Tk()より前に呼ぶ必要がある）
    from monitor_utils import set_dpi_awareness, resolve_mss_monitor_index
    set_dpi_awareness()

    # 設定ファイル読み込み
    config_path = get_base_dir() / 'config.ini'
    config = load_config(config_path)

    # screenshots_tempディレクトリを作成
    temp_dir = Path(config.get('screenshot', 'temp_dir', fallback='screenshots_temp'))
    if not temp_dir.is_absolute():
        temp_dir = get_base_dir() / temp_dir
    temp_dir.mkdir(exist_ok=True)
    logger.info(f"スクリーンショット一時ディレクトリ: {temp_dir}")

    # llama-server を auto_start = true なら起動して ready まで待機
    llama_server = maybe_start_llama_server(config)
    if llama_server:
        # config の api_base_url が未設定／空ならサーバの URL を使う
        configured_url = config.get('llm', 'api_base_url', fallback='').strip()
        if not configured_url:
            config._config.set('llm', 'api_base_url', llama_server.base_url)

    # LM Studio クライアント初期化
    logger.info("LM Studio クライアントを初期化中...")
    llm_client = initialize_llm_client(config)

    # ペルソナマネージャー初期化
    logger.info("ペルソナマネージャーを初期化中...")
    persona_manager = initialize_persona_manager(config)

    # コメントジェネレーター初期化
    logger.info("コメントジェネレーターを初期化中...")
    comment_generator = initialize_comment_generator(llm_client, persona_manager, config)

    # モニター解決（キャプチャとオーバーレイを別々に設定可能）
    import mss
    # 後方互換: 旧 target_monitor が存在する場合はフォールバックとして使用
    fallback_monitor = config.get('display', 'target_monitor', fallback='primary')
    capture_monitor_str = config.get('display', 'capture_monitor', fallback=fallback_monitor)
    overlay_monitor_str = config.get('display', 'overlay_monitor', fallback=fallback_monitor)

    with mss.mss() as sct:
        num_monitors = len(sct.monitors) - 1
        logger.info("=" * 60)
        logger.info(f"利用可能なモニター ({num_monitors}台):")
        for i in range(1, num_monitors + 1):
            monitor = sct.monitors[i]
            logger.info(f"  mss[{i}]: {monitor['width']}x{monitor['height']} at ({monitor['left']}, {monitor['top']})")

        # キャプチャモニター解決
        capture_mss_idx = resolve_mss_monitor_index(capture_monitor_str, sct.monitors)
        cap_info = sct.monitors[capture_mss_idx]
        logger.info(
            f"キャプチャモニター: config='{capture_monitor_str}' -> "
            f"mss[{capture_mss_idx}] = {cap_info['width']}x{cap_info['height']} "
            f"at ({cap_info['left']},{cap_info['top']})"
        )

        # オーバーレイモニター解決
        overlay_mss_idx = resolve_mss_monitor_index(overlay_monitor_str, sct.monitors)
        ovl_info = sct.monitors[overlay_mss_idx]
        logger.info(
            f"オーバーレイモニター: config='{overlay_monitor_str}' -> "
            f"mss[{overlay_mss_idx}] = {ovl_info['width']}x{ovl_info['height']} "
            f"at ({ovl_info['left']},{ovl_info['top']})"
        )
        logger.info("=" * 60)

    # コメントオーバーレイ初期化
    logger.info("コメントオーバーレイを初期化中...")
    overlay = CommentOverlay(config, target_monitor=overlay_mss_idx)

    # キュー初期化
    screenshot_queue = queue.Queue(maxsize=config.getint('performance', 'screenshot_queue_size', fallback=10))

    # スレッド初期化
    threads = []

    # スクリーンショットキャプチャスレッド
    logger.info("スクリーンショットキャプチャスレッド起動...")
    capture_thread = ScreenshotCaptureThread(
        screenshot_queue=screenshot_queue,
        interval=config.getfloat('screenshot', 'capture_interval_sec', fallback=20.0),
        idle_threshold=config.getfloat('screenshot', 'idle_threshold_sec', fallback=30.0),
        idle_interval=config.getfloat('screenshot', 'idle_interval_sec', fallback=60.0),
        max_interval=config.getfloat('screenshot', 'max_interval_sec', fallback=120.0),
        idle_backoff_factor=config.getfloat('screenshot', 'idle_backoff_factor', fallback=1.5),
        temp_dir=str(temp_dir),
        image_quality=config.getint('screenshot', 'image_quality', fallback=90),
        image_format=config.get('screenshot', 'image_format', fallback='jpeg'),
        max_temp_files=config.getint('screenshot', 'max_temp_files', fallback=5),
        get_last_activity_time=None,
        target_monitor=capture_mss_idx,
    )
    threads.append(capture_thread)

    # LLMワーカースレッド（4つ並列）
    num_workers = config.getint('performance', 'llm_worker_threads', fallback=4)
    logger.info(f"LLMワーカースレッド {num_workers}個 起動...")
    for i in range(num_workers):
        worker = LLMWorkerThread(
            screenshot_queue=screenshot_queue,
            action_log_queue=None,  # 旧システムは使用しない
            llm_client=llm_client,
            username=config.get('general', 'username', fallback='User'),
            storage_mode=config.get('screenshot', 'storage_mode', fallback='temp'),
            comment_generator=comment_generator,
            overlay=overlay,
        )
        threads.append(worker)

    # すべてのスレッド開始
    for thread in threads:
        thread.start()

    logger.info("")
    logger.info("=" * 60)
    logger.info("起動完了！")
    logger.info("スクリーンショットを撮影し、AIがスクロールコメントを生成します。")
    logger.info("終了するにはシステムトレイアイコンの「終了」を選択してください。")
    logger.info("=" * 60)
    logger.info("")

    # 終了処理のコールバック
    def shutdown():
        """トレイアイコンまたはCtrl+Cから呼ばれる終了処理"""
        logger.info("終了処理を開始...")
        # オーバーレイ停止（tkinterメインループを終了）
        overlay.stop()

    # システムトレイアイコンを別スレッドで起動
    tray_icon = create_tray_icon(on_exit=shutdown)
    tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
    tray_thread.start()
    logger.info("システムトレイアイコンを起動しました")

    try:
        # オーバーレイのメインループ実行（ブロッキング）
        overlay.run()
    except KeyboardInterrupt:
        logger.info("\n終了処理中...")
    finally:
        # トレイアイコンを停止
        try:
            tray_icon.stop()
        except Exception:
            pass

        # すべてのスレッドを停止
        for thread in threads:
            thread.stop()

        # スレッドの終了を待機
        for thread in threads:
            thread.join(timeout=5)

        # オーバーレイ停止
        overlay.stop()

        logger.info("=" * 60)
        logger.info("終了しました。")
        logger.info("=" * 60)


if __name__ == '__main__':
    main()
