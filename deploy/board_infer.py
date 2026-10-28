"""
Milk-V Duo 板端 YOLO 推理脚本
使用 ONNX Runtime 进行推理，内存占用最小化
用法:
    python board_infer.py --model best11_ir9.onnx --source image.jpg
    python board_infer.py --model best11_ir9.onnx --source video.mp4 --output result.json
    python board_infer.py --model best11_ir9.onnx --serve --port 8080  # HTTP服务模式
"""
import argparse
import json
import os
import sys
import time
import warnings
warnings.filterwarnings('ignore')

import numpy as np

# ============================================================
# 类别名称 — 与训练时保持一致
# ============================================================
CLASS_NAMES = {
    0: 'signage',
}

# 煤矿作业阶段名称
STAGE_NAMES = {
    '1': '开孔', '2': '见煤', '3': '验煤', '4': '止煤',
    '5': '终孔', '6': '验孔', '7': '封孔'
}


def letterbox(img, new_shape=(640, 640), color=(114, 114, 114)):
    """Resize and pad image to new_shape, preserving aspect ratio."""
    shape = img.shape[:2]
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = (int(round(shape[1] * r)), int(round(shape[0] * r)))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]
    dw, dh = dw // 2, dh // 2

    if shape[::-1] != new_unpad:
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = dh, new_shape[0] - new_unpad[0] - dh
    left, right = dw, new_shape[1] - new_unpad[1] - dw
    img = cv2.copyMakeBorder(img, top, bottom, left, right,
                             cv2.BORDER_CONSTANT, value=color)
    return img, (r, dw, dh)


def xywh2xyxy(x):
    """Convert [cx, cy, w, h] to [x1, y1, x2, y2]."""
    y = np.copy(x)
    y[:, 0] = x[:, 0] - x[:, 2] / 2
    y[:, 1] = x[:, 1] - x[:, 3] / 2
    y[:, 2] = x[:, 0] + x[:, 2] / 2
    y[:, 3] = x[:, 1] + x[:, 3] / 2
    return y


def nms(boxes, scores, iou_threshold):
    """Simple NumPy NMS implementation."""
    if len(boxes) == 0:
        return []
    x1, y1 = boxes[:, 0], boxes[:, 1]
    x2, y2 = boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[np.where(iou <= iou_threshold)[0] + 1]
    return keep


