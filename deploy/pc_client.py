"""
PC 端客户端 — 与 Milk-V Duo 板端推理服务配合使用

架构：
  PC (本脚本) ──HTTP──> Milk-V Duo (board_infer.py --serve)
   │                          │
   │  发送视频帧/图片          │  YOLO检测
   │                          │
   │  <── 返回检测框JSON ──── │
   │
   ├─ 本地OCR识别 (PaddleOCR)
   ├─ 阶段状态判断
   └─ 结果保存/显示

用法:
  python pc_client.py --board 192.168.42.1:8080 --source video.mp4
  python pc_client.py --board 192.168.42.1:8080 --source rtsp://...
  python pc_client.py --board 192.168.42.1:8080 --source image.jpg
"""
import argparse
import json
import os
import sys
import time
import warnings
warnings.filterwarnings('ignore')

import cv2
import numpy as np
import requests


# ============================================================
# 阶段名称
# ============================================================
STAGE_NAMES = {
    '1': '开孔', '2': '见煤', '3': '验煤', '4': '止煤',
    '5': '终孔', '6': '验孔', '7': '封孔'
}


class BoardDetector:
    """通过 HTTP 与板端推理服务通信"""

    def __init__(self, board_addr='192.168.42.1:8080', timeout=5):
        self.base_url = f'http://{board_addr}'
        self.timeout = timeout
        self.connected = False

    def check(self):
        """检查板子是否在线"""
        try:
            r = requests.get(f'{self.base_url}/health', timeout=3)
            self.connected = r.status_code == 200
            return self.connected
        except Exception:
            self.connected = False
            return False

    def detect(self, frame):
        """发送帧到板子, 返回检测结果"""
        _, img_encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        try:
            r = requests.post(
                f'{self.base_url}/detect',
                data=img_encoded.tobytes(),
                timeout=self.timeout,
            )
            if r.status_code == 200:
                return r.json()
            else:
                return {'detections': [], 'error': r.text}
        except Exception as e:
            return {'detections': [], 'error': str(e)}


class LocalOCR:
    """本地 OCR (PaddleOCR)"""

    def __init__(self):
        self.ocr = None

    def load(self):
        try:
            from paddleocr import PaddleOCR
            self.ocr = PaddleOCR(use_angle_cls=True, lang='ch', use_gpu=False)
            print('[OK] PaddleOCR 加载成功 (CPU模式)')
        except ImportError:
            print('[WARN] PaddleOCR 未安装, OCR功能不可用')
            self.ocr = None

    def recognize(self, img):
        """对图像进行 OCR, 返回文本列表"""
        if self.ocr is None:
            return []
        try:
            results = self.ocr.ocr(img, cls=True)
            if results and results[0]:
                return [item[1][0] for item in results[0]]
        except Exception as e:
            print(f'[OCR ERR] {e}')
        return []

    def match_stage(self, texts):
        """从OCR文本中匹配阶段名称"""
        for text in texts:
            for key, name in STAGE_NAMES.items():
                if name in text:
                    return name
        return None


