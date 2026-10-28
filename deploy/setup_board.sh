#!/bin/sh
# Milk-V Duo 摄像头检测环境初始化
echo "=== Milk-V Duo 环境初始化 ==="

PYTHON=""
for p in python3 python; do
    command -v $p >/dev/null 2>&1 && PYTHON=$p && break
done

if [ -z "$PYTHON" ]; then
    echo "[ERR] 未找到 Python, 尝试安装..."
    apt-get update 2>/dev/null && apt-get install -y python3 2>/dev/null
    opkg update 2>/dev/null && opkg install python3 2>/dev/null
    for p in python3 python; do
        command -v $p >/dev/null 2>&1 && PYTHON=$p && break
    done
fi

if [ -z "$PYTHON" ]; then
    echo "[ERR] Python 安装失败, 请手动安装"
    exit 1
fi

echo "[OK] Python: $($PYTHON --version 2>&1)"

# 安装 pip
$PYTHON -m pip --version >/dev/null 2>&1 || {
    echo "安装 pip..."
    $PYTHON -m ensurepip 2>/dev/null || true
}

PIP="$PYTHON -m pip"

# 安装最小依赖
echo "安装依赖 (可能需要几分钟)..."
for pkg in numpy opencv-python-headless; do
    echo "  $pkg ..."
    $PIP install "$pkg" --no-cache-dir 2>&1 | tail -1
done

# onnxruntime 可选（失败则用 OpenCV DNN）
echo "  onnxruntime ..."
$PIP install onnxruntime --no-cache-dir 2>&1 | tail -1 || {
    echo "  [WARN] onnxruntime 不可用, 将使用 OpenCV DNN 后端"
}

# 验证
echo ""
echo "=== 环境验证 ==="
$PYTHON -c "
import sys; print(f'Python: {sys.version}')
try:
    import numpy; print(f'numpy: {numpy.__version__}')
except: print('numpy: MISSING')
try:
    import cv2; print(f'opencv: {cv2.__version__}')
except: print('opencv: MISSING')
try:
    import onnxruntime; print(f'onnxruntime: {onnxruntime.__version__}')
except: print('onnxruntime: MISSING (回退OpenCV DNN)')
"

echo ""
echo "=== 初始化完成 ==="
echo "启动摄像头检测:"
echo "  $PYTHON board_camera.py --model best11_ir9.onnx"
echo ""
echo "浏览器打开 http://$(hostname -I | awk '{print $1}'):8080"
