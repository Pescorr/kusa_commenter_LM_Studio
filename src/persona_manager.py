"""
ペルソナ管理システム

このモジュールは、5種類のペルソナ（キャラクター性）を管理し、
重み付きランダムで選択する機能を提供します。
"""

from dataclasses import dataclass
from typing import Dict, List
import random
import logging

from config_utils import SafeConfigParser

# ロガー設定
logger = logging.getLogger(__name__)


@dataclass
class PersonaConfig:
    """
    1つのペルソナの設定情報

    Attributes:
        name: ペルソナ名（例: "narrator", "guesser"）
        weight: 選択時の重み（0-100、大きいほど選ばれやすい）
        color: 表示色（16進数、例: "#FFFFFF"）
        size: フォントサイズ（ピクセル）
        max_chars: 最大文字数
        smart_prompt: Smart Mode用の短縮説明（JSON生成プロンプト内で使用）
        basic_prompt: Basic Mode用のシステムプロンプト（個別API呼び出しで使用）
        display_style: 表示スタイル（空文字 = グローバルデフォルト使用）
    """
    name: str
    weight: int
    color: str
    size: int
    max_chars: int
    smart_prompt: str
    basic_prompt: str
    display_style: str = ""


class PersonaManager:
    """
    ペルソナの管理と選択を担当

    機能:
    - config.iniからペルソナ設定を読み込み
    - 重み付きランダムでペルソナを選択
    - 複数ペルソナの同時選択（重複あり）
    """

    def __init__(self, config: SafeConfigParser):
        """
        Args:
            config: 読み込み済みのSafeConfigParserオブジェクト
        """
        self.personas: Dict[str, PersonaConfig] = {}
        self._load_from_config(config)

    def _load_from_config(self, config: SafeConfigParser):
        """
        config.iniから5つのペルソナ設定を読み込み

        読み込むセクション:
        - [personas]: 重み、色、サイズ、文字数上限
        - [prompts_narrator], [prompts_guesser], ... : システムプロンプト
        """
        persona_names = ['narrator', 'guesser', 'critic', 'instructor', 'analyzer']

        for name in persona_names:
            # [personas] セクションから読み込み
            weight = config.getint('personas', f'{name}_weight', fallback=20)
            color = config.get('personas', f'{name}_color', fallback='#FFFFFF')
            size = config.getint('personas', f'{name}_size', fallback=28)
            max_chars = config.getint('personas', f'{name}_max_chars', fallback=50)
            display_style = config.get('personas', f'{name}_display_style', fallback='')

            # [prompts_{name}] セクションからプロンプト読み込み
            smart_prompt = config.get(
                f'prompts_{name}',
                'smart',
                fallback=f'{name}ペルソナ'
            )
            basic_prompt = config.get(
                f'prompts_{name}',
                'basic',
                fallback=f'{name}ペルソナのプロンプトが未設定です。'
            )

            self.personas[name] = PersonaConfig(
                name=name,
                weight=weight,
                color=color,
                size=size,
                max_chars=max_chars,
                smart_prompt=smart_prompt,
                basic_prompt=basic_prompt,
                display_style=display_style
            )

            logger.info(
                f"ペルソナ '{name}' 読み込み完了: "
                f"重み={weight}, 色={color}, サイズ={size}px, 文字数上限={max_chars}"
            )

        logger.info(f"合計 {len(self.personas)} 個のペルソナを読み込みました")

    def _get_active_personas(self) -> tuple:
        """
        weight > 0 の有効なペルソナのみ取得

        Returns:
            (personas_list, weights) のタプル
            全ペルソナがweight=0の場合は全ペルソナを均等確率で返す
        """
        active = [p for p in self.personas.values() if p.weight > 0]

        if not active:
            # 全ペルソナがweight=0 → フォールバック：全ペルソナ均等
            logger.warning("全ペルソナのweightが0です。均等確率で選択します。")
            active = list(self.personas.values())
            return active, [1] * len(active)

        return active, [p.weight for p in active]

    def select_persona(self) -> PersonaConfig:
        """
        重み付きランダムで1つのペルソナを選択
        weight=0のペルソナは候補から除外される

        Returns:
            選択されたPersonaConfigオブジェクト
        """
        personas_list, weights = self._get_active_personas()
        return random.choices(personas_list, weights=weights, k=1)[0]

    def select_multiple(self, count: int) -> List[PersonaConfig]:
        """
        重み付きランダムで複数のペルソナを選択（重複あり）
        weight=0のペルソナは候補から除外される

        Args:
            count: 選択するペルソナ数

        Returns:
            PersonaConfigのリスト
        """
        personas_list, weights = self._get_active_personas()

        # 重複を許可して選択
        selected_count = min(count, len(personas_list) * 2)  # 最大でも10個まで
        return random.choices(personas_list, weights=weights, k=selected_count)

    def get_persona(self, name: str) -> PersonaConfig:
        """
        名前でペルソナを取得

        Args:
            name: ペルソナ名

        Returns:
            PersonaConfigオブジェクト

        Raises:
            KeyError: 存在しないペルソナ名の場合
        """
        if name not in self.personas:
            logger.warning(f"未知のペルソナ: {name}")
            raise KeyError(f"ペルソナ '{name}' が見つかりません")

        return self.personas[name]
