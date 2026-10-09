from pathlib import Path
from PyInstaller.utils.hooks import collect_all,collect_delvewheel_libs_directory
root=Path(SPECPATH)
ffmpeg=root/'bin'/'ffmpeg.exe'
if not ffmpeg.is_file():raise RuntimeError('Run scripts/fetch_ffmpeg.py first')
av_data,av_bins,av_hidden=collect_all('av')
av_data,av_bins=collect_delvewheel_libs_directory('av',datas=av_data,binaries=av_bins)
a=Analysis([str(root/'src'/'app.py')],pathex=[str(root/'src')],binaries=av_bins,
    datas=av_data+[(str(ffmpeg),'bin')],hiddenimports=av_hidden,excludes=['imageio_ffmpeg'],noarchive=False)
# Never ship the unused old FFmpeg decoder from OpenCV.
a.binaries=[x for x in a.binaries if 'opencv_videoio_ffmpeg' not in str(x).lower()]
a.datas=[x for x in a.datas if 'opencv_videoio_ffmpeg' not in str(x).lower()]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='SMM2PauseCutter',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=False,console=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='SMM2PauseCutter')
