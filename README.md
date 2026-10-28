# 安矿智析 · 煤矿钻场视频智能剪辑与数据管理平台

面向煤矿钻场"打钻视频量大、人工剪辑慢、工序难以追溯"的真实问题，用**改进
YOLO11n + PaddleOCR + FFmpeg + Flask/Vue3** 搭建的一条可运行的自动剪辑与数据
管理链路：AI 识别画面中的工序指示牌文字，自动定位工序切换帧，按帧序号无损切片，
自动规范命名并与钻孔台账双向绑定，形成"一孔一档"。

- **检测**：改进 YOLO11n，mAP50 **94.1%**（较基线 +4.8 个百分点），参数量
  **2.02 M**、计算量 **4.7 GFLOPs**、推理 **180 FPS**
- **端到端**：以检测框裁剪替代 PP-OCRv4 原生 DBNet 检测后，单帧整体处理时间
  由 55.3 ms 降至 **27.1 ms**，帧率由 18 FPS 提升至 **37 FPS**
- **落地**：10 小时长视频约 10 分钟剪完，已在两座煤矿连续运行 3 个月

- **赛项**：2026 第八届全球校园人工智能算法精英大赛 · 算法主题赛（AI+开源）
- **许可证**：AGPL-3.0（见 [LICENSE](LICENSE)）—— 含 Ultralytics 衍生代码的部分

---

## 1. 目录结构

```
.
├── backend/                  # Flask 后端：业务接口 + AI 引擎
│   ├── app.py                #   REST 接口入口（端口 2800）
│   ├── ai_engine.py          #   检测 → OCR → 工序判定 → 切片 全流程引擎
│   ├── models.py             #   SQLAlchemy 数据表（钻孔台账/地点/摄像仪/识别记录）
│   ├── config.py             #   路径与配置（支持 VIDEO_ROOT 环境变量）
│   ├── zzbest.pt             #   检测权重（服务端推理用）
│   ├── raw_videos/           #   待处理原始视频（processed/ 为切片输出）
│   ├── thumbnails/           #   切片缩略图缓存
│   └── requirements.txt
├── frontend/                 # Vue 3 + Element Plus 前端
│   ├── src/views/            #   六大业务模块页面
│   ├── src/api/index.js      #   接口封装（后端基址 http://localhost:2800）
│   └── package.json
├── framework/                # 改进版 Ultralytics 8.3.9 完整源码（AGPL-3.0，可直接安装）
│   ├── pyproject.toml        #   pip install -e framework/
│   ├── README.md             #   相对上游的改动清单
│   └── ultralytics/
│       ├── cfg/models/11/yolo11-attention.yaml  # 最终采用的模型结构
│       ├── nn/extra_modules/ #   新增模块（Faster-EMA / TripletAttention / Detect_Efficient 等）
│       └── utils/loss.py     #   PIoUv2 损失实现
├── train/
│   ├── yolo11-attention.yaml #   改进模型结构（与 framework 内同名文件、weights/best.pt 一致）
│   ├── train.py              #   训练脚本（默认超参数即论文取值）
│   ├── export.py             #   导出 ONNX 并做冒烟推理
│   ├── piouv2_patch.md       #   算法改造点逐条清单（含文件与行号）
│   ├── data.yaml             #   数据集配置（nc=1，signage）
│   ├── meV2027v51.py         #   PyQt5 桌面端全流程客户端（检测+OCR+剪辑）
│   └── requirements.txt
├── weights/
│   ├── best.pt               #   训练权重（内嵌完整 300 轮训练日志）
│   └── best11_ir9.onnx       #   ONNX 部署模型
├── deploy/                   #   RISC-V 边缘端（Milk-V Duo）部署脚本
├── docs/                     #   部署手册、接口文档、数据集说明、测试记录
├── fonts/                    #   Noto Sans SC 思源黑体（SIL OFL 1.1）
├── dataset_description/      #   数据集说明与脱敏样例
├── LICENSE                   #   AGPL-3.0
└── NOTICE                    #   第三方许可与版权声明
```

> **说明**：因涉及井下真实作业影像与企业生产信息，仓库中**不包含**原始监控
> 视频全量与完整标注文件；数据集以 `dataset_description/` 说明文档 + 脱敏样例
> 形式开放，评审期可通过受限仓库或网盘查阅原始材料。

