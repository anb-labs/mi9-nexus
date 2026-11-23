#!/usr/bin/env bash
# Build libmi9llama.so (llama.cpp + JNI) for Android ABIs and place them in jniLibs.
#
# Requirements: Android NDK r28 (any 28.x), cmake >= 3.31, make.
# Usage: ./build-native.sh [abi ...]   (default: arm64-v8a x86_64)
set -euo pipefail
cd "$(dirname "$0")"

ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
NDK="$ANDROID_HOME/ndk/28.2.13676358"
HOST_TAG="linux-x86_64"
NDKBIN="$NDK/toolchains/llvm/prebuilt/$HOST_TAG/bin"
LLAMA_SRC="$(cd third_party/llama.cpp && pwd)"

if [ ! -x "$NDKBIN/clang" ]; then
  echo "NDK not found at $NDK. Install with:" >&2
  echo "  sdkmanager \"ndk;28.2.13676358\"" >&2
  exit 1
fi

ABIS=("$@")
[ ${#ABIS[@]} -eq 0 ] && ABIS=(arm64-v8a x86_64)

for ABI in "${ABIS[@]}"; do
  echo "=== building $ABI ==="
  cmake -B "build/$ABI" -S app/src/main/cpp -G "Unix Makefiles" \
    -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI="$ABI" \
    -DANDROID_PLATFORM=android-26 \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_SRC="$LLAMA_SRC" >/dev/null
  cmake --build "build/$ABI" -j"$(nproc)"
  mkdir -p "app/src/main/jniLibs/$ABI"
  cp "build/$ABI/libmi9llama.so" "app/src/main/jniLibs/$ABI/libmi9llama.so"
  "$NDKBIN/llvm-strip" --strip-unneeded "app/src/main/jniLibs/$ABI/libmi9llama.so"
  echo "=== $ABI done ($(du -h "app/src/main/jniLibs/$ABI/libmi9llama.so" | cut -f1)) ==="
done
echo "All done. Rebuild the APK: ./gradlew assembleDebug"