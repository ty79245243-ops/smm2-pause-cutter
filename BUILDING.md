# 開発とビルド（Windows）

Python 3.12・64bitを用意します。GitHubのリポジトリにはバイナリや動画を入れません。

## 開発用環境

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe scripts/fetch_ffmpeg.py
.\.venv\Scripts\python.exe src/app.py
```

FFmpeg取得スクリプトは開発時だけ通信し、9.0.2の配布ZIPのSHA-256を照合します。
配布元が「latest」を更新した場合はハッシュ不一致で停止します。新バージョンを検証してマニフェストを更新してください。
実行時のアプリは自動ダウンロードを行いません。任意のPATHからFFmpegを探しません。
開発時は `bin/ffmpeg.exe`、配布時は `_internal/bin/ffmpeg.exe` を使用します。
外部FFmpegを使う場合は環境変数 `SMM2_PAUSE_CUTTER_FFMPEG` に既存EXEの絶対パスを指定します。

## テスト

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s src -p "test_*.py" -v
```

テストは自前の短い動画と合成画像を作ります。ユーザーの録画はリポジトリに含めません。
実録画による回帰検証は別途実施し、ソース用テスト結果だけで全録画環境に対応すると判断しないでください。

## Windowsビルド

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean SMM2PauseCutter.spec
```

`dist/SMM2PauseCutter/` が実行ファイル一式です。
OpenCVの旧動画デコーダーDLLを除外し、動画読み込みにはPyAVを使います。
EXEだけでなく `_internal`、README、ライセンス・告知を含めてZIPにします。
実行ファイルは未署名です。署名やウイルス対策ソフトの検査結果を偽って記載しないでください。

## 公開前

Windows用バイナリとソース用ZIPは分けてください。
第三者バイナリの対応ソース・ライセンス・ビルド情報を揃え、同じReleaseから入手できるようにしてから公開してください。
単に自作コードを公開したり、FFmpegの最新版へのリンクを貼ったりするだけでは、対応ソース確認の代わりになりません。
公開前に、Python未導入の別PCで起動・解析・音声設定ごとの書き出し・中止を確認してください。
配布ZIPに動画・個人ログ・秘密情報が入っていないことを確認し、SHA-256を掲載してください。
