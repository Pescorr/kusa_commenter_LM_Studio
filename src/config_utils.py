"""
設定ファイル安全読み込みユーティリティ

インラインコメントを自動除去するConfigParserラッパー
"""

import configparser
import re
from typing import Union


class SafeConfigParser:
    """
    ConfigParserのラッパークラス（インラインコメントと空白を自動除去）

    対応例:
        mode = smart    # これはコメント     → "smart" を返す
        color = #FFFFFF # 白色               → "#FFFFFF" を返す
        font = MS Gothic  # デフォルトフォント → "MS Gothic" を返す

    検出パターン: ' #' (空白 + ハッシュ) をコメント開始として扱う
    これにより、#FFFFFF のような16進数カラーコードは保持される
    """

    def __init__(self, config: configparser.ConfigParser):
        """
        初期化

        Args:
            config: ラップするConfigParserインスタンス
        """
        self._config = config

    def _clean_value(self, value: str) -> str:
        """
        インラインコメントを削除し、前後の空白をトリミング

        戦略: ' #' (空白 + ハッシュ) をコメントマーカーとして検出
        これにより、16進数カラー（#FFFFFF等）を保持しながらコメントを除去

        Args:
            value: 生の設定値文字列

        Returns:
            クリーンされた値（コメントと空白を除去）

        処理例:
            "smart    # コメント"     → "smart"
            "#FFFFFF # 白色"          → "#FFFFFF"
            "  value  "               → "value"
        """
        # コメントパターンを検索: 空白 + #
        comment_match = re.search(r'\s+#', value)
        if comment_match:
            # '#' の前の空白から以降をすべて削除
            value = value[:comment_match.start()]

        # 前後の空白をトリミング
        return value.strip()

    def get(self, section: str, option: str, **kwargs) -> str:
        """
        文字列値を取得（インラインコメント自動除去）

        Args:
            section: セクション名
            option: オプション名
            **kwargs: 追加引数（例: fallback）

        Returns:
            クリーンされた文字列値
        """
        value = self._config.get(section, option, **kwargs)
        return self._clean_value(value)

    def getint(self, section: str, option: str, **kwargs) -> int:
        """
        整数値を取得（コメント除去後に変換）

        Args:
            section: セクション名
            option: オプション名
            **kwargs: 追加引数（例: fallback）

        Returns:
            整数値
        """
        raw_value = self._config.get(section, option, **kwargs)
        clean_value = self._clean_value(raw_value)

        # BUG-005修正: 値の検証とエラーメッセージ改善
        if not clean_value:
            raise ValueError(f"設定値が空です: [{section}] {option}")

        try:
            return int(clean_value)
        except ValueError as e:
            raise ValueError(
                f"整数への変換に失敗: [{section}] {option} = '{clean_value}'"
            ) from e

    def getfloat(self, section: str, option: str, **kwargs) -> float:
        """
        浮動小数点値を取得（コメント除去後に変換）

        Args:
            section: セクション名
            option: オプション名
            **kwargs: 追加引数（例: fallback）

        Returns:
            浮動小数点値
        """
        raw_value = self._config.get(section, option, **kwargs)
        clean_value = self._clean_value(raw_value)

        # BUG-005修正: 値の検証とエラーメッセージ改善
        if not clean_value:
            raise ValueError(f"設定値が空です: [{section}] {option}")

        try:
            return float(clean_value)
        except ValueError as e:
            raise ValueError(
                f"浮動小数点数への変換に失敗: [{section}] {option} = '{clean_value}'"
            ) from e

    def getboolean(self, section: str, option: str, **kwargs) -> bool:
        """
        真偽値を取得（コメント除去後に変換）

        Args:
            section: セクション名
            option: オプション名
            **kwargs: 追加引数（例: fallback）

        Returns:
            真偽値
        """
        raw_value = self._config.get(section, option, **kwargs)
        clean_value = self._clean_value(raw_value)
        # 真偽値変換
        return clean_value.lower() in ('true', '1', 'yes', 'on')
