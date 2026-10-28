"""
Milk-V Duo 摄像头实时 YOLO 检测
用法:
    python board_camera.py --model best11_ir9.onnx           # USB摄像头
    python board_camera.py --model best11_ir9.onnx --cam 1   # 指定摄像头索引
    python board_camera.py --model best11_ir9.onnx --cam /dev/video0  # CSI摄像头

浏览器打开 http://板子IP:8080 查看实时检测画面
"""
import argparse
import json
import os
import sys
import time
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import cv2

# ============================================================
CLASS_NAMES = {0: 'signage'}
STAGE_NAMES = {'1': '开孔', '2': '见煤', '3': '验煤', '4': '止煤',
               '5': '终孔', '6': '验孔', '7': '封孔'}


def letterbox(img, new_shape=(640, 640), color=(114, 114, 114)):
    shape = img.shape[:2]
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = (int(round(shape[1] * r)), int(round(shape[0] * r)))
    dw, dh = (new_shape[1] - new_unpad[0]) // 2, (new_shape[0] - new_unpad[1]) // 2
    if shape[::-1] != new_unpad:
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    img = cv2.copyMakeBorder(img, dh, new_shape[0] - new_unpad[0] - dh,
                             dw, new_shape[1] - new_unpad[1] - dw,
                             cv2.BORDER_CONSTANT, value=color)
    return img, (r, dw, dh)


def xywh2xyxy(x):
    y = np.copy(x)
    y[:, 0] = x[:, 0] - x[:, 2] / 2
    y[:, 1] = x[:, 1] - x[:, 3] / 2
    y[:, 2] = x[:, 0] + x[:, 2] / 2
    y[:, 3] = x[:, 1] + x[:, 3] / 2
    return y


def nms(boxes, scores, iou_threshold):
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


class YOLODetector:
    """YOLO ONNX 检测器（自动选择后端）"""

    def __init__(self, model_path, conf=0.5, iou=0.45, img_size=640):
        self.model_path = model_path
        self.conf = conf
        self.iou = iou
        self.img_size = img_size
        self.session = None
        self.net = None

    def load(self):
        # 优先 ONNX Runtime
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
            opts.intra_op_num_threads = 1
            opts.inter_op_num_threads = 1
            opts.enable_mem_pattern = False
            opts.enable_cpu_mem_arena = False
            opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            self.session = ort.InferenceSession(self.model_path, opts,
                                                providers=['CPUExecutionProvider'])
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name
            self._backend = 'onnxruntime'
            print(f"[OK] ONNX Runtime 加载成功")
            return True
        except Exception as e:
            print(f"[INFO] ONNX Runtime 不可用 ({e}), 尝试 OpenCV DNN...")

        # 回退 OpenCV DNN
        try:
            self.net = cv2.dnn.readNetFromONNX(self.model_path)
            self._backend = 'opencv_dnn'
            print(f"[OK] OpenCV DNN 加载成功")
            return True
        except Exception as e:
            print(f"[ERR] 模型加载失败: {e}")
            return False

    def detect(self, img):
        """输入 BGR 图像，返回检测结果列表"""
        orig_h, orig_w = img.shape[:2]

        # 预处理
        processed, (ratio, dw, dh) = letterbox(img, (self.img_size, self.img_size))
        blob = processed[:, :, ::-1].astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))[np.newaxis, ...]

        # 推理
        if self._backend == 'onnxruntime':
            preds = self.session.run([self.output_name], {self.input_name: blob})[0]
        else:
            self.net.setInput(blob)
            preds = self.net.forward()

        # 后处理
        preds = np.squeeze(preds)
        if preds.ndim == 2 and preds.shape[1] < preds.shape[0]:
            preds = preds.T

        if len(preds) == 0:
            return []

        # YOLO输出: [cx,cy,w,h, obj_conf, cls0, cls1, ...] 或 [cx,cy,w,h, conf, cls_id]
        if preds.shape[1] == 6:
            boxes_xywh, scores, cls_ids = preds[:, :4], preds[:, 4], preds[:, 5].astype(int)
        else:
            boxes_xywh = preds[:, :4]
            scores = preds[:, 4] * preds[:, 5:].max(axis=1)
            cls_ids = preds[:, 5:].argmax(axis=1)

        mask = scores > self.conf
        boxes_xywh, scores, cls_ids = boxes_xywh[mask], scores[mask], cls_ids[mask]
        if len(boxes_xywh) == 0:
            return []

        boxes = xywh2xyxy(boxes_xywh)
        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - dw) / ratio
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - dh) / ratio
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, orig_w)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, orig_h)

        valid = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
        boxes, scores, cls_ids = boxes[valid], scores[valid], cls_ids[valid]

        indices = nms(boxes, scores, self.iou)

        results = []
        for i in indices:
            cls_id = int(cls_ids[i])
            results.append({
                'bbox': boxes[i].round().astype(int).tolist(),
                'score': round(float(scores[i]), 3),
                'class': CLASS_NAMES.get(cls_id, f'cls_{cls_id}'),
            })
        return results


