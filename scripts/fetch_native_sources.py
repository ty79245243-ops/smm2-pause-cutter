from pathlib import Path
import urllib.request, hashlib, tarfile, zipfile, json
root=Path('native').resolve();root.mkdir(exist_ok=True)
items=[
 ('ffmpeg','https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz','8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e'),
 ('x264','https://code.videolan.org/videolan/x264/-/archive/b35605ace3ddf7c1a5d67a2eb553f034aef41d55/x264-b35605ace3ddf7c1a5d67a2eb553f034aef41d55.tar.bz2','6eeb82934e69fd51e043bd8c5b0d152839638d1ce7aa4eea65a3fedcf83ff224'),
 ('nasm','https://www.nasm.us/pub/nasm/releasebuilds/2.16.03/win64/nasm-2.16.03-win64.zip','3ee4782247bcb874378d02f7eab4e294a84d3d15f3f6ee2de2f47a46aa7226e6'),
]
manifest=[]
for name,url,expected in items:
    path=root/url.rsplit('/',1)[-1]
    if not path.exists():
        print('Downloading',name,flush=True)
        with urllib.request.urlopen(url,timeout=90) as r:path.write_bytes(r.read())
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if expected and actual!=expected:raise RuntimeError(name+' hash mismatch')
    folder=root/name;folder.mkdir(exist_ok=True)
    if path.suffix=='.zip':
        with zipfile.ZipFile(path) as z:
            for member in z.infolist():
                resolved=(folder/member.filename).resolve()
                assert resolved.is_relative_to(folder)
            z.extractall(folder)
    else:
        with tarfile.open(path) as t:t.extractall(folder,filter='data')
    manifest.append(dict(name=name,url=url,sha256=actual,archive=path.name))
    print('Ready',name,actual,flush=True)
(root/'downloads.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
