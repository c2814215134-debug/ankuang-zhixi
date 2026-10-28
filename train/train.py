# -*- coding: utf-8 -*-
"""
改进 YOLO11n 训练脚本 —— 煤矿钻场工序指示牌检测（单类别 signage）

前置条件
--------
1. 本脚本依赖仓库自带的改进版框架（提供 C3k2_Faster_EMA、TripletAttention、
   Detect_Efficient 与 PIoUv2），在仓库根目录执行  pip install -e framework/
   即可，无需手工覆盖模块。切勿再装 PyPI 上的 ultralytics，会覆盖改进版。
2. 数据集按 train/data.yaml 的目录结构组织好（images/{train,val,test}
   与 labels/{train,val,test} 一一对应，YOLO txt 格式）。
3. PIoUv2 已在框架内改好：loss.py 与 tal.py 两处均已传 PIoU2=True，二者必须
   同时启用（只改一处会出现"CIoU 分配正样本 + PIoUv2 算损失"，mAP50 低约 0.4 点）。
   改动位置见 train/piouv2_patch.md。

用法
----
    python train.py --data ../dataset/data.yaml --epochs 300 --batch 32

论文中的超参数即为脚本默认值，与 weights/best.pt 内嵌的 train_args 完全一致。
"""

import argparse
import os
import sys
from datetime import datetime

import torch


def parse_args():
    p = argparse.ArgumentParser(description="训练改进 YOLO11n（煤矿钻场工序指示牌检测）")
    p.add_argument("--model", default="yolo11-attention.yaml",
                   help="模型结构定义文件（本仓库 train/ 目录）")
    p.add_argument("--data", default="../dataset/data.yaml", help="数据集配置")
    p.add_argument("--weights", default="yolo11n.pt", help="预训练权重，空字符串表示从零训练")
    p.add_argument("--epochs", type=int, default=300)
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--device", default="0", help="GPU 编号，CPU 训练填 cpu")
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--patience", type=int, default=100, help="早停轮次")
    p.add_argument("--optimizer", default="SGD")
    p.add_argument("--lr0", type=float, default=0.01)
    p.add_argument("--lrf", type=float, default=0.01)
    p.add_argument("--momentum", type=float, default=0.937)
    p.add_argument("--weight-decay", type=float, default=0.0005)
    p.add_argument("--warmup-epochs", type=float, default=3.0)
    p.add_argument("--project", default="signage/runs/train")
    p.add_argument("--name", default="exp")
    p.add_argument("--seed", type=int, default=0)
    return p.parse_args()


def main():
    args = parse_args()
    from ultralytics import YOLO
    from ultralytics import settings as ul_settings

    print("=" * 68)
    print("改进 YOLO11n 训练 · 煤矿钻场工序指示牌检测")
    print("=" * 68)
    print(f"PyTorch       : {torch.__version__}   CUDA 可用: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU           : {torch.cuda.get_device_name(0)}")
    print(f"模型结构      : {args.model}")
    print(f"数据集        : {args.data}")
    print(f"epochs/batch  : {args.epochs} / {args.batch}   imgsz={args.imgsz}")
    print(f"优化器        : {args.optimizer}  lr0={args.lr0}  momentum={args.momentum}  wd={args.weight_decay}")
    print(f"开始时间      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 68)

    # 关闭匿名指标上传，避免联网
    try:
        ul_settings.update({"sync": False})
    except Exception:
        pass

    model = YOLO(args.model).load(args.weights) if args.weights else YOLO(args.model)

    results = model.train(
        data=args.data,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        optimizer=args.optimizer,
        lr0=args.lr0,
        lrf=args.lrf,
        momentum=args.momentum,
        weight_decay=args.weight_decay,
        warmup_epochs=args.warmup_epochs,
        seed=args.seed,
        deterministic=True,
        amp=True,
        plots=True,
        project=args.project,
        name=args.name,
    )

    # 在验证集上复核最终指标
    metrics = model.val(data=args.data, split="val")
    print("\n" + "=" * 68)
    print("验证集结果")
    print(f"  P      : {metrics.box.mp:.4f}")
    print(f"  R      : {metrics.box.mr:.4f}")
    print(f"  mAP50  : {metrics.box.map50:.4f}")
    print(f"  mAP50-95: {metrics.box.map:.4f}")
    print("=" * 68)
    return results


if __name__ == "__main__":
    sys.exit(0 if main() is not None else 1)
