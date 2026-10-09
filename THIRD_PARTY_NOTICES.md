# 第三者コンポーネント

自作コードはMITです。第三者コンポーネントには各ライセンスが適用されます。

| コンポーネント | バージョン／構成 | ライセンス・資料 |
|---|---|---|
| 読み込み用FFmpeg DLL | 9.0.2、自前ビルド、外部ライブラリなし、GPL/nonfree無効 | LGPL 2.1以降、licenses/COPYING.LGPLv2.1 |
| 書き出し用FFmpeg EXE | 9.0.2、自前ビルド、外部ライブラリはx264のみ | GPL 2以降、licenses/COPYING.GPLv2 |
| x264 | b35605ace3ddf7c1a5d67a2eb553f034aef41d55 | GPL 2以降、licenses/x264-COPYING.txt |
| PyAV | 19.0.1、DLL参照名のみ変更 | BSD 3-Clause、licenses/PyAV-LICENSE.txt |
| OpenCV Python headless | 5.0.0.93、動画デコーダーDLLは除外 | MIT/Apache等、licenses/OpenCV-* |
| NumPy | 2.5.3 | BSD等、licenses/NumPy/（OpenBLAS等を含む） |
| Python / Tcl / Tk | 同梱ランタイムによる | licenses/Python-LICENSE.txt、tcl8.6/tk8.6-license.terms |
| OpenSSL | 3.5.8（Pythonに同梱） | Apache 2.0、licenses/OpenSSL-LICENSE.txt |
| libffi | Pythonに同梱 | MIT、licenses/libffi-LICENSE.txt |
| GCC runtime | MinGW GCC 15.1.0、静的リンク | GPL 3 + GCC Runtime Library Exception 3.1、licenses/GCC-* |
| MinGW-w64 runtime | v12 | licenses/MinGW-w64-COPYING.txt |
| PyInstaller | 6.22.3 | licenses/PyInstaller-LICENSE.txt、bootloader例外 |

Windows ZIPには、同梱FFmpeg/x264/PyAVに対応するソースアーカイブ、DLL参照名変更スクリプト、ビルド手順をsourceフォルダに含めています。
これらのソースを使った改変・再ビルドや、互換DLLへの交換を禁止する追加条件はありません。
FFmpeg DLLは動的リンク、GPLの書き出しEXEは別プロセスで呼び出します。
元のPyAV wheelのFFmpeg・コーデックDLLおよびGyanのEXEは本配布に含めません。
