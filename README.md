# Screen Commentator (Windows)

AI が画面を見て、スクロールコメントを自動生成するオーバーレイアプリケーションです。
ローカル LLM（LM Studio）を使って画面のスクリーンショットを分析し、
5種類のペルソナが弾幕風のコメントを画面上にリアルタイム表示します。

**誰かがコメントしてくれている感覚で使える、日常 AI アシスタント。**

## 特徴

- **透過オーバーレイ**: 画面最前面にクリックスルーでコメントをスクロール表示
- **5種類のペルソナ**: Standard（客観的）、Meme（予測）、Critic（批評）、Instructor（助言）、Barrage（翻訳・要約）
- **完全ローカル**: LM Studio のローカル LLM を使用、API 費用ゼロ
- **2つのモード**: Smart Mode（1回の API で JSON 生成）と Basic Mode（確実）
- **カスタマイズ可能**: 色・サイズ・速度・ペルソナ配分を config.ini で調整

## 前提条件

1. **Python 3.8以上**
2. **LM Studio** — [lmstudio.ai](https://lmstudio.ai/) からダウンロード
   - Vision モデル（画像認識対応）が必要
   - 推奨: `qwen2.5-vl:3b`, `llava`, `bakllava` など

### 推奨環境

- Windows 10/11
- メモリ: 8GB以上（LLM 実行のため）
- GPU: 推奨（LLM の高速化）

## セットアップ

```bash
pip install -r requirements.txt
```

LM Studio を起動し、Vision モデルをロードしてローカルサーバーを起動してください（デフォルト: `http://localhost:1234`）。

## 使い方

```bash
python src/main.py
```

終了はシステムトレイアイコンの「終了」から。

## 設定

`config.ini` を編集して各種設定を変更できます。

### オーバーレイ設定

```ini
[overlay]
num_lanes = 9              # レーン数
scroll_speed_base = 400    # スクロール速度（px/秒）
font_family = MS Gothic    # フォント
enable_stroke = true       # 文字の縁取り
```

### パイプライン設定

```ini
[pipeline]
mode = smart               # smart / basic
```

### ペルソナ配分

```ini
[personas]
standard_weight = 20
meme_weight = 10
critic_weight = 25
instructor_weight = 25
barrage_weight = 20
```

### ディスプレイ設定

```ini
[display]
capture_monitor = primary   # スクリーンショット撮影対象
overlay_monitor = primary   # コメント表示対象
```

## ペルソナ一覧

| ペルソナ | 特徴 | 色 |
|---------|------|-----|
| **Standard** | 客観的な観察者。淡々と状況を説明 | 白 |
| **Meme** | 入力予測・固有名詞特定 | 緑 |
| **Critic** | 厳しい批評家。ツッコミ担当 | 赤 |
| **Instructor** | 親切な指導者。アドバイス提供 | シアン |
| **Barrage** | 翻訳・計算・要約bot | 黄 |

## ファイル構成

```
├── config.ini              # 設定ファイル
├── requirements.txt        # 依存パッケージ
├── screen_commentator.spec # PyInstaller ビルド設定
├── build.bat               # ビルドスクリプト
├── test_components.py      # コンポーネントテスト
└── src/
    ├── main.py             # エントリーポイント
    ├── comment_overlay.py  # オーバーレイシステム
    ├── comment_data.py     # データ構造定義
    ├── comment_generator.py # コメント生成
    ├── persona_manager.py  # ペルソナ管理
    ├── llm_client.py       # LM Studio API クライアント
    ├── screenshot_capture.py # スクリーンショット撮影
    ├── config_utils.py     # 設定ユーティリティ
    └── monitor_utils.py    # モニター解決
```

## 注意事項

- **配信での利用は非推奨です。** 画面キャプチャの内容がコメントとして表示されるため、個人情報や機密情報が映り込む可能性があります。
- ローカル LLM の性能に依存します。モデルが重い場合はコメント生成に時間がかかります。
- `exclude_overlay_from_capture = true`（デフォルト）でオーバーレイ自体がスクリーンショットに映り込むのを防げます。

## ビルド（EXE化）

```bash
python -m PyInstaller screen_commentator.spec --clean --noconfirm
```

出力先: `dist/ScreenCommentator/`

## ライセンス

MIT License — 詳細は [LICENSE](LICENSE) を参照。

## 謝辞

- Inspired by [@r1cA18/screen-commentator](https://github.com/r1cA18/screen-commentator) (macOS版, MIT License)
- [LM Studio](https://lmstudio.ai/)
