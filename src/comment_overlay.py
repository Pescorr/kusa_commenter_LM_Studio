"""
コメントオーバーレイシステム

このモジュールは、透過オーバーレイウィンドウを作成し、
3つの表示スタイルでコメントを表示します。

表示スタイル:
- scroll: 弾幕風の右→左スクロール
- toast: 画面右下にポップアップ通知（フェードイン/アウト付き）
- chatlog: 画面左下にチャットログパネル（YouTube/Twitch風）
"""

import tkinter as tk
import queue
import time
import threading
from typing import List, Optional
import logging

from config_utils import SafeConfigParser
from comment_data import Comment

# ロガー設定
logger = logging.getLogger(__name__)


class LaneManager:
    """
    レーン管理システム（LRU方式）

    弾幕コメントは、複数の「レーン（横線）」に分かれて表示されます。
    このクラスは、新しいコメントをどのレーンに配置するかを決定し、
    コメント同士が重ならないように管理します。

    LRU (Least Recently Used) 方式:
        - 最も古く使われたレーンを優先的に再利用
        - 衝突判定: 前のコメントがまだ画面内にあるかチェック
    """

    def __init__(self, num_lanes: int = 8, screen_width: int = 1920, screen_height: int = 1080):
        """
        Args:
            num_lanes: レーン数（デフォルト8）
            screen_width: 画面幅（ピクセル）
            screen_height: 画面高さ（ピクセル）
        """
        import threading  # BUG-002修正: スレッドセーフ化のためのインポート

        self.num_lanes = num_lanes
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.lane_height = screen_height / num_lanes

        # 各レーンの最後のコメント終了予定時刻
        # None = レーンが空いている
        self.lanes: List[Optional[float]] = [None] * num_lanes

        # BUG-002修正: スレッドセーフ化のためのロック
        self._lock = threading.RLock()

    def allocate_lane(self, comment_width: float, speed: float) -> int:
        """
        コメントを配置するレーンを選択

        アルゴリズム:
        1. 空いているレーンを優先
        2. 前のコメントが完全に通過したレーンを選択
        3. すべて埋まっている場合は最も古いレーン（LRU）を再利用

        Args:
            comment_width: コメントの横幅（ピクセル）
            speed: スクロール速度（ピクセル/秒）

        Returns:
            割り当てられたレーン番号（0～num_lanes-1）
        """
        with self._lock:  # BUG-002修正: スレッドセーフ化
            current_time = time.time()

            # コメントが画面を完全に通過するまでの予想時間を計算
            duration = self._estimate_duration(comment_width, speed)
            end_time = current_time + duration

            # ステップ1: 空きレーンを探す
            for i, lane_end_time in enumerate(self.lanes):
                if lane_end_time is None:
                    # 空きレーン発見
                    self.lanes[i] = end_time
                    return i
                elif current_time > lane_end_time:
                    # 前のコメントが既に終了している
                    self.lanes[i] = end_time
                    return i

            # ステップ2: 全レーンが埋まっている → LRU選択
            # 最も古い終了時刻を持つレーンを探す
            lru_lane = min(range(len(self.lanes)), key=lambda i: self.lanes[i] or 0)
            self.lanes[lru_lane] = end_time
            return lru_lane

    def _estimate_duration(self, width: float, speed: float) -> float:
        """
        コメントが画面を完全に横断するまでの時間を推定

        コメントは画面右端（x = screen_width）から開始し、
        完全に左端から消えるまで（x = -width）移動する。

        総移動距離 = screen_width + width
        時間 = 距離 / 速度

        Args:
            width: コメントの横幅
            speed: スクロール速度

        Returns:
            所要時間（秒）
        """
        total_distance = self.screen_width + width
        return total_distance / speed if speed > 0 else 10.0

    def get_lane_y_position(self, lane: int) -> float:
        """
        レーン番号からY座標を計算

        Args:
            lane: レーン番号（0～num_lanes-1）

        Returns:
            Y座標（ピクセル）
        """
        return lane * self.lane_height + self.lane_height / 2


