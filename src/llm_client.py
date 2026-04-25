"""
LM Studio API Client for RPG Logger v3
Handles all LLM interactions: screenshot analysis and summary generation
"""

import os
import base64
import time
import requests
from PIL import Image
from io import BytesIO


class LMStudioClient:
    """Client for interacting with LM Studio's local API"""

    def __init__(
        self,
        base_url="http://localhost:1234/v1",
        vision_model_name="",
        summary_model_name="",
        timeout=30,
        max_retries=3,
        temperature=0.7,
        action_log_max_tokens=100,
        summary_max_tokens=500,
        action_log_system_prompt="",
        summary_system_prompt="",
        max_width=1280,
        image_quality=85,
        action_log_fallback_system_prompt="スクリーンショットから{username}の現在の行動を1行で記録してください。",
        action_log_user_prompt="スクリーンショットを見て、{username}は今何をしていますか？",
        action_log_fallback_message="{username} は 何かをしている。",
        summary_fallback_system_prompt="30分間の行動ログを要約し、{username}の記録として出力してください。",
        summary_user_prompt="以下は{username}の30分間の行動ログです。これを記録として要約してください。",
        summary_fallback_message="{username}の30分間の記録（要約生成に失敗しました）",
        smart_mode_max_tokens=300,
        basic_mode_max_tokens=100,
        api_error_cooldown_sec=300,
        api_token="",
        api_mode="openai",
        mcp_integrations="",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.api_mode = api_mode  # "openai" or "lmstudio"
        self.mcp_integrations = [s.strip() for s in mcp_integrations.split(",") if s.strip()] if mcp_integrations else []
        self.vision_model_name = vision_model_name  # Model for screenshot analysis (must support vision)
        self.summary_model_name = summary_model_name  # Model for text-only summary generation
        self._resolved_model_name = None  # lmstudioモード用: local-model解決後のキャッシュ
        self.timeout = timeout
        self.max_retries = max_retries
        self.temperature = temperature
        self.action_log_max_tokens = action_log_max_tokens
        self.summary_max_tokens = summary_max_tokens
        self.action_log_system_prompt = action_log_system_prompt
        self.summary_system_prompt = summary_system_prompt
        self.max_width = max_width
        self.image_quality = image_quality

        # Prompt templates
        self.action_log_fallback_system_prompt = action_log_fallback_system_prompt
        self.action_log_user_prompt = action_log_user_prompt
        self.action_log_fallback_message = action_log_fallback_message
        self.summary_fallback_system_prompt = summary_fallback_system_prompt
        self.summary_user_prompt = summary_user_prompt
        self.summary_fallback_message = summary_fallback_message

        # Track API health
        self.api_available = True
        self.last_error_time = 0
        self.consecutive_errors = 0

        # Token limits and cooldown settings
        self.smart_mode_max_tokens = smart_mode_max_tokens
        self.basic_mode_max_tokens = basic_mode_max_tokens
        self.api_error_cooldown_sec = api_error_cooldown_sec

    def _remove_thinking_tags(self, text: str) -> str:
        """
        推論機能付きモデルからのレスポンスに含まれる<thinking>...</thinking>タグを除去
        
        Args:
            text: 処理対象のテキスト
            
        Returns:
            タグ除去後のテキスト
        """
        import re
        # <thinking> と </thinking> の間の内容を除去（大文字小文字区別なし）
        return re.sub(r'<thinking>.*?</thinking>\s*', '', text, flags=re.DOTALL | re.IGNORECASE)

    def encode_image_base64(self, image_path: str) -> str:
        """
        Read image file, optionally resize, and encode to base64

        Args:
            image_path: Path to image file

        Returns:
            Base64-encoded image string
        """
        try:
            img = Image.open(image_path)

            # Resize if too large (save bandwidth and processing time)
            if self.max_width > 0 and img.width > self.max_width:
                ratio = self.max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((self.max_width, new_height), Image.Resampling.LANCZOS)

            # Convert to RGB if needed (remove alpha channel)
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = background

            # Encode to base64
            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=self.image_quality)
            img_bytes = buffered.getvalue()
            img_base64 = base64.b64encode(img_bytes).decode("utf-8")

            return img_base64

        except Exception as e:
            print(f"[LLM Client] Error encoding image: {e}")
            raise

    def generate_action_log(self, screenshot_path: str, username: str) -> str:
        """
        Analyze screenshot and generate a single-line Dragon Quest-style action log

        Args:
            screenshot_path: Path to screenshot file
            username: User's name for personalized messages

        Returns:
            Single-line action log (e.g., "Pescorr は VS Code でコードを書いている。")
        """
        try:
            # Encode image
            img_base64 = self.encode_image_base64(screenshot_path)

            # Prepare messages
            messages = [
                {
                    "role": "system",
                    "content": self.action_log_system_prompt or self.action_log_fallback_system_prompt.format(username=username)
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": self.action_log_user_prompt.format(username=username)
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_base64}"
                            }
                        }
                    ]
                }
            ]

            # Call API with vision model
            response_text = self._call_api(messages, self.action_log_max_tokens, model_name=self.vision_model_name)

            # Remove thinking tags and clean up response
            log = self._remove_thinking_tags(response_text).strip().strip('"').strip("'").replace("\n", " ")

            # Reset error tracking on success
            self.consecutive_errors = 0
            self.api_available = True

            return log

        except Exception as e:
            print(f"[LLM Client] Error generating action log: {e}")
            self.consecutive_errors += 1
            self.last_error_time = time.time()

            # Return fallback message
            return self.action_log_fallback_message.format(username=username)

    def generate_summary(self, log_text: str, username: str) -> str:
        """
        Generate a 30-minute summary from action logs

        Args:
            log_text: Full text of 30-minute action log file
            username: User's name for personalized summary

        Returns:
            Dragon Quest-style summary
        """
        try:
            messages = [
                {
                    "role": "system",
                    "content": self.summary_system_prompt or self.summary_fallback_system_prompt.format(username=username)
                },
                {
                    "role": "user",
                    "content": self.summary_user_prompt.format(username=username) + f"\n\n{log_text}"
                }
            ]

            # Call API with summary model (text-only, no vision required)
            response_text = self._call_api(messages, self.summary_max_tokens, model_name=self.summary_model_name)

            # Remove thinking tags and clean up response
            self.consecutive_errors = 0
            self.api_available = True

            return self._remove_thinking_tags(response_text).strip()

        except Exception as e:
            print(f"[LLM Client] Error generating summary: {e}")
            self.consecutive_errors += 1
            self.last_error_time = time.time()

            # Return fallback summary
            return self.summary_fallback_message.format(username=username)

    def _resolve_model_name(self, model_name: str) -> str:
        """
        lmstudioモード用: local-model等の汎用名を実際のモデルIDに解決

        /api/v1/chatはlocal-modelを受け付けないため、
        /api/v1/modelsから現在ロード済みのモデルIDを取得して使用する
        """
        if model_name and model_name != "local-model":
            return model_name

        # キャッシュがあればそれを使う
        if self._resolved_model_name:
            return self._resolved_model_name

        try:
            root_url = self.base_url
            if root_url.endswith("/v1"):
                root_url = root_url[:-3]

            headers = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            # /api/v1/models から loaded_instances があるモデルを探す
            resp = requests.get(f"{root_url}/api/v1/models", headers=headers, timeout=10)
            resp.raise_for_status()
            models = resp.json().get("models", [])

            for model in models:
                loaded = model.get("loaded_instances", 0)
                if isinstance(loaded, list):
                    loaded = len(loaded)
                if loaded > 0:
                    self._resolved_model_name = model["key"]
                    print(f"[LLM Client] Model resolved: local-model → {self._resolved_model_name} (loaded)")
                    return self._resolved_model_name

            # ロード済みモデルがない場合、/v1/modelsの最初のモデルにフォールバック
            resp2 = requests.get(f"{self.base_url}/models", headers=headers, timeout=10)
            resp2.raise_for_status()
            openai_models = resp2.json().get("data", [])
            if openai_models:
                self._resolved_model_name = openai_models[0]["id"]
                print(f"[LLM Client] Model resolved: local-model → {self._resolved_model_name} (fallback)")
                return self._resolved_model_name

        except Exception as e:
            print(f"[LLM Client] Failed to resolve model name: {e}")

        # フォールバック: そのまま返す
        return model_name

    def _build_request(self, messages: list, max_tokens: int, model_name: str = None):
        """
        APIモードに応じてURL・ペイロード・ヘッダーを構築

        Returns:
            (url, payload, headers) のタプル
        """
        actual_model = model_name or self.vision_model_name
        headers = {"Content-Type": "application/json"}

        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        if self.api_mode == "lmstudio":
            # local-modelを実際のモデル名に解決
            actual_model = self._resolve_model_name(actual_model)
            # LM Studio独自API: /api/v1/chat
            root_url = self.base_url
            if root_url.endswith("/v1"):
                root_url = root_url[:-3]
            url = f"{root_url}/api/v1/chat"

            # OpenAI messages形式 → LM Studio input形式に変換
            input_blocks = []
            for msg in messages:
                if msg["role"] == "system":
                    # systemプロンプトはテキストブロックとして先頭に追加
                    input_blocks.append({"type": "text", "content": f"[System] {msg['content']}"})
                elif msg["role"] == "user":
                    content = msg["content"]
                    if isinstance(content, list):
                        # マルチモーダル: text/image_url → text/image に変換
                        for part in content:
                            if part.get("type") == "text":
                                input_blocks.append({"type": "text", "content": part["text"]})
                            elif part.get("type") == "image_url":
                                data_url = part["image_url"]["url"]
                                input_blocks.append({"type": "image", "data_url": data_url})
                    else:
                        input_blocks.append({"type": "text", "content": content})

            payload = {
                "model": actual_model,
                "input": input_blocks,
            }

            if self.mcp_integrations:
                payload["integrations"] = self.mcp_integrations

        else:
            # OpenAI互換API: /v1/chat/completions
            url = f"{self.base_url}/chat/completions"
            payload = {
                "model": actual_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": self.temperature,
            }

        return url, payload, headers

    def _parse_response(self, data: dict) -> str:
        """
        APIモードに応じてレスポンスからテキストを抽出
        """
        if self.api_mode == "lmstudio":
            # LM Studio独自API形式: {"output": [{"type": "message", "content": "..."}, ...]}
            if "output" in data:
                for item in data["output"]:
                    if item.get("type") == "message" and "content" in item:
                        return item["content"]
                raise ValueError("No message content in LM Studio API response")
            # フォールバック: OpenAI形式もチェック
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            raise ValueError("Invalid response format from LM Studio API")
        else:
            # OpenAI互換形式
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            raise ValueError("Invalid response format from LM Studio API")

    def _call_api(self, messages: list, max_tokens: int, model_name: str = None) -> str:
        """
        Internal method to call LM Studio API with retry logic

        Args:
            messages: Message list for chat completion
            max_tokens: Maximum tokens to generate
            model_name: Model to use (defaults to vision_model_name if not specified)

        Returns:
            Response text

        Raises:
            Exception if all retries fail
        """
        url, payload, headers = self._build_request(messages, max_tokens, model_name)

        last_exception = None

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )

                # Check response
                response.raise_for_status()

                # Parse response
                data = response.json()
                return self._parse_response(data)

            except requests.exceptions.ConnectionError as e:
                last_exception = e
                print(f"[LLM Client] Connection error (attempt {attempt + 1}/{self.max_retries}): {e}")
                self.api_available = False

                # BUG-003修正: Exponential backoff with max 30s cap
                if attempt < self.max_retries - 1:
                    wait_time = min(2 ** attempt, 30)
                    time.sleep(wait_time)

            except requests.exceptions.Timeout as e:
                last_exception = e
                print(f"[LLM Client] Timeout (attempt {attempt + 1}/{self.max_retries}): {e}")

                # BUG-003修正: Exponential backoff with max 30s cap
                if attempt < self.max_retries - 1:
                    wait_time = min(2 ** attempt, 30)
                    time.sleep(wait_time)

            except Exception as e:
                last_exception = e
                print(f"[LLM Client] API error (attempt {attempt + 1}/{self.max_retries}): {e}")

                # BUG-003修正: Exponential backoff with max 30s cap
                if attempt < self.max_retries - 1:
                    wait_time = min(2 ** attempt, 30)
                    time.sleep(wait_time)

        # All retries failed
        self.api_available = False
        raise last_exception

    def is_api_healthy(self) -> bool:
        """
        Check if API is likely to be available

        Returns:
            True if API seems healthy, False otherwise
        """
        # If recent errors, assume unhealthy for a while
        if self.consecutive_errors >= 3:
            time_since_error = time.time() - self.last_error_time
            # Wait configured cooldown period before retrying after multiple failures
            if time_since_error < self.api_error_cooldown_sec:
                return False

        return self.api_available

    def generate_comments_smart_mode(self, screenshot_path: str, system_prompt: str) -> str:
        """
        Smart Mode用: JSON形式で複数コメントを取得

        Args:
            screenshot_path: スクリーンショット画像のパス
            system_prompt: Smart Mode用のシステムプロンプト

        Returns:
            JSON文字列（例: '{"comments": [{"persona": "guesser", "text": "草"}, ...]}'）
        """
        try:
            # Encode image
            img_base64 = self.encode_image_base64(screenshot_path)

            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "スクリーンショットを見て、指定されたペルソナでコメントを生成してください。"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_base64}"
                            }
                        }
                    ]
                }
            ]

            # Call API with vision model (複数コメント分のトークン確保)
            response_text = self._call_api(messages, max_tokens=self.smart_mode_max_tokens, model_name=self.vision_model_name)

            self.consecutive_errors = 0
            self.api_available = True

            return self._remove_thinking_tags(response_text)

        except Exception as e:
            self.consecutive_errors += 1
            self.last_error_time = time.time()
            self.api_available = False
            print(f"[LLM Client] Smart Mode error: {e}")
            raise

    def generate_comment_single_persona(self, screenshot_path: str, system_prompt: str, max_chars: int) -> str:
        """
        Basic Mode用: 単一ペルソナのコメントを取得

        Args:
            screenshot_path: スクリーンショット画像のパス
            system_prompt: ペルソナ固有のシステムプロンプト
            max_chars: 最大文字数

        Returns:
            プレーンテキストのコメント（例: "草www"）
        """
        try:
            # Encode image
            img_base64 = self.encode_image_base64(screenshot_path)

            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"スクリーンショットを見て、{max_chars}文字以内でコメントしてください。"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_base64}"
                            }
                        }
                    ]
                }
            ]

            # Call API with vision model (単一コメントなので少なめ)
            response_text = self._call_api(messages, max_tokens=self.basic_mode_max_tokens, model_name=self.vision_model_name)

            # Reset error tracking on success
            self.consecutive_errors = 0
            self.api_available = True

            return self._remove_thinking_tags(response_text).strip().strip('"').strip("'")[:max_chars]

        except Exception as e:
            self.consecutive_errors += 1
            self.last_error_time = time.time()
            self.api_available = False
            print(f"[LLM Client] Basic Mode error: {e}")
            raise