---

## 2. 环境要求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| 操作系统 | Ubuntu 22.04 / Windows 10+ | 两种系统均验证通过 |
| Python | 3.8 ~ 3.10 | 训练端 3.8 验证；服务端 3.9+ 亦可 |
| GPU | NVIDIA RTX 4090 24 GB（训练） | 推理可为纯 CPU |
| CUDA | 11.8 | 仅训练与 GPU 推理需要 |
| Node.js | ≥ 18 | 前端构建与开发服务器 |
| FFmpeg | 4.x | **必需**，用于视频切片与转码 |

---

## 3. 快速开始

### 3.1 安装 FFmpeg

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y ffmpeg

# Windows：下载 https://www.gyan.dev/ffmpeg/builds/ 的 essentials 版本，
# 解压后把 ffmpeg.exe 所在目录加入 PATH，或直接放到 backend/ 目录下。
ffmpeg -version
```

### 3.2 安装改进版检测框架

后端与训练脚本都依赖改进版框架，先装它（AGPL-3.0，随仓库提供源码）：

```bash
# 仓库根目录执行
pip install -e framework/
```

### 3.3 启动后端

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
# 看到 "煤矿系统后端 V2.0 已启动: http://0.0.0.0:2800" 即成功
# 健康检查：http://localhost:2800/api/health
```

> 首次启动自动创建 SQLite 数据库与数据表。账号在登录页**注册**创建：
> 用户名须**字母+数字组合**，密码 **>6 位且含字母与数字**。

### 3.4 启动前端

```bash
cd frontend
npm install
npm run dev        # 默认 http://localhost:5173
```

生产构建：`npm run build`（产物在 `frontend/dist/`）。

### 3.5 跑一次完整流程

1. 登录 → 进入 **工序智能分析 / AI 识别结果台账**
2. 点击 **配置批量分析任务** → 上传一段钻场监控视频
3. 设置"归档重命名"名称与**跳帧阈值**（1–30，默认 3；数值越大跳过帧越多、处理越快）
4. 提交任务 → 在任务列表查看实时分析进度与判定状态
5. 完成后点 **查看结果** → 自动跳转视频归档库并定位该视频的工序切片
6. 在 **钻孔业务管理** 新建台账，把切片与钻孔编号绑定，形成"一孔一档"

---

## 4. 算法改进说明

相对原生 YOLO11n 做了三项改进，最终结构见 `train/yolo11-attention.yaml`
（与 `weights/best.pt` 逐层一致）：

| # | 改进 | 作用 | 单独增益（mAP50） |
| --- | --- | --- | --- |
| ① | **C3k2 → C3k2_Faster_EMA** | FasterBlock（PConv 部分卷积）降冗余计算 + EMA 多尺度注意力保特征 | +1.6 |
| ② | **引入 Triplet Attention** | 三分支无参注意力，强化跨维度交互，抑制尘雾与反光背景 | +2.9 |
| ③ | **CIoU → PIoUv2 损失** | 以边距离惩罚项替代宽高比项，收敛更快、定位更准 | +2.1 |

三项同时启用时 mAP50 达 **94.1%**（基线 89.3%），参数量由 2.58 M 降至
**2.02 M**，计算量由 6.3 降至 **4.7 GFLOPs**。

OCR 侧：**以 YOLO 检测框裁剪结果直接替代 PP-OCRv4 原生 DBNet 文字检测环节**。
指示牌是固定版式的单行文本，用检测框裁剪既准又快，检测耗时由 35.0 ms 降至
6.5 ms，是整条链路提速的主要来源。

改造点逐条（文件、行号、代码片段）见 **`train/piouv2_patch.md`**。

---

## 5. 训练自己的模型

### 5.1 准备工程

改进后的框架源码已随仓库提供在 `framework/`（基于 Ultralytics 8.3.9，
含 `C3k2_Faster_EMA`、`TripletAttention`、`Detect_Efficient` 与 PIoUv2 分支），
**无需手工打补丁**，以可编辑模式安装即可：

```bash
pip install -e framework/          # 安装改进版框架（AGPL-3.0）
pip install -r train/requirements.txt
python -c "from ultralytics import YOLO; print('ok')"
```

