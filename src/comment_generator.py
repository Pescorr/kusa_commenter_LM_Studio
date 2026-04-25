"""
コメント生成オーケストレーター

このモジュールは、Smart ModeとBasic Modeを統合し、
LLMを使ったコメント生成を一元管理します。
"""

from enum import Enum
from typing import List
import json
import random
import re
import logging

from config_utils import SafeConfigParser
from comment_data import Comment, CommentContext
from persona_manager import PersonaManager, PersonaConfig

# ロガー設定
logger = logging.getLogger(__name__)


class PipelineMode(Enum):
    """パイプラインモードの列挙型"""
    SMART = "smart"    # 1回のAPI呼び出し→JSON
    BASIC = "basic"    # 複数回のAPI呼び出し


class CommentGenerator:
    """
    コメント生成の中核クラス

    機能:
    - Smart Mode: 1回のAPI呼び出しで全ペルソナのコメントを取得
    - Basic Mode: 各ペルソナごとに個別API呼び出し
    - Fallback: API障害時のテンプレートコメント生成
    - 自動モード切り替え（Smart Mode失敗 → Basic Mode）
    """

    def __init__(self,
                 llm_client,
                 persona_manager: PersonaManager,
                 config: SafeConfigParser):
        """
        Args:
            llm_client: LM Studio APIクライアント
            persona_manager: ペルソナマネージャー
            config: 設定オブジェクト
        """
        self.llm_client = llm_client
        self.persona_manager = persona_manager
        self.config = config

        # パイプラインモード設定
        mode_str = config.get('pipeline', 'mode', fallback='smart')
        self.pipeline_mode = PipelineMode[mode_str.upper()]

        # Smart Mode失敗カウンター
        self.smart_mode_failures = 0
        self.max_smart_failures = config.getint('pipeline', 'smart_mode_max_failures', fallback=5)

        logger.info(f"CommentGenerator初期化: モード={self.pipeline_mode.value}")

    def generate(self, context: CommentContext) -> List[Comment]:
        """
        コメント生成のメインエントリーポイント

        Args:
            context: スクリーンショットやタイムスタンプ等のコンテキスト

        Returns:
            Commentオブジェクトのリスト（1-5個）
        """
        try:
            if self.pipeline_mode == PipelineMode.SMART:
                return self._smart_mode_generation(context)
            else:
                return self._basic_mode_generation(context)
        except Exception as e:
            logger.error(f"コメント生成エラー: {e}", exc_info=True)
            return self._generate_fallback_comments(context)

    def _smart_mode_generation(self, context: CommentContext) -> List[Comment]:
        """
        Smart Mode: 1回のAPI呼び出しでJSON形式の複数コメント取得

        フロー:
        1. 3-5個のペルソナをランダム選択
        2. Smart Mode用のシステムプロンプトを構築
        3. LLM APIを1回呼び出し
        4. JSON応答を解析
        5. Commentオブジェクトのリストを生成

        Args:
            context: コメント生成コンテキスト

        Returns:
            Commentオブジェクトのリスト
        """
        # ステップ1: ターゲットペルソナを3-5個選択
        num_personas = random.randint(3, 5)
        target_personas = self.persona_manager.select_multiple(count=num_personas)

        # ステップ2: Smart Mode用システムプロンプト構築
        system_prompt = self._build_smart_mode_prompt(target_personas)

        # ステップ3: API呼び出し
        try:
            response_text = self.llm_client.generate_comments_smart_mode(
                screenshot_path=context.screenshot_path,
                system_prompt=system_prompt
            )

            # ステップ4: JSON解析
            # LLMが余計なテキストを含む場合があるので、JSON部分を抽出
            response_text = self._extract_json(response_text)
            comments_data = json.loads(response_text)
            comments = []

            for item in comments_data.get('comments', []):
                persona_name = item.get('persona', '')
                text = item.get('text', '')

                if not persona_name or not text:
                    continue

                # ペルソナ設定を取得
                try:
                    persona_config = self.persona_manager.get_persona(persona_name)
                except KeyError:
                    logger.warning(f"未知のペルソナ: {persona_name}、スキップします")
                    continue

                # Commentオブジェクト作成
                comment = Comment(
                    text=text[:persona_config.max_chars],  # 文字数制限
                    persona=persona_name,
                    color=persona_config.color,
                    size=persona_config.size,
                    speed=self._calculate_speed(),
                    display_style=self._resolve_display_style(persona_name)
                )
                comments.append(comment)

            # 成功 → 失敗カウンターリセット
            self.smart_mode_failures = 0
            logger.info(f"Smart Mode成功: {len(comments)}個のコメント生成")

            return comments

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # JSON解析失敗
            logger.warning(f"Smart Mode JSON解析失敗: {e}")
            self.smart_mode_failures += 1

            # 連続失敗が上限に達したらBasic Modeに切り替え
            if self.smart_mode_failures >= self.max_smart_failures:
                logger.info(f"Smart Mode {self.max_smart_failures}回連続失敗 → Basic Modeに切り替え")
                self.pipeline_mode = PipelineMode.BASIC

            # 今回はBasic Modeでリトライ
            return self._basic_mode_generation(context)

    def _basic_mode_generation(self, context: CommentContext) -> List[Comment]:
        """
        Basic Mode: 各ペルソナごとに個別API呼び出し

        フロー:
        1. 3個のペルソナをランダム選択
        2. 各ペルソナごとにAPI呼び出し（計3回）
        3. Commentオブジェクトを生成

        Args:
            context: コメント生成コンテキスト

        Returns:
            Commentオブジェクトのリスト
        """
        comments = []

        # 3個のペルソナを選択（全5個は多すぎるので）
        selected_personas = self.persona_manager.select_multiple(count=3)

        for persona_config in selected_personas:
            try:
                # 個別API呼び出し
                text = self.llm_client.generate_comment_single_persona(
                    screenshot_path=context.screenshot_path,
                    system_prompt=persona_config.basic_prompt,
                    max_chars=persona_config.max_chars
                )

                comment = Comment(
                    text=text,
                    persona=persona_config.name,
                    color=persona_config.color,
                    size=persona_config.size,
                    speed=self._calculate_speed(),
                    display_style=self._resolve_display_style(persona_config.name)
                )
                comments.append(comment)

            except Exception as e:
                logger.error(f"Basic Mode: {persona_config.name} の生成失敗: {e}")
                continue

        logger.info(f"Basic Mode成功: {len(comments)}個のコメント生成")
        return comments if comments else self._generate_fallback_comments(context)

    def _generate_fallback_comments(self, context: CommentContext) -> List[Comment]:
        """
        フォールバック: API障害時のテンプレートコメント

        Args:
            context: コメント生成コンテキスト

        Returns:
            Commentオブジェクトのリスト（1個）
        """
        templates = [
            "何してるんだ？",
            "...",
            "画面を見ている",
            "作業中",
            "zzz",
        ]

        text = random.choice(templates)
        persona_config = self.persona_manager.get_persona('narrator')

        logger.info("フォールバックコメント使用")
        return [Comment(
            text=text,
            persona='narrator',
            color=persona_config.color,
            size=persona_config.size,
            speed=self._calculate_speed(),
            display_style=self._resolve_display_style('narrator')
        )]

    def _build_smart_mode_prompt(self, personas: List[PersonaConfig]) -> str:
        """
        Smart Mode用のシステムプロンプトを構築

        Args:
            personas: ターゲットペルソナのリスト

        Returns:
            システムプロンプト文字列
        """
        prompt = f"""あなたはスクロールコメント生成AIです。
スクリーンショットを分析し、以下の{len(personas)}つのペルソナで合計{len(personas)}個のコメントを生成してください。

【ペルソナ一覧】
"""
        for p in personas:
            prompt += f"- {p.name}: {p.smart_prompt}\n"

        prompt += """
【出力形式】
必ず以下のJSON形式で出力してください（他のテキストは含めない）:
{
  "comments": [
    {"persona": "narrator", "text": "コメント内容"},
    {"persona": "guesser", "text": "コメント内容"},
    ...
  ]
}

【重要】
- persona名は上記リストの名前を使用
- 各ペルソナの文字数制限を守る
- コメントは日本語で記述
- JSONの構文エラーがないように注意
- JSON以外のテキストは出力しない
"""
        return prompt

    def _extract_json(self, text: str) -> str:
        """
        LLMの応答からJSON部分を抽出し、壊れたJSONの修復を試みる

        Args:
            text: LLMの応答テキスト

        Returns:
            JSON文字列
        """
        # ```json ... ``` で囲まれている場合
        if '```json' in text:
            start = text.find('```json') + 7
            end = text.find('```', start)
            if end != -1:
                candidate = text[start:end].strip()
                return self._repair_json(candidate)

        # { ... } の部分を抽出
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            candidate = text[start:end+1]
            return self._repair_json(candidate)

        # そのまま返す
        return text

    def _repair_json(self, text: str) -> str:
        """
        LLMが出力した壊れたJSONを段階的に修復する

        修復パターン:
        1. raw_decode で末尾のゴミを無視（有効なJSONの後に余計な文字）
        2. 二重波括弧 ({{ → {, }} → })
        3. 閉じ括弧の補完（途中切れ対応）
        4. 末尾の余分な括弧を削って再構築
        """
        # まず正常なJSONかチェック
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

        # 修復1: raw_decode — 有効なJSONの後の余計な文字を無視
        try:
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(text.lstrip())
            result = json.dumps(obj, ensure_ascii=False)
            logger.info("JSON修復適用: 末尾のゴミを除去")
            return result
        except (json.JSONDecodeError, ValueError):
            pass

        # 修復2: 二重波括弧 ({{ → {, }} → })
        fixed = text.replace('{{', '{').replace('}}', '}')
        try:
            json.loads(fixed)
            logger.info("JSON修復適用: 二重波括弧を単一に変換")
            return fixed
        except json.JSONDecodeError:
            pass
        # 二重波括弧修復 + raw_decode
        try:
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(fixed.lstrip())
            result = json.dumps(obj, ensure_ascii=False)
            logger.info("JSON修復適用: 二重波括弧変換 + 末尾除去")
            return result
        except (json.JSONDecodeError, ValueError):
            pass

        # 修復3: 閉じ括弧の補完（途中切れ対応）
        completed = self._complete_brackets(text)
        if completed != text:
            try:
                json.loads(completed)
                logger.info("JSON修復適用: 括弧補完")
                return completed
            except json.JSONDecodeError:
                pass

        # 修復4: 末尾の余分な閉じ括弧を1つずつ削って試行
        trimmed = text
        while trimmed and trimmed[-1] in '}]':
            trimmed = trimmed[:-1]
            # 正しい閉じ括弧を補完して試行
            completed = self._complete_brackets(trimmed)
            try:
                json.loads(completed)
                logger.info("JSON修復適用: 末尾再構築")
                return completed
            except json.JSONDecodeError:
                continue

        # 修復できなかった場合は元のテキストを返す
        return text

    @staticmethod
    def _complete_brackets(text: str) -> str:
        """不足している閉じ括弧を補完（ネスト構造を考慮）"""
        stack = []
        in_string = False
        escape_next = False
        for ch in text:
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in '{[':
                stack.append('}' if ch == '{' else ']')
            elif ch in '}]':
                if stack and stack[-1] == ch:
                    stack.pop()
        if stack:
            return text + ''.join(reversed(stack))
        return text

    def _calculate_speed(self) -> float:
        """
        ランダムなスクロール速度を計算

        Returns:
            速度（ピクセル/秒）
        """
        base_speed = self.config.getfloat('overlay', 'scroll_speed_base', fallback=200)
        variation = self.config.getfloat('overlay', 'speed_variation', fallback=0.4)

        # ±variation の範囲でランダム化
        multiplier = random.uniform(1.0 - variation, 1.0 + variation)
        return base_speed * multiplier

    def _resolve_display_style(self, persona_name: str) -> str:
        """
        ペルソナの表示スタイルを解決

        優先順位:
        1. ペルソナ個別設定（persona_manager.display_style）
        2. グローバルデフォルト（[overlay] display_style）
        3. "scroll"（フォールバック）

        Args:
            persona_name: ペルソナ名

        Returns:
            表示スタイル文字列: "scroll", "toast", "chatlog"
        """
        valid_styles = ('scroll', 'toast', 'chatlog')

        # ペルソナ個別設定を確認
        try:
            persona_config = self.persona_manager.get_persona(persona_name)
            if persona_config.display_style in valid_styles:
                return persona_config.display_style
        except KeyError:
            pass

        # グローバルデフォルト
        global_style = self.config.get('overlay', 'display_style', fallback='scroll')
        if global_style in valid_styles:
            return global_style

        return 'scroll'
