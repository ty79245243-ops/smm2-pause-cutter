"""Relink the unmodified PyAV binding code to our LGPL FFmpeg DLLs.

Only PE import-library names are changed. No function, signature or code changes.
The original PyAV wheel's bundled codec DLLs are deliberately not copied.
"""
from pathlib import Path
import shutil,re,json,hashlib
import pefile
root=Path('vendor');root.mkdir(exist_ok=True)
original=Path('vendor-original')
for name in ('av','av-19.0.1.dist-info'):
    shutil.copytree(original/name,root/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
libs=root/'av.libs';libs.mkdir(exist_ok=True)
for source in Path('native/prefix-decoder/bin').glob('*.dll'):
    shutil.copy2(source,libs/source.name)
assert len(list(libs.glob('*.dll')))==7
changes=[]
for path in sorted((root/'av').rglob('*.pyd')):
    data=bytearray(path.read_bytes());pe=pefile.PE(data=bytes(data));relinked=[]
    for imp in pe.DIRECTORY_ENTRY_IMPORT:
        old=imp.dll.decode('ascii')
        match=re.fullmatch(r'(avcodec|avformat|avutil|avdevice|avfilter|swscale|swresample)-(\d+)-[0-9a-f]+\.dll',old)
        if not match:continue
        new=f'{match[1]}-{match[2]}.dll'
        assert (libs/new).is_file(),new
        offset=pe.get_offset_from_rva(imp.struct.Name)
        data[offset:offset+len(old)+1]=new.encode().ljust(len(old)+1,b'\0')
        relinked.append({'original':old,'replacement':new})
    if relinked:
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        path.write_bytes(data)
        changes.append({'path':path.relative_to(root).as_posix(),'original_sha256':before,'sha256':hashlib.sha256(data).hexdigest(),'imports':relinked})
(root/'binding-import-changes.json').write_text(json.dumps(changes,indent=2),encoding='utf-8')
print('Relinked',len(changes),'bindings; only 7 locally built FFmpeg DLLs')
