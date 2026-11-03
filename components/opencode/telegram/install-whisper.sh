#!/usr/bin/env bash
# Install / rebuild the local Whisper engine used by the Telegram bridge.
#
#   ./install-whisper.sh            # CUDA build if nvcc exists, else CPU
#   ./install-whisper.sh --cpu      # force CPU build
#   ./install-whisper.sh --cuda     # force CUDA build
#   WHISPER_MODEL_NAME=ggml-small.en.bin ./install-whisper.sh   # other model
#
# Puts everything under ~/.local/share/opencode/whisper:
#   bin/whisper-cli  (+ libggml*.so)      models/<model>.bin
set -euo pipefail

ROOT="${WHISPER_ROOT:-$HOME/.local/share/opencode/whisper}"
VERSION="${WHISPER_VERSION:-1.9.5}"
MODEL_NAME="${WHISPER_MODEL_NAME:-ggml-large-v3-turbo-q5_0.bin}"
MODE="auto"

for arg in "$@"; do
  case "$arg" in
    --cpu) MODE="cpu" ;;
    --cuda) MODE="cuda" ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [[ "$MODE" == "auto" ]]; then
  command -v nvcc >/dev/null 2>&1 && MODE="cuda" || MODE="cpu"
fi

mkdir -p "$ROOT"/{bin,models,src}
cd "$ROOT/src"

if [[ ! -d "whisper.cpp-$VERSION" ]]; then
  echo "==> downloading whisper.cpp v$VERSION"
  curl -fsSL -o "wcpp-$VERSION.tar.gz" \
    "https://github.com/ggml-org/whisper.cpp/archive/refs/tags/v$VERSION.tar.gz"
  tar xzf "wcpp-$VERSION.tar.gz"
fi

cd "whisper.cpp-$VERSION"

CMAKE_ARGS=(
  -B build
  -DCMAKE_BUILD_TYPE=Release
  -DWHISPER_BUILD_TESTS=OFF
  -DWHISPER_BUILD_EXAMPLES=ON
  -DBUILD_SHARED_LIBS=ON
)
if [[ "$MODE" == "cuda" ]]; then
  echo "==> configuring CUDA build"
  CMAKE_ARGS+=(-DGGML_CUDA=1)
  # RTX 3090 = sm_86; widen if the GPU changes.
  CMAKE_ARGS+=(-DCMAKE_CUDA_ARCHITECTURES="${CUDA_ARCH:-86}")
else
  echo "==> configuring CPU build"
  CMAKE_ARGS+=(-DGGML_CUDA=0)
fi

cmake "${CMAKE_ARGS[@]}"
cmake --build build --config Release -j"$(nproc)" --target whisper-cli

echo "==> installing binary + shared libs to $ROOT/bin"
cp -f build/bin/whisper-cli "$ROOT/bin/"
cp -af build/bin/libggml*.so* "$ROOT/bin/" 2>/dev/null || true

if [[ ! -s "$ROOT/models/$MODEL_NAME" ]]; then
  echo "==> downloading model $MODEL_NAME (~0.5-1.6 GB)"
  curl -fL --retry 3 -o "$ROOT/models/$MODEL_NAME.part" \
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$MODEL_NAME"
  mv "$ROOT/models/$MODEL_NAME.part" "$ROOT/models/$MODEL_NAME"
fi

echo "==> done"
echo "    bin:   $ROOT/bin/whisper-cli ($MODE)"
echo "    model: $ROOT/models/$MODEL_NAME"
echo
echo "Quick check:"
echo "  LD_LIBRARY_PATH=$ROOT/bin $ROOT/bin/whisper-cli -m $ROOT/models/$MODEL_NAME \\"
echo "    -f /path/to/speech.wav -l auto -nt -np"
echo
echo "Then restart the bridge: systemctl --user restart opencode-telegram.service"
