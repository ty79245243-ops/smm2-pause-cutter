"""Developer-only verified FFmpeg download. Not called by the application."""
from pathlib import Path
import hashlib,json,urllib.request,zipfile,tempfile,shutil
ROOT=Path(__file__).resolve().parent.parent
manifest=json.loads((ROOT/'scripts'/'ffmpeg-download.json').read_text(encoding='utf-8'))
with tempfile.TemporaryDirectory(prefix='smm2_ffmpeg_') as folder:
    archive=Path(folder)/'ffmpeg.zip'
    with urllib.request.urlopen(manifest['url'],timeout=60) as response,archive.open('wb') as output:
        shutil.copyfileobj(response,output)
    actual=hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual!=manifest['sha256']:raise RuntimeError('FFmpeg download hash mismatch. Do not execute it; review the upstream release.')
    with zipfile.ZipFile(archive) as z:
        members=[n for n in z.namelist() if n.endswith('/bin/ffmpeg.exe')]
        if len(members)!=1:raise RuntimeError('Unexpected archive structure')
        (ROOT/'bin').mkdir(exist_ok=True)
        (ROOT/'bin'/'ffmpeg.exe').write_bytes(z.read(members[0]))
print('Verified FFmpeg',manifest['version'],'stored in bin/ffmpeg.exe')
