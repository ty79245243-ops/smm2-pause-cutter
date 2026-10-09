#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
base="$PWD"
mkdir -p tools prefix decoder encoder
cp msys-make/usr/bin/make.exe tools/make.exe
export PATH="$base/tools:$base/nasm/nasm-2.16.03:/c/mingw64/bin:$PATH"
ffsrc="$base/ffmpeg/ffmpeg-9.0.2"
xsrc="$base/x264/x264-b35605ace3ddf7c1a5d67a2eb553f034aef41d55"
cd "$xsrc"
./configure --prefix="$base/prefix" --host=x86_64-w64-mingw32 --enable-static --disable-cli --disable-opencl --disable-lsmash --disable-swscale --disable-ffms --extra-ldflags=-static-libgcc > "$base/x264-configure.log" 2>&1
make -j8 > "$base/x264-build.log" 2>&1
make install >> "$base/x264-build.log" 2>&1
cat > "$base/tools/pkg-config" <<'SH'
#!/usr/bin/env bash
case "$*" in
  *x264*)
    here="$(cd "$(dirname "$0")/.." && pwd)"
    case "$*" in
      *--libs*) echo "-L$here/prefix/lib -lx264";;
      *--cflags*) echo "-I$here/prefix/include";;
      *--modversion*) echo 0.165;;
    esac
    exit 0;;
  *--version*) echo 1.8.1; exit 0;;
  *) exit 1;;
esac
SH
chmod +x "$base/tools/pkg-config"
cd "$base/decoder"
"$ffsrc/configure" --prefix="$base/prefix-decoder" --target-os=mingw32 --arch=x86_64 --cc=gcc --cxx=g++ --disable-autodetect --disable-network --disable-doc --disable-debug --disable-programs --disable-static --enable-shared --disable-encoders --disable-indevs --disable-outdevs --disable-protocols --enable-protocol=file,pipe --extra-ldflags=-static-libgcc > "$base/decoder-configure.log" 2>&1
make -j8 > "$base/decoder-build.log" 2>&1
make install >> "$base/decoder-build.log" 2>&1
cd "$base/encoder"
"$ffsrc/configure" --prefix="$base/prefix-encoder" --target-os=mingw32 --arch=x86_64 --cc=gcc --cxx=g++ --pkg-config="$base/tools/pkg-config" --disable-autodetect --disable-network --disable-doc --disable-debug --disable-shared --enable-static --enable-gpl --enable-libx264 --disable-encoders --enable-encoder=libx264,aac --disable-filters --enable-filter=select,setpts,atrim,asetpts,concat,scale,format,aresample,aformat,anull,null,apad,asplit --disable-ffplay --disable-indevs --disable-outdevs --disable-protocols --enable-protocol=file,pipe --extra-ldflags=-static-libgcc > "$base/encoder-configure.log" 2>&1
make -j8 > "$base/encoder-build.log" 2>&1
make install >> "$base/encoder-build.log" 2>&1
echo 'Native decoder and encoder build complete'