def draw_detections(img, detections):
    """在图像上绘制检测框"""
    for det in detections:
        x1, y1, x2, y2 = det['bbox']
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"{det['class']} {det['score']:.2f}"
        cv2.putText(img, label, (x1, max(y1 - 5, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    return img


# ============================================================
# MJPEG HTTP 服务器
# ============================================================
MJPEG_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><title>Milk-V Duo 实时检测</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{background:#0d1117;color:#c9d1d9;font-family:Arial;text-align:center;margin:0;padding:10px}
  h2{color:#58a6ff} img{max-width:95vw;border:2px solid #30363d;border-radius:4px}
  .info{color:#8b949e;font-size:13px;margin:8px 0}
  .fps{color:#3fb950;font-weight:bold}
</style></head><body>
<h2>Milk-V Duo YOLO 实时检测</h2>
<p class="info">检测目标: signage (指示牌) | 刷新页面查看最新帧</p>
<p class="info">FPS: <span class="fps" id="fps">--</span></p>
<img id="stream" src="/stream" onload="tick()">
<script>
  var last=Date.now(),cnt=0;
  function tick(){cnt++;var n=Date.now();if(n-last>=2000){document.getElementById('fps').textContent=(cnt/((n-last)/1000)).toFixed(1);last=n;cnt=0}}
</script>
</body></html>"""


class MJPEGServer:
    """轻量级 MJPEG HTTP 服务器"""

    def __init__(self, port=8080):
        self.port = port
        self._latest_jpeg = None  # 最新检测帧

    def update_frame(self, jpeg_bytes):
        self._latest_jpeg = jpeg_bytes

    def start(self):
        from http.server import HTTPServer, BaseHTTPRequestHandler
        server_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/':
                    self._send_html()
                elif self.path == '/stream':
                    self._send_stream()
                elif self.path == '/snapshot':
                    self._send_snapshot()
                elif self.path == '/health':
                    self._send_json({'status': 'ok'})
                else:
                    self.send_response(404); self.end_headers()

            def _send_html(self):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(MJPEG_HTML.encode())

            def _send_snapshot(self):
                jpeg = server_ref._latest_jpeg
                if jpeg is None:
                    self.send_response(204); self.end_headers(); return
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(jpeg)))
                self.end_headers()
                self.wfile.write(jpeg)

            def _send_stream(self):
                self.send_response(200)
                self.send_header('Content-Type',
                                 'multipart/x-mixed-replace; boundary=frame')
                self.end_headers()
                while True:
                    jpeg = server_ref._latest_jpeg
                    if jpeg:
                        try:
                            self.wfile.write(b'--frame\r\n')
                            self.wfile.write(b'Content-Type: image/jpeg\r\n\r\n')
                            self.wfile.write(jpeg)
                            self.wfile.write(b'\r\n')
                        except (BrokenPipeError, ConnectionResetError):
                            break
                    time.sleep(0.05)

            def _send_json(self, data):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def log_message(self, *args):
                pass  # 静默日志减少IO

        self.server = HTTPServer(('0.0.0.0', self.port), Handler)
        print(f"\n[MJPEG] 浏览器打开 http://192.168.42.1:{self.port} 查看实时画面")
        print(f"  按 Ctrl+C 停止服务\n")
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            print("\n[STOP] 服务已停止")


# ============================================================
# 主入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(description='Milk-V Duo 摄像头实时检测')
    parser.add_argument('--model', default='best11_ir9.onnx', help='ONNX模型路径')
    parser.add_argument('--cam', default='0', help='摄像头索引(0,1,2...) 或 /dev/video0')
    parser.add_argument('--conf', type=float, default=0.5, help='置信度阈值')
    parser.add_argument('--port', type=int, default=8080, help='HTTP端口')
    parser.add_argument('--img-size', type=int, default=640, help='输入尺寸')
    parser.add_argument('--skip', type=int, default=1, help='每N帧检测一次(省算力)')

    args = parser.parse_args()

    print("=" * 50)
    print("Milk-V Duo 摄像头 YOLO 实时检测")
    print("=" * 50)

    # 1. 加载模型
    print(f"\n[1] 加载模型: {args.model}")
    detector = YOLODetector(args.model, conf=args.conf, img_size=args.img_size)
    if not detector.load():
        sys.exit(1)

    # 2. 打开摄像头
    print(f"\n[2] 打开摄像头: {args.cam}")
    src = int(args.cam) if args.cam.isdigit() else args.cam
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        # 尝试 V4L2 设备
        for dev in ['/dev/video0', '/dev/video1', '/dev/video2']:
            if os.path.exists(dev):
                cap = cv2.VideoCapture(dev)
                if cap.isOpened():
                    print(f"  自动选择: {dev}")
                    break
    if not cap.isOpened():
        print("[ERR] 无法打开摄像头! 请检查:")
        print("  - USB摄像头是否已插入")
        print("  - 设备路径是否正确 (ls /dev/video*)")
        sys.exit(1)

    # 设置低分辨率以减少内存占用
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 15)
    real_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    real_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"  分辨率: {real_w}x{real_h}")

    # 3. 启动 MJPEG 服务
    print(f"\n[3] 启动 MJPEG HTTP 服务")
    server = MJPEGServer(port=args.port)

    import threading
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()

    # 4. 主循环: 采集 → 检测 → 推流
    print(f"[4] 开始检测循环 (每{args.skip}帧检测一次)...")
    print("-" * 50)

    frame_idx = 0
    fps_times = []
    last_print = time.time()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            frame_idx += 1

            t0 = time.time()

            if frame_idx % args.skip == 0:
                detections = detector.detect(frame)
                frame = draw_detections(frame, detections)
            else:
                detections = []

            # 压缩为 JPEG
            _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            server.update_frame(jpeg.tobytes())

            # FPS 统计
            fps_times.append(time.time() - t0)
            if time.time() - last_print > 5:
                avg = sum(fps_times[-50:]) / min(len(fps_times[-50:]), 50)
                fps = 1.0 / max(avg, 0.001)
                det_str = f" 检测: {len(detections)}个目标" if detections else ""
                print(f"  FPS: {fps:.1f} | 帧: {frame_idx}{det_str}")
                last_print = time.time()

    except KeyboardInterrupt:
        print("\n[STOP] 用户中断")

    cap.release()
    print("[DONE] 摄像头已释放")


if __name__ == '__main__':
    main()
