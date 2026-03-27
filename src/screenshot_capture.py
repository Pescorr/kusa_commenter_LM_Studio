"""
Screenshot Capture Thread for RPG Logger v3
Periodically captures screenshots and queues them for LLM processing
"""

import os
import time
import threading
import queue
import logging
from datetime import datetime
import mss

logger = logging.getLogger(__name__)


class ScreenshotCaptureThread(threading.Thread):
    """
    Daemon thread that captures screenshots at regular intervals with idle detection
    """

    def __init__(
        self,
        interval=10.0,
        screenshot_queue=None,
        temp_dir="screenshots_temp",
        image_format="png",
        max_temp_files=5,
        image_quality=85,
        idle_threshold=15.0,
        idle_interval=60.0,
        max_interval=300.0,
        idle_backoff_factor=1.5,
        get_last_activity_time=None,
        target_monitor=1,
    ):
        """
        Initialize screenshot capture thread

        Args:
            interval: Seconds between captures when active
            screenshot_queue: Queue to send screenshot paths to
            temp_dir: Directory for temporary screenshot storage
            image_format: File format (png or jpeg)
            max_temp_files: Maximum number of temp files to keep
            image_quality: JPEG quality (1-100, only for JPEG format)
            idle_threshold: Seconds of inactivity before considered idle
            idle_interval: Base interval when idle
            max_interval: Maximum interval during extended idle
            idle_backoff_factor: Exponential backoff multiplier
            get_last_activity_time: Function that returns last activity timestamp
            target_monitor: Monitor number to capture (1=primary, 2=secondary, ...)
        """
        super().__init__(daemon=True)
        self.active_interval = interval
        self.screenshot_queue = screenshot_queue
        self.temp_dir = temp_dir
        self.image_format = image_format.lower()
        self.max_temp_files = max_temp_files
        self.image_quality = image_quality
        self.target_monitor = target_monitor

        # Idle detection parameters
        self.idle_threshold = idle_threshold
        self.idle_interval = idle_interval
        self.max_interval = max_interval
        self.idle_backoff_factor = idle_backoff_factor
        self.get_last_activity_time = get_last_activity_time

        # Idle state tracking
        self.idle_level = 0

        self.stop_event = threading.Event()

        # Ensure temp directory exists
        os.makedirs(self.temp_dir, exist_ok=True)

        print(f"[Screenshot] Initialized (active={interval}s, idle={idle_interval}s, format={image_format}, monitor={target_monitor})")

    def run(self):
        """Main loop: capture screenshots periodically with adaptive intervals"""
        print("[Screenshot] Thread started")

        while not self.stop_event.is_set():
            try:
                # Capture screenshot
                screenshot_path = self._capture()

                if screenshot_path and self.screenshot_queue:
                    # Send to queue for LLM processing
                    try:
                        self.screenshot_queue.put(
                            {
                                "timestamp": time.time(),
                                "path": screenshot_path,
                            },
                            timeout=1,
                        )
                    except queue.Full:
                        print("[Screenshot] Warning: Queue full, skipping frame")

                # Clean up old files
                self._cleanup_old_files()

            except Exception as e:
                print(f"[Screenshot] Error in capture loop: {e}")

            # Calculate next interval based on idle detection
            next_interval = self._compute_next_interval()

            # Wait for next interval
            self.stop_event.wait(next_interval)

        print("[Screenshot] Thread stopped")

    def stop(self):
        """Signal the thread to stop"""
        self.stop_event.set()

    def _compute_next_interval(self) -> float:
        """
        Calculate next capture interval based on idle detection

        Returns:
            Next interval in seconds (adaptive based on activity)
        """
        # If no activity tracker provided, use active interval
        if self.get_last_activity_time is None:
            return self.active_interval

        now = time.time()
        last_activity = self.get_last_activity_time()
        idle_for = now - last_activity

        # Check if user is active (within idle threshold)
        if idle_for < self.idle_threshold:
            # Reset idle level and return active interval
            self.idle_level = 0
            return self.active_interval

        # User is idle, increase idle level and calculate backoff interval
        self.idle_level += 1
        interval = self.idle_interval * (self.idle_backoff_factor ** max(0, self.idle_level - 1))

        # Cap at maximum interval
        return min(self.max_interval, interval)

    def _capture(self) -> str:
        """
        Capture screenshot of target monitor

        Returns:
            Path to saved screenshot file, or None if failed
        """
        try:
            # Use mss for fast screenshot capture
            with mss.mss() as sct:
                # モニターインデックス検証（main.pyで解決済みだが安全のためクランプ）
                num_monitors = len(sct.monitors) - 1
                monitor_index = max(1, min(self.target_monitor, num_monitors))
                if monitor_index != self.target_monitor:
                    logger.warning(
                        f"Monitor index {self.target_monitor} out of range "
                        f"(1-{num_monitors}), clamped to {monitor_index}"
                    )

                # Capture target monitor
                monitor = sct.monitors[monitor_index]
                screenshot = sct.grab(monitor)

                # Generate filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                ext = "png" if self.image_format == "png" else "jpg"
                filename = f"screenshot_{timestamp}.{ext}"
                filepath = os.path.join(self.temp_dir, filename)

                # Save screenshot based on format
                if self.image_format == "png":
                    # Use mss built-in PNG saver
                    mss.tools.to_png(screenshot.rgb, screenshot.size, output=filepath)
                else:
                    # Use PIL for JPEG with quality control
                    from PIL import Image
                    img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
                    img.save(filepath, format="JPEG", quality=self.image_quality)

                return filepath

        except Exception as e:
            logger.error(f"Capture failed: {e}")
            return None

    def _cleanup_old_files(self):
        """
        Delete old screenshot files, keeping only the most recent N files

        BUG-001修正: FileNotFoundErrorを明示的に処理
        """
        try:
            # BUG-001修正: ディレクトリが存在しない場合は作成
            if not os.path.exists(self.temp_dir):
                os.makedirs(self.temp_dir, exist_ok=True)
                return

            # Get all screenshot files in temp directory
            files = []
            for f in os.listdir(self.temp_dir):
                if f.startswith("screenshot_") and (f.endswith(".png") or f.endswith(".jpg")):
                    filepath = os.path.join(self.temp_dir, f)
                    try:
                        mtime = os.path.getmtime(filepath)
                        files.append((filepath, mtime))
                    except FileNotFoundError:
                        # BUG-001修正: ファイルが削除された（レースコンディション）
                        print(f"[Screenshot] File disappeared during cleanup: {filepath}")
                        continue
                    except OSError as e:
                        print(f"[Screenshot] Cannot access file {filepath}: {e}")
                        continue

            # Sort by modification time (newest first)
            files.sort(key=lambda x: x[1], reverse=True)

            # Delete old files (keep only max_temp_files)
            for filepath, _ in files[self.max_temp_files:]:
                try:
                    os.remove(filepath)
                    print(f"[Screenshot] Deleted old file: {filepath}")
                except FileNotFoundError:
                    # BUG-001修正: 既に削除されている
                    pass
                except OSError as e:
                    print(f"[Screenshot] Failed to delete {filepath}: {e}")

        except Exception as e:
            print(f"[Screenshot] Unexpected cleanup error: {e}")


