"""
llama-server.exe をサブプロセスとして起動・管理するヘルパー。

config.ini の [llama_server] セクションを読んで自動起動・ヘルスチェック・終了処理を行う。
"""

from __future__ import annotations

import atexit
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)


class LlamaServerManager:
    """llama-server.exe を Popen で起動・停止・ヘルスチェックする。"""

    def __init__(
        self,
        executable_path: Path,
        model_path: Path,
        mmproj_path: Optional[Path],
        port: int = 8080,
        n_gpu_layers: int = -1,
        ctx_size: int = 8192,
        extra_args: str = "",
        disable_thinking: bool = False,
    ) -> None:
        self.executable_path = Path(executable_path)
        self.model_path = Path(model_path)
        self.mmproj_path = Path(mmproj_path) if mmproj_path else None
        self.port = port
        self.n_gpu_layers = n_gpu_layers
        self.ctx_size = ctx_size
        self.extra_args = extra_args.strip()
        self.disable_thinking = disable_thinking
        self.process: Optional[subprocess.Popen] = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def _build_args(self) -> List[str]:
        args: List[str] = [
            str(self.executable_path),
            "-m", str(self.model_path),
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "-ngl", str(self.n_gpu_layers),
            "-c", str(self.ctx_size),
        ]
        if self.mmproj_path:
            args.extend(["--mmproj", str(self.mmproj_path)])
        if self.disable_thinking:
            # Qwen3 / DeepSeek-R1 等の reasoning を完全停止
            # --reasoning off: chat template の thinking ブロックを無効化
            # --reasoning-budget 0: 万一思考トークンが出ても即座に打ち切り
            args.extend(["--reasoning", "off", "--reasoning-budget", "0"])
        if self.extra_args:
            args.extend(self.extra_args.split())
        return args

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self) -> None:
        """llama-server.exe を起動。既に動いていれば何もしない。"""
        if self.is_running():
            logger.info("llama-server is already running, skip start")
            return

        if not self.executable_path.exists():
            raise FileNotFoundError(f"llama-server.exe not found: {self.executable_path}")
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model file not found: {self.model_path}\n"
                f"Hint: Run setup_model.bat first to download the model."
            )
        if self.mmproj_path and not self.mmproj_path.exists():
            raise FileNotFoundError(
                f"mmproj file not found: {self.mmproj_path}\n"
                f"Hint: Run setup_model.bat first to download the mmproj."
            )

        cmd = self._build_args()
        logger.info("Starting llama-server: %s", " ".join(cmd))

        # CREATE_NO_WINDOW = 0x08000000 (Windows でコンソール窓を出さない)
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        self.process = subprocess.Popen(
            cmd,
            cwd=str(self.executable_path.parent),
            creationflags=creation_flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # atexit と SIGTERM で確実に止める
        atexit.register(self.stop)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, lambda *_: self.stop())

    def wait_until_ready(self, timeout: float = 180.0, poll_interval: float = 1.0) -> bool:
        """サーバが /v1/models に応答するまで待機。"""
        if not self.is_running():
            logger.warning("llama-server is not running, cannot wait")
            return False

        deadline = time.time() + timeout
        url = f"{self.base_url}/models"
        last_err: Optional[str] = None
        while time.time() < deadline:
            if not self.is_running():
                logger.error("llama-server crashed before becoming ready (last error: %s)", last_err)
                return False
            try:
                resp = requests.get(url, timeout=2.0)
                if resp.status_code == 200:
                    elapsed = timeout - (deadline - time.time())
                    logger.info("llama-server ready after %.1fs", elapsed)
                    return True
                last_err = f"HTTP {resp.status_code}"
            except requests.RequestException as e:
                last_err = str(e)
            time.sleep(poll_interval)

        logger.error("llama-server did not become ready within %.0fs (last error: %s)", timeout, last_err)
        return False

    def stop(self) -> None:
        """サーバを停止。既に止まっていれば何もしない。"""
        if not self.is_running():
            return
        assert self.process is not None
        logger.info("Stopping llama-server (pid=%s)", self.process.pid)
        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("llama-server did not exit in 5s, killing")
                self.process.kill()
                self.process.wait(timeout=3)
        except Exception as e:
            logger.error("Failed to stop llama-server: %s", e)
        finally:
            self.process = None
