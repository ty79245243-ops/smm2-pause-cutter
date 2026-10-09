# Windowsビルド

Python 3.12 64bit、Git for Windows、MinGW-w64 GCC 15.1.0（win32/SEH/UCRT）、NASM 2.16.03、MSYS GNU Make 4.4.1が必要です。
今回のコンパイル環境とDLL参照変更内容はnative/BUILD_INFO.jsonを参照してください。

1. Python仮想環境を作り、requirements-build.txtをインストールします。
2. リポジトリ直下で `python scripts/fetch_native_sources.py` を実行し、native/へハッシュ検証済みソースとNASMを取得・展開します。
3. [MSYS2公式のGNU Make 4.4.1-2](https://repo.msys2.org/msys/x86_64/make-4.4.1-2-x86_64.pkg.tar.zst)を取得し、make.exeをnative/msys-make/usr/bin/に配置します。アーカイブのSHA256は `2408af61717dae87b00c855b132769a125c708907fc94a46bb16dae076113e5c` です。
4. Git Bashから `bash native/build-native.sh` を実行します。GCCはC:/mingw64/binを使用します。
5. `python -m pip install --no-deps --target vendor-original av==19.0.1` を実行します。
6. `python scripts/relink_pyav.py` を実行します。PyAVの実行コードは変更せず、PEの参照DLL名だけを自前の同一FFmpeg 9.0.2 DLLに変更します。
7. native/prefix-encoder/bin/ffmpeg.exeをbin/ffmpeg.exeへコピーします。
8. `python -m PyInstaller --noconfirm --clean SMM2PauseCutter.spec` でビルドします。

ビルド時はvendorをPYTHONPATHの先頭へ追加してください。vendor/av.libsのDLLもspecが同梱します。
PowerShellでは `$env:PYTHONPATH = (Resolve-Path vendor).Path` と設定できます。手順7まで完了すれば `python src/app.py` でソースから起動できます。
自前のFFmpegソースは未改変です。x264も未改変です。configure引数はnative/build-native.shに記録しています。
テストは `python -m unittest discover -s src -p "test_*.py" -v` で実行します。

Windows ZIPにはdistの一式、README、LICENSE、licenses、対応ソース・本手順・変更スクリプトを含めてください。
別PCでの確認を実施していない場合は、その旨を明記してください。