class YOLOONNX:
    """轻量级 YOLO ONNX 推理器"""

    def __init__(self, model_path, conf_threshold=0.5, iou_threshold=0.45, img_size=640):
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.img_size = img_size
        self.session = None
        self.input_name = None
        self.output_name = None

    def load(self):
        """加载 ONNX 模型，尝试多种后端（优先选内存占用最小的）"""
        # 方案1: onnxruntime (最小内存配置)
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
            opts.intra_op_num_threads = 1
            opts.inter_op_num_threads = 1
            opts.enable_mem_pattern = False
            opts.enable_cpu_mem_arena = False
            # 极限内存优化
            opts.optimized_model_filepath = None
            opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            try:
                self.session = ort.InferenceSession(
                    self.model_path, opts,
                    providers=['CPUExecutionProvider'])
            except Exception:
                self.session = ort.InferenceSession(self.model_path, opts)
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name
            self._run = self._run_ort
            print(f"[OK] ONNX Runtime 加载成功: {self.model_path}")
            return True
        except ImportError:
            print("[INFO] ONNX Runtime 未安装, 尝试 OpenCV DNN...")
        except Exception as e:
            print(f"[WARN] ONNX Runtime 初始化失败: {e}")

        # 方案2: OpenCV DNN (更轻量)
        try:
            import cv2
            self.net = cv2.dnn.readNetFromONNX(self.model_path)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            self._run = self._run_cvdnn
            print(f"[OK] OpenCV DNN 加载成功: {self.model_path}")
            return True
        except Exception as e:
            print(f"[ERR] 无法加载模型: {e}")
            print("[提示] 64MB 内存板子可能OOM, 建议使用 TPU SDK 或 ncnn")
            return False

    def _run_ort(self, blob):
        return self.session.run([self.output_name], {self.input_name: blob})[0]

    def _run_cvdnn(self, blob):
        self.net.setInput(blob)
        return self.net.forward()

    def preprocess(self, img):
        """预处理: BGR→RGB, /255, letterbox, (1,3,640,640)"""
        img, (ratio, dw, dh) = letterbox(img, (self.img_size, self.img_size))
        img = img[:, :, ::-1]  # BGR to RGB
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)
        return img, (ratio, dw, dh)

    def postprocess(self, preds, preprocess_info, orig_shape):
        """
        后处理 YOLO 输出 → 检测框列表
        返回: [{"bbox": [x1,y1,x2,y2], "score": float, "class": str}, ...]
        """
        ratio, dw, dh = preprocess_info
        preds = np.squeeze(preds)  # [N, 6]  or transpose [6, N]

        if preds.ndim == 2 and preds.shape[1] > preds.shape[0]:
            preds = preds.T  # [6, N] → [N, 6]

        # 过滤低置信度
        if preds.ndim == 2:
            mask = preds[:, 4] > self.conf_threshold
            preds = preds[mask]

        if len(preds) == 0:
            return []

        # YOLO 输出格式: [cx, cy, w, h, obj_conf, cls_conf, cls0, cls1, ...]
        # 或: [cx, cy, w, h, conf, cls_id] 合并格式
        if preds.shape[1] == 6:
            boxes_xywh = preds[:, :4]
            scores = preds[:, 4]
            cls_ids = preds[:, 5].astype(int)
        elif preds.shape[1] > 6:
            boxes_xywh = preds[:, :4]
            scores = preds[:, 4]
            cls_scores = preds[:, 5:]
            cls_ids = np.argmax(cls_scores, axis=1)
            scores = scores * np.max(cls_scores, axis=1)
        else:
            boxes_xywh = preds[:, :4]
            scores = preds[:, -1]
            cls_ids = np.zeros(len(preds), dtype=int)

        # 坐标转换
        boxes = xywh2xyxy(boxes_xywh)

        # 去除 padding
        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - dw) / ratio
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - dh) / ratio

        # 裁剪到图像边界
        h, w = orig_shape[:2]
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h)

        # 过滤无效框
        valid = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1]) & (scores > self.conf_threshold)
        boxes = boxes[valid]
        scores = scores[valid]
        cls_ids = cls_ids[valid]

        # NMS
        indices = nms(boxes, scores, self.iou_threshold)

        results = []
        for i in indices:
            cls_id = int(cls_ids[i])
            cls_name = CLASS_NAMES.get(cls_id, f'class_{cls_id}')
            results.append({
                'bbox': boxes[i].round().astype(int).tolist(),
                'score': round(float(scores[i]), 4),
                'class': cls_name,
                'class_id': cls_id,
            })
        return results

    def detect(self, img):
        """完整推理: 输入 BGR 图像, 返回检测结果列表"""
        if self._run is None:
            raise RuntimeError("模型未加载, 请先调用 load()")

        orig_shape = img.shape
        blob, preprocess_info = self.preprocess(img)
        preds = self._run(blob)
        return self.postprocess(preds, preprocess_info, orig_shape)