class CommentOverlay:
    """
    コメント透過オーバーレイウィンドウ

    機能:
    - 画面最前面に透過ウィンドウを表示
    - クリックスルー（クリックが下のウィンドウに透過）
    - 3つの表示スタイル: scroll / toast / chatlog
    - スムーズなアニメーション
    """

    def __init__(self, config: SafeConfigParser, target_monitor: int = 1):
        """
        Args:
            config: SafeConfigParserオブジェクト（config.ini読み込み済み）
            target_monitor: モニター番号（1=プライマリー, 2=セカンダリー, ...）
        """
        import mss

        self.config = config
        self.target_monitor = target_monitor

        # tkinterルートウィンドウ
        self.root = tk.Tk()

        # FPS設定を読み込み、ミリ秒に変換
        self.animation_fps = max(1, config.getint('performance', 'animation_fps', fallback=60))
        self.frame_interval_ms = int(1000 / self.animation_fps)

        # スレッドセーフなコメントキュー
        queue_size = max(1, config.getint('performance', 'comment_queue_size', fallback=100))
        self.comment_queue = queue.Queue(maxsize=queue_size)

        # === Scroll スタイル用 ===
        self.active_comments: List[Comment] = []

        # === Toast スタイル用 ===
        self.toast_comments: List[Comment] = []

        # === Chatlog スタイル用 ===
        self.chatlog_comments: List[Comment] = []

        # ターゲットモニターのサイズと位置を取得（インデックスはmain.pyで解決済み）
        with mss.mss() as sct:
            num_monitors = len(sct.monitors) - 1
            monitor_index = max(1, min(target_monitor, num_monitors))
            if monitor_index != target_monitor:
                logger.warning(
                    f"Monitor index {target_monitor} out of range "
                    f"(1-{num_monitors}), clamped to {monitor_index}"
                )

            monitor = sct.monitors[monitor_index]
            screen_width = monitor['width']
            screen_height = monitor['height']
            self.monitor_left = monitor['left']
            self.monitor_top = monitor['top']

        logger.info(f"Overlay target monitor: {monitor_index} ({screen_width}x{screen_height} at {self.monitor_left},{self.monitor_top})")

        # レーン管理システム（scroll用）
        num_lanes = config.getint('overlay', 'num_lanes', fallback=8)

        self.lane_manager = LaneManager(
            num_lanes=num_lanes,
            screen_width=screen_width,
            screen_height=screen_height
        )

        # 画面サイズを保存
        self.screen_width = screen_width
        self.screen_height = screen_height

        # === スタイル別フォントサイズ（0=ペルソナ設定を使用） ===
        self.scroll_font_size = config.getint('overlay', 'scroll_font_size', fallback=0)
        self.toast_font_size = config.getint('overlay', 'toast_font_size', fallback=0)
        self.chatlog_font_size = config.getint('overlay', 'chatlog_font_size', fallback=0)

        # === Toast設定読み込み ===
        self.toast_lifetime = config.getfloat('overlay', 'toast_lifetime_sec', fallback=5.0)
        self.toast_fade_duration = config.getfloat('overlay', 'toast_fade_duration_sec', fallback=0.5)
        self.toast_max_visible = config.getint('overlay', 'toast_max_visible', fallback=4)
        self.toast_margin_right = config.getint('overlay', 'toast_margin_right', fallback=30)
        self.toast_margin_bottom = config.getint('overlay', 'toast_margin_bottom', fallback=60)
        self.toast_spacing = config.getint('overlay', 'toast_spacing', fallback=8)
        self.toast_padding_h = config.getint('overlay', 'toast_padding_h', fallback=16)
        self.toast_padding_v = config.getint('overlay', 'toast_padding_v', fallback=10)
        self.toast_bg_color = config.get('overlay', 'toast_bg_color', fallback='#1A1A2E')
        self.toast_bg_opacity = config.getfloat('overlay', 'toast_bg_opacity', fallback=0.7)
        self.toast_text_opacity = config.getfloat('overlay', 'toast_text_opacity', fallback=1.0)

        # === Chatlog設定読み込み ===
        self.chatlog_max_lines = config.getint('overlay', 'chatlog_max_lines', fallback=10)
        self.chatlog_panel_width = config.getint('overlay', 'chatlog_panel_width', fallback=450)
        self.chatlog_panel_height = config.getint('overlay', 'chatlog_panel_height', fallback=350)
        self.chatlog_margin_left = config.getint('overlay', 'chatlog_margin_left', fallback=30)
        self.chatlog_margin_bottom = config.getint('overlay', 'chatlog_margin_bottom', fallback=60)
        self.chatlog_bg_color = config.get('overlay', 'chatlog_bg_color', fallback='#0D0D0D')
        self.chatlog_bg_opacity = config.getfloat('overlay', 'chatlog_bg_opacity', fallback=0.7)
        self.chatlog_line_spacing = config.getint('overlay', 'chatlog_line_spacing', fallback=6)
        self.chatlog_padding = config.getint('overlay', 'chatlog_padding', fallback=12)
        self.chatlog_name_visible = config.getboolean('overlay', 'chatlog_name_visible', fallback=True)

        # tkinter基本設定（geometry含む）
        self._setup_window_basic()

        # Canvas（描画領域）
        self.canvas = tk.Canvas(
            self.root,
            width=self.screen_width,
            height=self.screen_height,
            bg='#010101',  # 透明色と同じ色（透明になる）
            highlightthickness=0
        )
        self.canvas.pack()

        # Windows API設定（canvas.pack()後に呼ぶ必要がある）
        self._setup_window_api()

        # アニメーションループの状態
        self.running = False
        self.last_time = time.time()  # デルタタイム計算用

        # フォント設定をキャッシュ（毎フレーム読み込まない）
        self._font_family = config.get('overlay', 'font_family', fallback='MS Gothic')
        self._enable_stroke = config.getboolean('overlay', 'enable_stroke', fallback=True)
        self._stroke_width = config.getint('overlay', 'stroke_width', fallback=2)
        self._stroke_color = config.get('overlay', 'stroke_color', fallback='#000000')

    def _setup_window_basic(self):
        """
        tkinter基本ウィンドウ設定（タイトル、装飾なし、ジオメトリ、背景色）
        """
        self.root.title("Screen Commentator")
        self.root.overrideredirect(True)

        # 正しいモニター座標でジオメトリ設定
        # tkinterは +-1920 形式の負座標を正しく処理する
        self.root.geometry(f'{self.screen_width}x{self.screen_height}+{self.monitor_left}+{self.monitor_top}')

        self.root.config(bg='#010101')
        self.root.attributes('-topmost', True)

    def _setup_window_api(self):
        """
        Windows API でウィンドウ位置確定・透明化・クリックスルーを設定。
        canvas.pack() の後に呼ぶこと（packがジオメトリを再計算するため）。
        """
        import ctypes

        # ウィンドウを描画してからハンドルを取得する
        self.root.update_idletasks()
        self.root.update()

        try:
            user32 = ctypes.windll.user32

            # 正しいトップレベルウィンドウハンドルを取得
            hwnd = user32.FindWindowW(None, "Screen Commentator")
            if not hwnd:
                hwnd = self.root.winfo_id()
                logger.info(f"FindWindowW失敗、winfo_idを使用: {hwnd}")
            else:
                logger.info(f"FindWindowWでHWND取得成功: {hwnd}")

            # SetWindowPos でモニター位置を確定（canvas.pack後のリセット対策）
            HWND_TOPMOST = -1
            SWP_NOACTIVATE = 0x0010
            pos_result = user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                self.monitor_left,
                self.monitor_top,
                self.screen_width,
                self.screen_height,
                SWP_NOACTIVATE
            )
            if pos_result:
                logger.info(
                    f"SetWindowPos成功: ({self.monitor_left},{self.monitor_top}) "
                    f"{self.screen_width}x{self.screen_height}"
                )
            else:
                logger.error(
                    f"SetWindowPos失敗: ({self.monitor_left},{self.monitor_top}) "
                    f"{self.screen_width}x{self.screen_height}"
                )

            # 定数
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            LWA_COLORKEY = 0x00000001

            # WS_EX_LAYERED + WS_EX_TRANSPARENT を設定
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            )

            # 色キー透明化を設定（#010101 = RGB(1,1,1)が透明になる）
            colorref = 0x00010101  # COLORREF形式: 0x00BBGGRR
            result = user32.SetLayeredWindowAttributes(
                hwnd, colorref, 0, LWA_COLORKEY
            )

            if result:
                logger.info("透明化とクリックスルーを有効化しました")
            else:
                logger.error("SetLayeredWindowAttributes失敗")

            # スクリーンキャプチャからオーバーレイを除外
            exclude_from_capture = self.config.getboolean(
                'screenshot', 'exclude_overlay_from_capture', fallback=True
            )
            if exclude_from_capture:
                WDA_EXCLUDEFROMCAPTURE = 0x00000011
                affinity_result = user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
                if affinity_result:
                    logger.info("スクリーンキャプチャからオーバーレイを除外しました")
                else:
                    logger.warning("SetWindowDisplayAffinity失敗 - コメントがスクリーンショットに映る可能性があります")
            else:
                logger.info("オーバーレイはスクリーンショットに映り込みます（exclude_overlay_from_capture=false）")

        except Exception as e:
            logger.error(f"ウィンドウ設定エラー: {e}")

    # ================================================================
    # コメント追加（スレッドセーフ）
    # ================================================================

    def add_comment(self, comment: Comment):
        """
        コメントをキューに追加（スレッドセーフ）

        他のスレッドから呼び出されることを想定

        Args:
            comment: Commentオブジェクト
        """
        try:
            self.comment_queue.put(comment, block=False)
        except queue.Full:
            logger.warning("コメントキューが満杯です。コメントを破棄します。")

    # ================================================================
    # コメントスポーン（ディスパッチャー）
    # ================================================================

    def _spawn_comment(self, comment: Comment):
        """
        コメントを表示スタイルに応じて配置

        Args:
            comment: Commentオブジェクト
        """
        # スタイル別フォントサイズでオーバーライド（0=ペルソナ設定を使用）
        style_size = self._get_style_font_size(comment.display_style)
        if style_size > 0:
            comment.size = style_size

        # テキスト寸法を測定（全スタイル共通）
        font = (self._font_family, comment.size, 'bold')

        temp_text = self.canvas.create_text(0, 0, text=comment.text, font=font)
        bbox = self.canvas.bbox(temp_text)
        self.canvas.delete(temp_text)

        fallback_width = self.config.getint('overlay', 'fallback_comment_width', fallback=100)
        comment.width = bbox[2] - bbox[0] if bbox else fallback_width
        comment.height = bbox[3] - bbox[1] if bbox else comment.size + 4

        # スタイル別にルーティング
        if comment.display_style == "toast":
            self._spawn_toast(comment)
        elif comment.display_style == "chatlog":
            self._spawn_chatlog(comment)
        else:
            self._spawn_scroll(comment)

    def _spawn_scroll(self, comment: Comment):
        """
        Scrollスタイル: レーン割り当て + 画面右端から開始
        """
        lane = self.lane_manager.allocate_lane(comment.width, comment.speed)
        comment.lane = lane
        comment.x = self.lane_manager.screen_width  # 画面右端
        comment.y = self.lane_manager.get_lane_y_position(lane)
        self.active_comments.append(comment)

    def _spawn_toast(self, comment: Comment):
        """
        Toastスタイル: 右下に通知ポップアップ
        """
        comment.spawn_time = time.time()
        comment.lifetime = self.toast_lifetime
        comment.fade_duration = self.toast_fade_duration
        comment.opacity = 0.0  # フェードイン開始

        # 最大表示数を超える場合、最古のtoastを即座にフェードアウトへ
        while len(self.toast_comments) >= self.toast_max_visible:
            oldest = self.toast_comments[0]
            elapsed = time.time() - oldest.spawn_time
            if elapsed < oldest.lifetime:
                # 強制的にフェードアウト開始
                oldest.spawn_time = time.time() - oldest.lifetime
            else:
                # 既にフェードアウト中 or 期限切れ → 即削除
                self.toast_comments.pop(0)

        self.toast_comments.append(comment)

    def _spawn_chatlog(self, comment: Comment):
        """
        Chatlogスタイル: パネルにコメント蓄積
        """
        # ペルソナ名付きテキストで高さを再計測（折り返し考慮）
        if self.chatlog_name_visible:
            display_text = f"{comment.persona}: {comment.text}"
        else:
            display_text = comment.text

        font = (self._font_family, comment.size, 'bold')
        wrap_width = self.chatlog_panel_width - self.chatlog_padding * 2

        temp_text = self.canvas.create_text(
            0, 0, text=display_text, font=font, width=wrap_width
        )
        bbox = self.canvas.bbox(temp_text)
        self.canvas.delete(temp_text)

        comment.height = bbox[3] - bbox[1] if bbox else comment.size + 4
        comment.spawn_time = time.time()

        self.chatlog_comments.append(comment)

        # 最大行数を超えたら古いものから削除
        while len(self.chatlog_comments) > self.chatlog_max_lines:
            self.chatlog_comments.pop(0)

    # ================================================================
    # アニメーションループ
    # ================================================================

    def _animation_step(self):
        """
        フレーム1つ分の処理（メインスレッドで実行）

        after()メソッドで定期的に呼び出される
        """
        if not self.running:
            return

        # デルタタイムを計算
        current_time = time.time()
        dt = current_time - self.last_time
        self.last_time = current_time

        # 新しいコメントをキューから取得
        try:
            while True:
                new_comment = self.comment_queue.get_nowait()
                self._spawn_comment(new_comment)
        except queue.Empty:
            pass

        # Scrollコメントを更新
        for comment in self.active_comments[:]:
            comment.x -= comment.speed * dt
            if comment.x + comment.width < 0:
                self.active_comments.remove(comment)

        # Toastコメントを更新
        self._update_toast_comments(current_time)

        # Chatlogは位置更新不要（静的表示）

        # 画面を再描画
        self._render()

        # 次フレームをスケジュール
        self.root.after(self.frame_interval_ms, self._animation_step)

    def _update_toast_comments(self, current_time: float):
        """
        Toastコメントの不透明度更新と期限切れ削除
        """
        to_remove = []

        for comment in self.toast_comments:
            elapsed = current_time - comment.spawn_time

            if elapsed < comment.fade_duration:
                # フェードイン中
                comment.opacity = elapsed / comment.fade_duration
            elif elapsed < comment.lifetime:
                # 完全表示中
                comment.opacity = 1.0
            elif elapsed < comment.lifetime + comment.fade_duration:
                # フェードアウト中
                fade_progress = (elapsed - comment.lifetime) / comment.fade_duration
                comment.opacity = 1.0 - fade_progress
            else:
                # 期限切れ
                to_remove.append(comment)

        for comment in to_remove:
            self.toast_comments.remove(comment)

    # ================================================================
    # 描画
    # ================================================================

    def _render(self):
        """
        Canvas上にすべてのスタイルのコメントを描画

        描画順序:
        1. Chatlogパネル背景（最背面）
        2. Scrollコメント
        3. Toast通知（最前面）
        """
        self.canvas.delete('all')

        # 1. Chatlog描画
        self._render_chatlog_panel()

        # 2. Scroll描画
        self._render_scroll_comments()

        # 3. Toast描画
        self._render_toast_comments()

        # Canvasを更新
        self.root.update_idletasks()

    def _render_scroll_comments(self):
        """
        Scrollスタイルのコメントを描画
        """
        for comment in self.active_comments:
            font = (self._font_family, comment.size, 'bold')

            if self._enable_stroke:
                sw = self._stroke_width
                for dx, dy in [(-sw, 0), (sw, 0),
                               (0, -sw), (0, sw),
                               (-sw, -sw), (sw, sw),
                               (-sw, sw), (sw, -sw)]:
                    self.canvas.create_text(
                        comment.x + dx, comment.y + dy,
                        text=comment.text, font=font,
                        fill=self._stroke_color, anchor='nw'
                    )

            self.canvas.create_text(
                comment.x, comment.y,
                text=comment.text, font=font,
                fill=comment.color, anchor='nw'
            )

    def _render_toast_comments(self):
        """
        Toastスタイルのコメントを描画（右下にスタック）

        フェード効果: 色を#010101（透明キー色）に向けて補間することで
        tkinterのカラーキー透過を利用した擬似フェードを実現
        """
        if not self.toast_comments:
            return

        base_x = self.screen_width - self.toast_margin_right
        current_y = self.screen_height - self.toast_margin_bottom

        # 新しいもの（リスト末尾）を下、古いものを上に描画
        for comment in reversed(self.toast_comments):
            font = (self._font_family, comment.size, 'bold')

            # ボックスサイズ
            box_w = comment.width + self.toast_padding_h * 2
            box_h = comment.height + self.toast_padding_v * 2

            # ボックス位置（右揃え、下から上へ）
            box_x1 = base_x - box_w
            box_y1 = current_y - box_h
            box_x2 = base_x
            box_y2 = current_y

            # 不透明度に基づく色補間（フェード効果 × ベース透明度）
            # フェード opacity (0→1→0) にベース透明度を掛けて最終的な不透明度を算出
            effective_bg_opacity = comment.opacity * self.toast_bg_opacity
            effective_text_opacity = comment.opacity * self.toast_text_opacity

            faded_text = self._interpolate_color(
                '#010101', comment.color, effective_text_opacity
            )
            faded_stroke = self._interpolate_color(
                '#010101', self._stroke_color, effective_text_opacity
            )

            # 背景矩形（opacity が実質ゼロなら描画スキップ）
            # ※ #010101ガードにより opacity≈0 でも #020202 が描画されてしまう問題の対策
            if effective_bg_opacity > 0.01:
                faded_bg = self._interpolate_color(
                    '#010101', self.toast_bg_color, effective_bg_opacity
                )
                self.canvas.create_rectangle(
                    box_x1, box_y1, box_x2, box_y2,
                    fill=faded_bg, outline=''
                )

            # テキスト
            text_x = box_x1 + self.toast_padding_h
            text_y = box_y1 + self.toast_padding_v

            if self._enable_stroke:
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    self.canvas.create_text(
                        text_x + dx, text_y + dy,
                        text=comment.text, font=font,
                        fill=faded_stroke, anchor='nw'
                    )

            self.canvas.create_text(
                text_x, text_y,
                text=comment.text, font=font,
                fill=faded_text, anchor='nw'
            )

            # 次のtoastの位置を上に移動
            current_y = box_y1 - self.toast_spacing

    def _render_chatlog_panel(self):
        """
        Chatlogスタイルのパネルとコメントを描画（左下）
        """
        if not self.chatlog_comments:
            return

        # パネル位置
        panel_x = self.chatlog_margin_left
        panel_y = self.screen_height - self.chatlog_margin_bottom - self.chatlog_panel_height
        panel_w = self.chatlog_panel_width
        panel_h = self.chatlog_panel_height

        # 半透明背景パネル（opacity が実質ゼロなら描画スキップ）
        if self.chatlog_bg_opacity > 0.01:
            bg_color = self._get_chatlog_bg_color()
            self.canvas.create_rectangle(
                panel_x, panel_y,
                panel_x + panel_w, panel_y + panel_h,
                fill=bg_color, outline=''
            )

        # コメントを下から上に描画
        text_x = panel_x + self.chatlog_padding
        current_y = panel_y + panel_h - self.chatlog_padding
        wrap_width = panel_w - self.chatlog_padding * 2

        for comment in reversed(self.chatlog_comments):
            font = (self._font_family, comment.size, 'bold')

            # ペルソナ名付きテキスト
            if self.chatlog_name_visible:
                display_text = f"{comment.persona}: {comment.text}"
            else:
                display_text = comment.text

            text_y = current_y - comment.height

            # パネル上端を超えたら描画しない
            if text_y < panel_y + self.chatlog_padding:
                break

            self.canvas.create_text(
                text_x, text_y,
                text=display_text, font=font,
                fill=comment.color, anchor='nw',
                width=wrap_width
            )

            current_y = text_y - self.chatlog_line_spacing

    # ================================================================
    # ヘルパーメソッド
    # ================================================================

    def _get_style_font_size(self, display_style: str) -> int:
        """
        表示スタイルごとのフォントサイズを取得

        Args:
            display_style: "scroll" / "toast" / "chatlog"

        Returns:
            フォントサイズ（0 = ペルソナ設定をそのまま使用）
        """
        if display_style == "scroll":
            return self.scroll_font_size
        elif display_style == "toast":
            return self.toast_font_size
        elif display_style == "chatlog":
            return self.chatlog_font_size
        return 0

    @staticmethod
    def _interpolate_color(color_a: str, color_b: str, t: float) -> str:
        """
        2つの16進数カラーを線形補間

        t=0.0 → color_a, t=1.0 → color_b
        Toastのフェード効果に使用（#010101 = 透明キー色に向けて補間）

        重要: #010101 はカラーキー透明色なので、結果がこの値に
        なると意図せず透明になる。ガードとして #020202 にシフト。

        Args:
            color_a: 開始色（16進数 "#RRGGBB"）
            color_b: 終了色（16進数 "#RRGGBB"）
            t: 補間パラメータ（0.0 ～ 1.0）

        Returns:
            補間された色（16進数 "#RRGGBB"）
        """
        t = max(0.0, min(1.0, t))

        r_a = int(color_a[1:3], 16)
        g_a = int(color_a[3:5], 16)
        b_a = int(color_a[5:7], 16)

        r_b = int(color_b[1:3], 16)
        g_b = int(color_b[3:5], 16)
        b_b = int(color_b[5:7], 16)

        r = int(r_a + (r_b - r_a) * t)
        g = int(g_a + (g_b - g_a) * t)
        b = int(b_a + (b_b - b_a) * t)

        # カラーキー透明色 #010101 との衝突を回避
        if r == 1 and g == 1 and b == 1:
            r, g, b = 2, 2, 2

        return f'#{r:02X}{g:02X}{b:02X}'

    def _get_chatlog_bg_color(self) -> str:
        """
        Chatlogパネルの背景色を計算（擬似不透明度適用）

        完全な透過は不可能（tkinter制限）なので、
        設定色にopacityを掛けて暗い色を生成する。

        Returns:
            背景色（16進数 "#RRGGBB"）
        """
        opacity = self.chatlog_bg_opacity
        r = int(int(self.chatlog_bg_color[1:3], 16) * opacity)
        g = int(int(self.chatlog_bg_color[3:5], 16) * opacity)
        b = int(int(self.chatlog_bg_color[5:7], 16) * opacity)

        # カラーキー透明色との衝突回避
        if r == 1 and g == 1 and b == 1:
            r, g, b = 2, 2, 2
        if r == 0 and g == 0 and b == 0:
            r, g, b = 2, 2, 2  # 真っ黒も暗すぎるので少しシフト

        return f'#{r:02X}{g:02X}{b:02X}'

    # ================================================================
    # メインループ
    # ================================================================

    def run(self):
        """
        tkinterメインループを開始（ブロッキング）
        """
        # アニメーション開始
        self.running = True
        self.last_time = time.time()

        # 最初のフレームをスケジュール（after()でメインスレッドで実行）
        self.root.after(self.frame_interval_ms, self._animation_step)

        logger.info("コメントオーバーレイを起動しました")

        # tkinterメインループ
        self.root.mainloop()

    def stop(self):
        """
        オーバーレイを停止
        """
        logger.info("コメントオーバーレイを停止しています...")
        self.running = False

        try:
            self.root.quit()
            self.root.destroy()
        except Exception as e:
            logger.error(f"オーバーレイ停止エラー: {e}")