def process_video_with_board(board, ocr, source, frame_skip=2):
    """
    完整处理流程:
    1. 读取视频帧
    2. 每隔 frame_skip 帧发送到板子进行 YOLO 检测
    3. 裁剪 signage 区域
    4. 本地 OCR 识别阶段名
    5. 保存结果
    """
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f'[ERR] 无法打开视频源: {source}')
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f'视频: {width}x{height}, {fps:.1f}fps, {total_frames}帧')
    print(f'跳帧: 每{frame_skip}帧检测一次')

    frame_idx = 0
    time_board = 0
    time_ocr = 0
    board_calls = 0
    ocr_calls = 0
    last_detected_stage = None
    detections_log = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        current_stage = None
        sign_regions = []

        if frame_idx % frame_skip == 0:
            # 1. 板端 YOLO 检测
            t0 = time.time()
            result = board.detect(frame)
            time_board += time.time() - t0
            board_calls += 1

            detections = result.get('detections', [])

            # 2. 裁剪 signage 区域 + OCR
            for det in detections:
                if det['class'] == 'signage':
                    x1, y1, x2, y2 = det['bbox']
                    h, w = frame.shape[:2]
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w, x2), min(h, y2)
                    crop = frame[y1:y2, x1:x2]

                    if crop.size > 0 and ocr.ocr is not None:
                        t0 = time.time()
                        texts = ocr.recognize(crop)
                        time_ocr += time.time() - t0
                        ocr_calls += 1

                        stage = ocr.match_stage(texts)
                        if stage:
                            current_stage = stage
                            sign_regions.append({
                                'bbox': det['bbox'],
                                'texts': texts,
                                'stage': stage,
                            })

        # 更新状态
        if current_stage:
            last_detected_stage = current_stage

        if current_stage or (frame_idx % (frame_skip * 5) == 0 and frame_idx > 0):
            status = f'帧 {frame_idx}/{total_frames} | 阶段: {last_detected_stage or "未检测"}'
            print(f'\r{status}', end='', flush=True)

        if current_stage:
            detections_log.append({
                'frame': frame_idx,
                'stage': current_stage,
                'regions': sign_regions,
            })

        frame_idx += 1

    cap.release()
    print()
    print(f'\n=== 处理完成 ===')
    print(f'总帧数: {frame_idx}')
    print(f'板端调用: {board_calls}次, 平均 {time_board/max(board_calls,1)*1000:.1f}ms/次')
    if ocr_calls > 0:
        print(f'OCR调用: {ocr_calls}次, 平均 {time_ocr/max(ocr_calls,1)*1000:.1f}ms/次')
    print(f'检测到阶段变化: {len(detections_log)}次')

    # 保存日志
    log_path = 'detection_log.json'
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(detections_log, f, ensure_ascii=False, indent=2)
    print(f'日志已保存: {log_path}')


def process_image_with_board(board, ocr, img_path):
    """处理单张图片"""
    img = cv2.imread(img_path)
    if img is None:
        print(f'[ERR] 无法读取: {img_path}')
        return

    # 板端检测
    t0 = time.time()
    result = board.detect(img)
    board_time = time.time() - t0
    print(f'板端检测: {board_time*1000:.1f}ms')

    detections = result.get('detections', [])
    print(f'检测到 {len(detections)} 个目标:')

    for det in detections:
        print(f'  {det["class"]}: {det["score"]:.3f} @ {det["bbox"]}')

        if det['class'] == 'signage' and ocr.ocr is not None:
            x1, y1, x2, y2 = det['bbox']
            crop = img[y1:y2, x1:x2]
            texts = ocr.recognize(crop)
            stage = ocr.match_stage(texts)
            print(f'    OCR文本: {texts}')
            print(f'    识别阶段: {stage or "未匹配"}')


# ============================================================
# 主入口
# ============================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PC端 — 配合Milk-V Duo推理')
    parser.add_argument('--board', type=str, default='192.168.42.1:8080', help='板子地址')
    parser.add_argument('--source', type=str, required=True, help='视频/图片路径 或 RTSP URL')
    parser.add_argument('--frame-skip', type=int, default=2, help='跳帧间隔')
    parser.add_argument('--no-ocr', action='store_true', help='禁用OCR')

    args = parser.parse_args()

    # 1. 连接板子
    board = BoardDetector(args.board)
    print(f'连接板子 {args.board}...')
    if not board.check():
        print(f'[ERR] 无法连接板子, 请确认:')
        print(f'  1. Milk-V Duo 已通过 USB 连接')
        print(f'  2. 板端服务已启动: python board_infer.py --serve')
        print(f'  3. RNDIS 网络正常 (ping 192.168.42.1)')
        sys.exit(1)
    print('[OK] 板子连接成功')

    # 2. 加载 OCR
    ocr = LocalOCR()
    if not args.no_ocr:
        ocr.load()

    # 3. 处理
    path = args.source.lower()
    if path.startswith('rtsp://') or path.endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv')):
        process_video_with_board(board, ocr, args.source, args.frame_skip)
    else:
        process_image_with_board(board, ocr, args.source)
