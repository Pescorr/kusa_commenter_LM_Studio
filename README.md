# kusa_commenter

AI が画面を見て、スクロールコメントを自動生成するオーバーレイアプリケーションです。
ローカル LLM（llama.cpp 同梱）が画面のスクリーンショットを分析し、
5 種類のペルソナが弾幕風のコメントを画面上にリアルタイム表示します。

**誰かがコメントしてくれている感覚で使える、日常 AI アシスタント。**

## 📦 ダウンロード（v1.1.0：llama.cpp 同梱版）

ビルド済み exe を配布しています（Windows 64bit）。
👉 **[最新リリース](https://github.com/Pescorr/kusa_commenter_LM_Studio/releases/latest)**

LM Studio など他ツール一切不要。3 ステップで動きます：

1. ZIP を解凍
2. `setup_model.bat` を実行（初回のみ、HuggingFace から Vision モデル ~6 GB を DL）
3. `ScreenCommentator.exe` を起動

> v1.0.0（LM Studio 連携版）も併用可能。詳細は[リリース一覧](https://github.com/Pescorr/kusa_commenter_LM_Studio/releases)。

## 特徴

- **透過オーバーレイ**: 画面最前面にクリックスルーでコメントをスクロール表示
- **5 種類のペルソナ**: Standard（客観的）／Meme（予測）／Critic（批評）／Instructor（助言）／Barrage（翻訳・要約）
- **完全ローカル**: llama.cpp + Qwen3.5-9B Vision、API 課金ゼロ
- **Smart / Basic 2 モード**: Smart Mode（1 回の API で JSON 生成）と Basic Mode（確実）
- **カスタマイズ可能**: 色・サイズ・速度・ペルソナ配分を `config.ini` で調整

## 動作環境

- Windows 10/11 (64bit)
- メモリ 16 GB 以上推奨（Q4_K_M で約 6 GB を使用）
- GPU: NVIDIA + CUDA 推奨（Qwen3.5-9B Q4_K_M を VRAM ~7 GB に載せる）。CPU only でも動作可。
- ストレージ: 8 GB 以上の空き（モデル含む）

## 使われているモデル

| 種別 | モデル | 配布元 | サイズ |
|---|---|---|---|
| LLM | Qwen3.5-9B-Q4_K_M | [unsloth/Qwen3.5-9B-GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF) | 5.3 GB |
| Vision Projection | mmproj-BF16 | 同上 | 879 MB |
| 推論エンジン | llama.cpp（同梱） | [ggerganov/llama.cpp](https://github.com/ggerganov/llama.cpp) | — |

ライセンス：モデル Apache 2.0 / llama.cpp MIT。商用利用可。

## ソースから実行する場合（開発者向け）

```bash
pip install -r requirements.txt
# llama-server.exe + Vision モデルを別途用意して config.ini を調整
python src/main.py
```

詳細は [config.ini](config.ini) と [src/llama_server_manager.py](src/llama_server_manager.py) を参照。

## 設定（config.ini）

主要セクション：

```ini
[llama_server]              # 同梱 llama-server を自動起動
auto_start = true
model_path = models/Qwen3.5-9B-Q4_K_M.gguf
mmproj_path = models/mmproj-BF16.gguf
n_gpu_layers = -1           # -1=全部GPU、0=CPU only

[overlay]
num_lanes = 9               # レーン数
scroll_speed_base = 400     # スクロール速度（px/秒）
font_family = MS Gothic

[pipeline]
mode = smart                # smart / basic

[personas]
narrator_weight = 20
guesser_weight = 10
critic_weight = 25
instructor_weight = 25
analyzer_weight = 20

[display]
capture_monitor = primary   # スクリーンショット撮影対象
overlay_monitor = primary   # コメント表示対象
```

## ペルソナ一覧

| ペルソナ | 特徴 | 色 |
|---|---|---|
| **Standard** | 客観的な観察者。淡々と状況を説明 | 白 |
| **Meme** | 入力予測・固有名詞特定 | 緑 |
| **Critic** | 厳しい批評家。ツッコミ担当 | 赤 |
| **Instructor** | 親切な指導者。アドバイス提供 | シアン |
| **Barrage** | 翻訳・計算・要約 bot | 黄 |

## 注意事項

- **配信での利用は非推奨。** スクリーンショットの内容がコメントに反映されるため、個人情報や機密情報の映り込みに注意。
- 初回起動時は llama-server のロードに数十秒〜数分かかります（モデルサイズに依存）。
- `exclude_overlay_from_capture = true`（既定）で、オーバーレイ自体がスクリーンショットに映り込むのを防げます。

## ビルド（自分で exe を作る場合）

```bash
python -m PyInstaller screen_commentator.spec --clean --noconfirm
```

`R:/AI/LLM_Servers/llama_server/` を spec の `LLAMA_SRC` に合わせて配置してください。

## ライセンス

MIT License — 詳細は [LICENSE](LICENSE) を参照。

## 謝辞

- Inspired by [@r1cA18/screen-commentator](https://github.com/r1cA18/screen-commentator)（macOS 版、MIT）
- [llama.cpp](https://github.com/ggerganov/llama.cpp)
- [unsloth/Qwen3.5-9B-GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF)