def process_image(model, img_path, output_dir=None):
    """处理单张图片"""
    img = cv2.imread(img_path)
    if img is None:
        return {'error': f'无法读取图片: {img_path}', 'detections': []}

    t0 = time.time()
    detections = model.detect(img)
    elapsed = time.time() - t0

    # 裁剪检测区域
    crops = []
    for det in detections:
        x1, y1, x2, y2 = det['bbox']
        crop = img[y1:y2, x1:x2]
        crop_path = None
        if output_dir and crop.size > 0:
            os.makedirs(output_dir, exist_ok=True)
            crop_name = f"crop_{x1}_{y1}_{x2}_{y2}.jpg"
            crop_path = os.path.join(output_dir, crop_name)
            cv2.imwrite(crop_path, crop)
        det['crop_path'] = crop_path
        crops.append(crop)

    result = {
        'image': img_path,
        'time': round(elapsed, 4),
        'num_detections': len(detections),
        'detections': detections,
    }

    # 绘制结果
    if output_dir:
        annotated = img.copy()
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{det['class']} {det['score']:.2f}"
            cv2.putText(annotated, label, (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        out_path = os.path.join(output_dir, f"detected_{os.path.basename(img_path)}")
        cv2.imwrite(out_path, annotated)
        result['annotated'] = out_path

    return result


def process_video(model, video_path, output_dir=None, frame_skip=2):
    """处理视频文件"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {'error': f'无法打开视频: {video_path}'}

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    detections_by_frame = {}
    frame_idx = 0
    total_time = 0
    processed = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_skip == 0:
            t0 = time.time()
            dets = model.detect(frame)
            total_time += time.time() - t0
            processed += 1

            if dets:
                detections_by_frame[frame_idx] = dets

        frame_idx += 1

    cap.release()

    return {
        'video': video_path,
        'total_frames': total_frames,
        'processed_frames': processed,
        'frame_skip': frame_skip,
        'avg_time': round(total_time / max(processed, 1), 4),
        'fps': fps,
        'resolution': [width, height],
        'detections_by_frame': detections_by_frame,
    }


def serve_http(model, host='0.0.0.0', port=8080):
    """HTTP 服务模式: 接收图片, 返回检测结果"""
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class DetectHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path == '/detect':
                content_length = int(self.headers['Content-Length'])
                img_data = self.rfile.read(content_length)
                img_array = np.frombuffer(img_data, dtype=np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if img is None:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"error":"invalid image"}')
                    return

                detections = model.detect(img)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'detections': detections,
                    'num_detections': len(detections),
                }).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def do_GET(self):
            if self.path == '/health':
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # 静默模式以减少内存输出

    server = HTTPServer((host, port), DetectHandler)
    print(f"[SERVE] 推理服务运行在 http://{host}:{port}")
    print(f"  POST /detect  发送图片二进制数据, 返回检测结果JSON")
    print(f"  GET  /health  健康检查")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SERVE] 服务已停止")


# ============================================================
# 主入口
# ============================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Milk-V Duo YOLO 推理')
    parser.add_argument('--model', type=str, default='best11_ir9.onnx', help='ONNX 模型路径')
    parser.add_argument('--source', type=str, help='图片或视频路径')
    parser.add_argument('--output', type=str, default='./output', help='输出目录')
    parser.add_argument('--conf', type=float, default=0.5, help='置信度阈值')
    parser.add_argument('--iou', type=float, default=0.45, help='NMS IoU 阈值')
    parser.add_argument('--img-size', type=int, default=640, help='输入尺寸')
    parser.add_argument('--frame-skip', type=int, default=2, help='视频跳帧间隔')
    parser.add_argument('--serve', action='store_true', help='HTTP 服务模式')
    parser.add_argument('--port', type=int, default=8080, help='HTTP 服务端口')

    args = parser.parse_args()

    import cv2

    print(f"=== Milk-V Duo YOLO 推理 ===")
    print(f"  模型: {args.model}")
    print(f"  置信度: {args.conf}")
    print(f"  输入尺寸: {args.img_size}")

    model = YOLOONNX(args.model, conf_threshold=args.conf,
                     iou_threshold=args.iou, img_size=args.img_size)

    if not model.load():
        print("[ERR] 模型加载失败, 退出")
        sys.exit(1)

    if args.serve:
        serve_http(model, port=args.port)
    elif args.source:
        os.makedirs(args.output, exist_ok=True)
        path = args.source.lower()
        if path.endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv')):
            result = process_video(model, args.source, args.output,
                                   frame_skip=args.frame_skip)
        else:
            result = process_image(model, args.source, args.output)

        result_json = os.path.join(args.output, 'result.json')
        with open(result_json, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[DONE] 结果保存至: {result_json}")
        print(f"  检测数: {result.get('num_detections', result.get('processed_frames', 'N/A'))}")
    else:
        print("请指定 --source 或 --serve")
        parser.print_help()