若只想复现改动、不安装：`train/piouv2_patch.md` 按文件与行号列出了相对上游
8.3.9 的全部修改点，可自行在官方版本上打补丁。

### 5.2 准备数据集

```
dataset/
├── images/{train,val,test}/
└── labels/{train,val,test}/     # YOLO txt：class x_center y_center w h（归一化）
```

`data.yaml` 中 `nc: 1`，`names: ['signage']`。标注规范见
`dataset_description/README.md`。

### 5.3 开始训练

```bash
cd train
python train.py --data ../dataset/data.yaml --epochs 300 --batch 32 --device 0
```

脚本默认值即论文超参数，与 `best.pt` 内嵌的 `train_args` 完全一致：

| 超参数 | 取值 | 超参数 | 取值 |
| --- | --- | --- | --- |
| 初始 / 最终学习率 | 0.01 / 0.01 | 优化器 | SGD |
| 动量 | 0.937 | 权重衰减 | 0.0005 |
| 输入尺寸 | 640 × 640 | Batch size | 32 |
| 训练轮次 | 300 | Workers | 16 |
| 早停 patience | 100 | 随机种子 | 0 |

单卡 RTX 4090 训练 300 轮约 1.8 小时。

### 5.4 导出与指标复核

```bash
python export.py --weights ../weights/best.pt --imgsz 640
```

`best.pt` 内嵌完整 300 轮训练日志，可直接核对：

```python
import torch
ck = torch.load("weights/best.pt", map_location="cpu", weights_only=False)
print(ck["train_args"])      # 训练超参数
print(ck["train_results"])   # 300 轮 loss / mAP / P / R 曲线
```

参考结果：P 90.2%、R 88.6%、mAP50 94.1%、mAP50-95 67.9%，最佳 mAP50 出现在
第 220 轮。

---

## 6. 边缘端部署（可选）

`deploy/` 提供 RISC-V 边缘设备（Milk-V Duo）的推理与上报程序，板端仅依赖
ONNX Runtime，无需 PyTorch / Paddle 全栈，适合井下低带宽、离线环境。

```bash
cd deploy
bash setup_board.sh                 # 板端环境安装
python board_infer.py --model ../weights/best11_ir9.onnx --source video.mp4
python board_camera.py              # 摄像头采集
```

`pc_client.py` 为 PC 端结果接收客户端。

---

## 7. 开源合规声明

| 范围 | 许可证 |
| --- | --- |
| 含 Ultralytics 衍生代码的部分（模型定义、训练与推理脚本） | **AGPL-3.0**（见 `LICENSE`） |
| 平台业务代码（Flask 后端、Vue3 前端、部署脚本） | MIT |
| 数据集说明文档 | 可公开；原始视频与完整标注因涉企业生产信息**不公开** |

- 依据 AGPL-3.0 第 13 条，若以网络服务形式对外提供本作品衍生部分，须向使用者
  提供对应源代码的获取方式；本作品在煤矿现场为内部部署，不对外分发。
- PaddleOCR / PaddlePaddle / OpenCV / ECharts 为 Apache-2.0；PyTorch / Flask 为
  BSD 类；Vue3 / Element Plus / Vite / ONNX Runtime 为 MIT；FFmpeg 以子进程方式
  调用，未修改、未链接、未再分发其源码。
- 视频叠加文字使用 **Noto Sans SC 思源黑体（SIL OFL 1.1）**，随仓库 `fonts/`
  分发；原专有字体 SimHei 文件不进入仓库。
- 第三方组件完整清单与义务见 **`NOTICE`** 与技术报告附录表 A1。

---

## 8. 已知限制

- 极端逆光、指示牌被完全遮挡时仍会漏检 → 平台保留"人工补录工序"入口，日志
  标记低置信度片段
- 非标准手写工序名无法匹配字典 → 人工补录并可扩展字典
- 单机部署并发任务超过 4 路时处理时延上升 → 任务排队与跳帧阈值调节
- 数据集 6332 张，遮挡与逆光样本相对不足 → 已纳入扩充计划

---

## 9. 致谢

本作品基于 [Ultralytics YOLO11](https://github.com/ultralytics/ultralytics)、
[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)、
[FFmpeg](https://ffmpeg.org/) 等开源项目构建，遵循其各自许可证。
