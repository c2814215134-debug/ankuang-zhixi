# -*- coding: utf-8 -*-
"""
把训练得到的 best.pt 导出为 ONNX，用于 Web 平台与边缘端部署推理。

用法
----
    python export.py --weights ../weights/best.pt --imgsz 640 --opset 12

导出产物：与权重同目录的 best11_ir9.onnx（动态 batch、静态 640×640 输入）
"""

import argparse
import os
import sys
from datetime import datetime


def parse_args():
    p = argparse.ArgumentParser(description="导出改进 YOLO11n 为 ONNX")
    p.add_argument("--weights", default="../weights/best.pt")
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--opset", type=int, default=12)
    p.add_argument("--simplify", action="store_true", default=True)
    p.add_argument("--dynamic", action="store_true", help="导出动态 batch 维度")
    return p.parse_args()


def main():
    args = parse_args()
    from ultralytics import YOLO

    if not os.path.exists(args.weights):
        print(f"[错误] 权重文件不存在：{args.weights}")
        return 1

    print(f"[{datetime.now():%H:%M:%S}] 载入 {args.weights}")
    model = YOLO(args.weights)

    print(f"[{datetime.now():%H:%M:%S}] 导出 ONNX：imgsz={args.imgsz} opset={args.opset} "
          f"simplify={args.simplify} dynamic={args.dynamic}")
    path = model.export(format="onnx",
                        imgsz=args.imgsz,
                        opset=args.opset,
                        simplify=args.simplify,
                        dynamic=args.dynamic)
    print(f"[{datetime.now():%H:%M:%S}] 导出完成：{path}")

    # 用 ONNX Runtime 做一次冒烟推理，确认导出可用
    try:
        import numpy as np
        import onnxruntime as ort

        sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        inp = sess.get_inputs()[0]
        dummy = np.zeros((1, 3, args.imgsz, args.imgsz), dtype=np.float32)
        out = sess.run(None, {inp.name: dummy})
        print(f"  ONNX Runtime 冒烟推理通过：输入 {inp.shape} → 输出 {out[0].shape}")
    except ImportError:
        print("  未安装 onnxruntime，跳过冒烟推理（pip install onnxruntime）")
    except Exception as e:  # noqa: BLE001
        print(f"  冒烟推理失败：{e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
