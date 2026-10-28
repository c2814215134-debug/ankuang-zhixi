# framework —— 改进版 Ultralytics 框架（AGPL-3.0）

本目录是「安矿智析」作品实际使用的检测框架源码，基于 **Ultralytics 8.3.9** 修改，
遵循上游 **AGPL-3.0** 许可（全文见仓库根目录 `LICENSE`）。

## 安装

```bash
# 在仓库根目录执行，可编辑模式安装，之后 backend/ 与 train/ 都能直接 import
pip install -e framework/

# 验证
python -c "from ultralytics import YOLO; print('ultralytics import ok')"
```

依赖会自动安装；若需导出 ONNX，另装 `onnx` 与 `onnxruntime`。

## 相对上游的改动

| # | 改动 | 位置 |
| --- | --- | --- |
| 1 | 主干与颈部 `C3k2` → `C3k2_Faster_EMA`（FasterBlock/PConv + EMA 多尺度注意力） | `ultralytics/nn/extra_modules/block.py`、`ultralytics/nn/tasks.py` |
| 2 | 主干末端（`SPPF → C2PSA` 之后）插入 `TripletAttention`，颈部 P5 跳跃连接由第 10 层改接第 11 层 | `ultralytics/nn/extra_modules/attention.py`、`ultralytics/nn/tasks.py` |
| 3 | 检测头改用 `Detect_Efficient` | `ultralytics/nn/extra_modules/head.py` |
| 4 | 回归损失 `CIoU` → `PIoUv2` | `ultralytics/utils/loss.py`、`ultralytics/utils/tal.py` |
| 5 | 新增实验模块（AFPN、CTrans、RFAconv、FreqFusion、SMPConv 等） | `ultralytics/nn/extra_modules/` |

**逐条改动清单（含文件路径、行号与代码片段）见仓库根目录 `train/piouv2_patch.md`。**

## 模型配置

本作品最终使用的结构定义：

```
framework/ultralytics/cfg/models/11/yolo11-attention.yaml
```

该文件与仓库根目录 `train/yolo11-attention.yaml` 内容一致，与 `weights/best.pt`
的层结构逐层对应。训练命令：

```bash
yolo detect train model=framework/ultralytics/cfg/models/11/yolo11-attention.yaml \
                   data=train/data.yaml epochs=300 imgsz=640 batch=32 device=0
```

`ultralytics/cfg/models/11/` 下另有约 200 个改型配置，是本项目在选型阶段做的
对比实验留存，最终采用的只有 `yolo11-attention.yaml`，其余仅供复现实验参考。

## 许可与义务

- 本目录代码为 AGPL-3.0 衍生作品，**分发或对外提供网络服务时须一并提供本目录
  完整源码**，并保留上游版权声明。
- 上游项目：<https://github.com/ultralytics/ultralytics>
- 版权归 Ultralytics 及原作者所有；本团队改动部分同样以 AGPL-3.0 发布。
