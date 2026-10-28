# 算法改造点清单（基于 Ultralytics 8.3.9）

本清单逐条列出团队在官方 Ultralytics 8.3.9 之上做了哪些改动、落在哪些文件、
以及在公开仓库中如何复现。所有行号均以本仓库配套的改造后工程为准。

> **路径基准**：下表中的 `ultralytics/...` 路径均相对于仓库的 `framework/` 目录，
> 即完整路径为 `framework/ultralytics/...`。安装方式：仓库根目录执行
> `pip install -e framework/`。

---

## 一、改进①：C3k2 → C3k2_Faster_EMA

| 文件 | 位置 | 内容 |
| --- | --- | --- |
| `ultralytics/nn/extra_modules/block.py` | `Faster_Block_EMA`、`C3k_Faster_EMA`（约 863 行）、`C3k2_Faster_EMA`（约 869 行） | 新增：以 FasterBlock（PConv 部分卷积 + 两层 1×1 卷积）替换原 Bottleneck，并在残差分支末端接入 EMA 注意力 |
| `ultralytics/nn/extra_modules/attention.py` | `EMA` | 新增多尺度并行子网的跨空间注意力模块 |
| `ultralytics/nn/tasks.py` | `C3K2_CLASS` 元组（约 122 行） | 把 `C3k2_Faster_EMA` 注册进解析白名单，使 YAML 可直接按类名引用 |

## 二、改进②：引入 Triplet Attention

| 文件 | 位置 | 内容 |
| --- | --- | --- |
| `ultralytics/nn/extra_modules/attention.py` | `TripletAttention`（约 661 行） | 新增三分支（H-W、C-W、C-H）无参数化注意力 |
| `ultralytics/nn/tasks.py` | `ATTENTION_CLASS` 元组（约 1192 行） | 注册 `TripletAttention` |
| `ultralytics/cfg/models/11/yolo11-attention.yaml` | backbone 第 11 层 | 在 SPPF → C2PSA 之后插入 `[-1, 1, TripletAttention, []]` |
| 同上 | head 第 22 层 | 跳跃连接由原生 `[[-1, 10], 1, Concat, [1]]`（接 C2PSA）改为 `[[-1, 11], 1, Concat, [1]]`（接 TripletAttention 输出） |

> 第二处改动是必需的：若只插入注意力模块而不改跳跃连接，加强后的特征不会
> 进入颈部 P5 分支，实测增益会消失。

## 三、改进③：CIoU → PIoUv2

### 3.1 损失项实现（已实现）

`ultralytics/utils/metrics.py` 的 `bbox_iou()` 中新增 `PIoU` / `PIoU2` 两个
开关（约 167–179 行），`bbox_inner_iou()`（约 219 行起）同步支持：

```python
elif PIoU or PIoU2:
    dw1 = torch.abs(b1_x2.minimum(b1_x1) - b2_x2.minimum(b2_x1))
    dw2 = torch.abs(b1_x2.maximum(b1_x1) - b2_x2.maximum(b2_x1))
    dh1 = torch.abs(b1_y2.minimum(b1_y1) - b2_y2.minimum(b2_y1))
    dh2 = torch.abs(b1_y2.maximum(b1_y1) - b2_y2.maximum(b2_y1))
    P = ((dw1 + dw2) / torch.abs(w2) + (dh1 + dh2) / torch.abs(h2)) / 4
    piou_v1 = 1 - iou - torch.exp(-P ** 2) + 1
    if PIoU:
        return 1 - piou_v1
    elif PIoU2:
        q = torch.exp(-P)
        x = q * Lambda
        return 1 - 3 * x * torch.exp(-x ** 2) * piou_v1
```

### 3.2 启用方式（**本仓库已默认启用 PIoUv2**）

本文最终模型采用 PIoUv2，两处开关均已切换，开箱即用：

| 文件 | 位置 | 当前值 |
| --- | --- | --- |
| `ultralytics/utils/loss.py` | `BboxLoss.__call__` 回归损失计算处（约 242 行） | `iou = bbox_iou(pred_bboxes[fg_mask], target_bboxes[fg_mask], xywh=False, PIoU2=True)` |
| `ultralytics/utils/tal.py` | `TaskAlignedAssigner.iou_calculation()`（约 130 行） | `return bbox_iou(gt_bboxes, pd_bboxes, xywh=False, PIoU2=True).squeeze(-1).clamp_(0)` |

> **两处必须同时改**。若只改 `loss.py`，会出现"用 CIoU 分配正样本、用
> PIoUv2 计算损失"的口径不一致；实测该情况下 mAP50 比两处都改低约 0.4 个
> 百分点。这一点在早期版本踩过坑，故一并记录。

### 3.3 复现基线对照

消融实验表 13 中"模型 1（基线）""模型 2""模型 3""模型 5"不使用 PIoUv2，
复现时把上述两行同时改回 `CIoU=True` 即可，改动处均留有 `# [本文改造]` 注释标明切换方法。

两行的当前取值可用如下命令直接核验：

```bash
grep -n "PIoU2=True" ultralytics/utils/loss.py ultralytics/utils/tal.py
```

数值冒烟测试（1 组预测框与 1 组真值框，坐标 x1y1x2y2 格式）：

| 情形 | CIoU | PIoUv2 |
| --- | --- | --- |
| 部分重叠 (10,10,30,30) vs (12,14,28,32) | 0.5824 | 0.5914 |
| 完全重合 | 1.0000 | 1.0000 |

## 四、附带改动：检测头 Detect_Efficient

| 文件 | 位置 | 内容 |
| --- | --- | --- |
| `ultralytics/nn/extra_modules/head.py` | `Detect_Efficient`（约 192 行） | 轻量化检测头 |
| `ultralytics/nn/tasks.py` | `DETECT_CLASS` 元组（约 116 行） | 注册该检测头 |

## 五、未改动的部分

数据加载、数据增强、NMS、训练调度器、验证与导出流程均沿用官方实现，
未做修改，保证与官方 YOLO11n 的可比性。
