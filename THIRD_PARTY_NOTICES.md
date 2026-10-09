# 第三者コンポーネント

自作コードのMIT LICENSEは、第三者コンポーネントをMITへ変更しません。
このソース用リポジトリは第三者EXE/DLLを含みません。

| コンポーネント | バージョン | 告知/上流 |
|---|---|---|
| Python / Tcl / Tk | ビルド環境による | licenses/Python-LICENSE.txt、Python/Tcl/Tk上流 |
| OpenCV Python headless | 5.0.0.93 | licenses/OpenCV-LICENSE.txt、OpenCV-THIRD-PARTY.txt、https://github.com/opencv/opencv-python |
| NumPy | 2.5.3 | licenses/NumPy/、https://github.com/numpy/numpy |
| PyAV | 19.0.1 | licenses/PyAV-LICENSE.txt、https://github.com/PyAV-Org/PyAV |
| PyAVのFFmpeg・外部DLL | FFmpeg 9.0.2 | licenses/pyav-binary-manifest.json、wheelの元ビルドとライセンスを別途確認 |
| FFmpeg Gyan essentials | 9.0.2 | GPLv3、licenses/FFmpeg-GPLv3.txt、licenses/ffmpeg-build/README.txt、https://www.gyan.dev/ffmpeg/builds/ |
| PyInstaller bootloader | 6.22.3 | licenses/PyInstaller-LICENSE.txt（bootloader例外を含む） |

GPL/LGPL等のバイナリを再配布する前に、実際のビルドに対応したソース・外部依存のライセンス・ビルド手順を揃えます。
FFmpeg本体のリリースtarballだけでは、外部ライブラリを含むGyanバイナリ全体の対応ソースを揃えたと断定できません。
関連する原則: https://www.ffmpeg.org/legal.html
GPLv3の配布条件: https://www.gnu.org/licenses/gpl-3.0.html
現時点で対応ソースの確認は未完了のため、Windowsバイナリの一般配布は準備中です。

元の録画由来の画像アンカーは削除し、検出用の✕はコードで一般的な幾何形状を生成します。
任天堂の映像・ロゴは本ソース用リポジトリにも候補ZIPにも含めません。