class LLMWorkerThread(threading.Thread):
    """
    Worker thread that processes screenshots with LLM
    """

    def __init__(
        self,
        screenshot_queue=None,
        action_log_queue=None,
        llm_client=None,
        username="User",
        storage_mode="temp",
        comment_generator=None,
        overlay=None,
    ):
        """
        Initialize LLM worker thread

        Args:
            screenshot_queue: Queue to receive screenshot paths from
            action_log_queue: Queue to send generated logs to (旧システム、互換性のため残す)
            llm_client: LMStudioClient instance
            username: User's name for personalized logs
            storage_mode: 'temp' (delete after processing) or 'archive' (keep)
            comment_generator: CommentGenerator instance (Phase 2用)
            overlay: CommentOverlay instance
        """
        super().__init__(daemon=True)
        self.screenshot_queue = screenshot_queue
        self.action_log_queue = action_log_queue
        self.llm_client = llm_client
        self.username = username
        self.storage_mode = storage_mode
        self.comment_generator = comment_generator
        self.overlay = overlay

        self.stop_event = threading.Event()

        print(f"[LLM Worker] Initialized (username={username}, storage={storage_mode})")

    def run(self):
        """Main loop: process screenshots from queue"""
        print("[LLM Worker] Thread started")

        while not self.stop_event.is_set():
            try:
                # Get screenshot from queue (block with timeout)
                item = self.screenshot_queue.get(timeout=1)

                # Check if LLM API is healthy
                if not self.llm_client.is_api_healthy():
                    print("[LLM Worker] API unhealthy, skipping frame")
                    continue

                # Phase 2: CommentGeneratorを使用してコメント生成
                if self.comment_generator and self.overlay:
                    # CommentContextを構築
                    from comment_data import CommentContext
                    context = CommentContext(
                        screenshot_path=item["path"],
                        timestamp=item["timestamp"]
                    )

                    # コメント生成
                    comments = self.comment_generator.generate(context)

                    # 各コメントをオーバーレイに送信
                    for comment in comments:
                        self.overlay.add_comment(comment)

                    print(f"[LLM Worker] Generated {len(comments)} comments")

                else:
                    # 旧システム: generate_action_log を使用（互換性のため）
                    action_log = self.llm_client.generate_action_log(
                        item["path"],
                        self.username,
                    )

                    # Send result to action log queue
                    if self.action_log_queue:
                        try:
                            self.action_log_queue.put(
                                {
                                    "timestamp": item["timestamp"],
                                    "log": action_log,
                                },
                                timeout=1,
                            )
                        except queue.Full:
                            print("[LLM Worker] Warning: Action log queue full")

                # Delete screenshot if temp mode
                if self.storage_mode == "temp":
                    try:
                        os.remove(item["path"])
                    except Exception as e:
                        print(f"[LLM Worker] Failed to delete temp file: {e}")

            except queue.Empty:
                # No screenshots in queue, continue waiting
                continue

            except Exception as e:
                print(f"[LLM Worker] Error processing screenshot: {e}")

        print("[LLM Worker] Thread stopped")

    def stop(self):
        """Signal the thread to stop"""
        self.stop_event.set()
