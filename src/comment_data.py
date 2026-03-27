"""
コメントデータ構造の定義

このモジュールはScreen Commentatorで使用される
基本的なデータクラスを定義します。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Comment:
    """
    オーバーレイに表示する1つのコメント

    Attributes:
        text: コメントのテキスト内容
        persona: ペルソナ名 (narrator/guesser/critic/instructor/analyzer)
        color: 表示色（16進数、例: "#FFFFFF"）
        size: フォントサイズ（ピクセル）
        speed: スクロール速度（ピクセル/秒、scroll用）
        display_style: 表示スタイル ("scroll" / "toast" / "chatlog")
        lane: 割り当てられたレーン番号（0-7、初期値None、scroll用）
        x: 現在のX座標（画面右端から開始、初期値0.0）
        y: 現在のY座標（レーンによって決定、初期値0.0）
        width: テキストの横幅（ピクセル、描画時に計算、初期値0.0）
        height: テキストの高さ（ピクセル、toast/chatlog用）
        spawn_time: 表示開始時刻（UNIX時刻、toast用）
        lifetime: 表示秒数（toast用）
        fade_duration: フェードイン/アウト秒数（toast用）
        opacity: 不透明度 0.0-1.0（toast用フェード制御）
    """
    text: str
    persona: str
    color: str
    size: int
    speed: float
    display_style: str = "scroll"
    lane: Optional[int] = None
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    spawn_time: float = 0.0
    lifetime: float = 5.0
    fade_duration: float = 0.5
    opacity: float = 1.0


@dataclass
class CommentContext:
    """
    コメント生成に必要なコンテキスト情報

    Attributes:
        screenshot_path: スクリーンショットファイルのパス
        timestamp: スクリーンショット撮影時刻（UNIX時刻）

    将来的に追加予定:
        active_app: アクティブなアプリケーション名
        window_title: ウィンドウタイトル
        excitement_score: 画面変化の興奮度（1-10）
        user_active: ユーザーがアクティブかどうか
    """
    screenshot_path: str
    timestamp: float
