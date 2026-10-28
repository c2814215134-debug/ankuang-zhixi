import os
import cv2
import time
import numpy as np
import torch
import subprocess
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import re

# 1. 导入依赖
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    print("错误 缺少 ultralytics", flush=True)
    YOLO_AVAILABLE = False

try:
    from paddleocr import PaddleOCR
    OCR_AVAILABLE = True
except ImportError:
    print("错误 缺少 paddleocr", flush=True)
    OCR_AVAILABLE = False

def get_device():
    """获取可用设备"""
    if torch.cuda.is_available():
        return torch.device('cuda:0')
    if torch.backends.mps.is_available():
        return torch.device('mps')
    return torch.device('cpu')

DEVICE = get_device()
print(f"🚀 AI Engine 启动设备: {DEVICE}", flush=True)

class MiningVideoAnalyzer:
    def __init__(self, weights_path="zzbest.pt", font_path="fonts/NotoSansSC-Regular.otf"):
        self.weights_path = weights_path
        self.font_path = font_path
        self.yolo_model = None
        self.ocr = None
        self.state_names = {
            '1': '开孔', '2': '见煤', '3': '验煤', '4': '止煤',
            '5': '终孔', '6': '验孔', '7': '封孔'
        }
        self.generated_files = []
        self.segments = []  # 实时记录识别到的时间戳
        self.processed_segments = []  # 已剪辑完成的片段

        # 验证文件存在
        self._validate_files()

    def _validate_files(self):
        """验证必要文件是否存在"""
        if not os.path.exists(self.weights_path):
            raise FileNotFoundError(f"权重文件缺失: {self.weights_path}")

        if not os.path.exists(self.font_path):
            print(f"警告 字体文件缺失: {self.font_path}, 使用默认字体", flush=True)

    def _initialize_models(self):
        """初始化AI模型"""
        print("工具 开始初始化 AI 模型...", flush=True)

        if not YOLO_AVAILABLE:
            raise RuntimeError("YOLO库未安装")
        if not OCR_AVAILABLE:
            raise RuntimeError("PaddleOCR库未安装")

        if self.yolo_model is None:
            try:
                print(f"加载 加载YOLO模型: {self.weights_path}", flush=True)
                self.yolo_model = YOLO(self.weights_path)
                self.yolo_model.to(DEVICE)
                print("正确 YOLO模型加载成功", flush=True)
            except Exception as e:
                raise RuntimeError(f"YOLO模型加载失败: {e}")

        if self.ocr is None:
            try:
                print("加载 加载OCR模型...", flush=True)
                # 根据PaddleOCR版本选择合适的参数
                try:
                    # 最新版本参数
                    self.ocr = PaddleOCR(use_angle_cls=True, lang="ch", use_gpu=torch.cuda.is_available())
                except TypeError:
                    try:
                        # 次新版本参数
                        self.ocr = PaddleOCR(use_angle_cls=True, lang="ch", gpu_mem=2000)
                    except TypeError:
                        # 旧版本参数（只支持基本功能）
                        self.ocr = PaddleOCR(use_angle_cls=True, lang="ch")
                print("正确 OCR模型加载成功", flush=True)
            except Exception as e:
                print(f"警告 OCR模型加载失败: {e}", flush=True)
                print("工具 尝试使用最小配置...", flush=True)
                # 最终回退方案
                self.ocr = PaddleOCR(lang="ch")

    def _put_chinese_text(self, img, text, position, font_size=30, color=(0, 255, 0)):
        """添加中文文本到图像"""
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(img_rgb)
        draw = ImageDraw.Draw(img_pil)

        try:
            font = ImageFont.truetype(self.font_path, font_size)
        except:
            font = ImageFont.load_default()

        # 描边效果
        stroke_width = 2
        stroke_fill = (0, 0, 0)
        x, y = position

        for dx, dy in [(-stroke_width, 0), (stroke_width, 0), (0, -stroke_width), (0, stroke_width)]:
            draw.text((x+dx, y+dy), text, font=font, fill=stroke_fill)

        draw.text(position, text, font=font, fill=color)
        return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    def _enhance_image_for_ocr(self, img):
        """增强OCR识别的图像预处理"""
        if img is None or img.size == 0:
            return img

        h, w = img.shape[:2]

        if h < 64 or w < 64:
            img = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        enhanced = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)

        edges = cv2.Canny(enhanced, 50, 150)
        enhanced = cv2.addWeighted(enhanced, 0.7, edges, 0.3, 0)

        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

    def _enhance_image_for_ocr_fast(self, img):
        """快速OCR预处理（简化版，用于批量处理）"""
        if img is None or img.size == 0:
            return img

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

    def _process_batch(self, frame_batch, scale):
        """真正的批量处理，大幅提升性能 (已加入 OCR 节流阀)"""
        if not frame_batch:
            return []

        try:
            frames = [fb[0] for fb in frame_batch]
            times = [fb[1] for fb in frame_batch]
            counts = [fb[2] for fb in frame_batch]
            original_frames = [fb[3] for fb in frame_batch]

            batch_results = self.yolo_model(frames, conf=0.15, iou=0.5, verbose=False)

            results = []
            
            # 🌟 核心提速秘籍 1：OCR 节流缓存！
            # 没必要每一帧都去查字典，只要这个 batch（16帧）里有任何一帧看清了字，整个 batch 都共用这个结果！
            cached_state_key = None 

            for idx, (yolo_result, frame, current_time, frame_count, original_frame) in enumerate(zip(batch_results, frames, times, counts, original_frames)):
                # 直接继承缓存里的状态
                current_detected_key = cached_state_key 

                if yolo_result.boxes is not None and len(yolo_result.boxes) > 0:
                    # 🌟 只有当“缓存为空（还没认出字）”时，才去调用极其耗费 CPU 的 PaddleOCR
                    if current_detected_key is None:
                        box = yolo_result.boxes[0]
                        x1, y1, x2, y2 = map(int, box.xyxy[0] / scale)

                        h_img, w_img = original_frame.shape[:2]
                        cx1, cy1 = max(0, x1-10), max(0, y1-10)
                        cx2, cy2 = min(w_img, x2+10), min(h_img, y2+10)
                        sign_img = original_frame[cy1:cy2, cx1:cx2]

                        if sign_img.size > 0:
                            enhanced_img = self._enhance_image_for_ocr_fast(sign_img)
                            ocr_res = self.ocr.ocr(enhanced_img)
                            parsed_texts = self._extract_texts(ocr_res)

                            for txt, score in parsed_texts:
                                if score > 0.3:
                                    state_key = self._match_process_state(txt)
                                    if state_key:
                                        current_detected_key = state_key
                                        cached_state_key = state_key # 🌟 存入缓存，后面的帧直接白嫖！
                                        break

                results.append((current_detected_key, current_time, frame_count, original_frame))

            return results

        except Exception as e:
            print(f"批量处理错误: {e}")
            return []

    def _extract_texts(self, res):
        """万能OCR结果解析器"""
        results = []
        if not res: return results

        try:
            if isinstance(res, list):
                for item in res:
                    if not item: continue
                    if isinstance(item, dict):
                        if 'rec_texts' in item:
                            texts = item['rec_texts']
                            scores = item.get('rec_scores', [])
                            for i, txt in enumerate(texts):
                                score = scores[i] if i < len(scores) else 0.0
                                results.append((txt, score))
                        elif 'text' in item:
                            results.append((item['text'], item.get('score', 1.0)))
                    elif isinstance(item, list):
                        for line in item:
                            if isinstance(line, list) and len(line) == 2:
                                results.append((line[0], line[1][0] if isinstance(line[1], tuple) else 0.5))
            elif isinstance(res, dict):
                if 'rec_texts' in res:
                    texts = res['rec_texts']
                    scores = res.get('rec_scores', [])
                    for i, txt in enumerate(texts):
                        score = scores[i] if i < len(scores) else 0.0
                        results.append((txt, score))
        except Exception as e:
            print(f"OCR结果解析错误: {e}", flush=True)

        return results

    def _match_process_state(self, text):
        """智能匹配工序状态"""
        if not text:
            return None

        clean_text = text.replace(" ", "").replace("\n", "")

        for k, v in self.state_names.items():
            if v in clean_text or clean_text in v:
                return k

        fuzzy_map = {
            '开孔': ['开孔', '开丸', '开f', '开孑', '开子', '开孑'],
            '见煤': ['见煤', '见某', '见m', '见谋', '见煤'],
            '验煤': ['验煤', '验某', '验m', '验谋', '验煤'],
            '止煤': ['止煤', '止某', '止m', '止谋', '止煤'],
            '终孔': ['终孔', '终丸', '终f', '终孑', '终子'],
            '验孔': ['验孔', '验丸', '验f', '验孑', '验子'],
            '封孔': ['封孔', '封丸', '封f', '封孑', '封子']
        }

        for k, variants in fuzzy_map.items():
            for v in self.state_names.values():
                if k in v and any(var in clean_text for var in variants):
                    for num, name in self.state_names.items():
                        if name == v:
                            return num

        return None

    def _cut_video_immediate(self, source_path, output_dir, segment, segment_id, progress_callback=None):
        """立即剪辑单个视频片段（带进度显示）"""
        try:
            state_name = self.state_names.get(segment['state'], "未知工序")
            start_time = segment['start']
            end_time = segment['end']
            duration = end_time - start_time

            if duration < 3:
                print(f"警告 片段过短，忽略: {state_name} ({duration:.1f}s)", flush=True)
                return None

            filename = f"{state_name}_partial_{segment_id}.mp4"
            output_path = os.path.join(output_dir, filename)

            ffmpeg_path = self._get_ffmpeg_path()

            cmd = [
                ffmpeg_path, '-y',
                '-i', source_path,
                '-ss', str(start_time),
                '-to', str(end_time),
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '28',
                '-c:a', 'aac',
                '-strict', 'experimental',
                output_path
            ]

            print(f"实时剪辑 {state_name}: {start_time:.1f}s -> {end_time:.1f}s", flush=True)

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            current_progress = 0

            while True:
                output = process.stderr.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    if 'time=' in output:
                        try:
                            time_start = output.find('time=')
                            if time_start != -1:
                                time_str = output[time_start+5:time_start+17]
                                time_parts = time_str.split(':')
                                if len(time_parts) == 3:
                                    hours, minutes, seconds = map(float, time_parts)
                                    current_seconds = hours * 3600 + minutes * 60 + seconds
                                    progress_percent = int((current_seconds / duration) * 100)

                                    if progress_percent > current_progress and progress_percent < 99:
                                        current_progress = progress_percent
                                        if progress_callback:
                                            progress_callback(f"剪辑 {state_name}: {progress_percent}%", progress_percent)
                                        print(f"剪辑进度 {state_name}: {progress_percent}%", flush=True)
                        except:
                            pass

            if process.returncode == 0 and os.path.exists(output_path):
                file_size = os.path.getsize(output_path) / (1024 * 1024)
                result = {
                    'step': state_name,
                    'filename': filename,
                    'path': output_path,
                    'size': f"{file_size:.2f} MB",
                    'is_partial': True
                }
                print(f"实时剪辑完成: {filename} ({file_size:.2f} MB)", flush=True)
                if progress_callback:
                    progress_callback(f"剪辑 {state_name} 完成", 100)
                return result
            else:
                stderr_output = process.stderr.read()
                print(f"错误 实时剪辑失败: {stderr_output}", flush=True)
                if progress_callback:
                    progress_callback(f"剪辑 {state_name} 失败", 0)
                return None

        except Exception as e:
            print(f"错误 实时剪辑异常: {e}", flush=True)
            if progress_callback:
                progress_callback(f"剪辑 {state_name} 出错: {str(e)}", 0)
            return None

    def _cut_video_with_ffmpeg(self, source_path, output_dir, segments):
        """使用FFmpeg提取视频时间戳（完整剪辑）"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        final_files = []
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        if not segments:
            print("警告 警告：未匹配到任何有效工序文字，未生成任何剪辑片段！", flush=True)
            return final_files

        ffmpeg_path = self._get_ffmpeg_path()

        for i, seg in enumerate(segments):
            try:
                state_name = self.state_names.get(seg['state'], "未知工序")
                start_time = seg['start']
                end_time = seg['end']
                duration = end_time - start_time

                if duration < 3:
                    print(f"警告 片段过短，忽略: {state_name} ({duration:.1f}s)", flush=True)
                    continue

                filename = f"{state_name}_{timestamp}_{i+1}.mp4"
                output_path = os.path.join(output_dir, filename)

                cmd = [
                    ffmpeg_path, '-y',
                    '-i', source_path,
                    '-ss', str(start_time),
                    '-to', str(end_time),
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-crf', '28',
                    '-c:a', 'aac',
                    '-strict', 'experimental',
                    output_path
                ]

                print(f"完整剪辑 {state_name}: {start_time:.1f}s -> {end_time:.1f}s", flush=True)

                process = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )

                if process.returncode == 0 and os.path.exists(output_path):
                    file_size = os.path.getsize(output_path) / (1024 * 1024)
                    final_files.append({
                        'step': state_name,
                        'filename': filename,
                        'path': output_path,
                        'size': f"{file_size:.2f} MB",
                        'is_partial': False
                    })
                    print(f"完整剪辑完成: {filename} ({file_size:.2f} MB)", flush=True)
                else:
                    print(f"错误 完整剪辑失败: {process.stderr}", flush=True)

            except Exception as e:
                print(f"错误 完整剪辑异常: {e}", flush=True)

        return final_files

    def _get_ffmpeg_path(self):
        """获取FFmpeg路径"""
        ffmpeg_paths = [
            'ffmpeg', 
            '/usr/bin/ffmpeg',
            '/usr/local/bin/ffmpeg',
            '/opt/homebrew/bin/ffmpeg',
            os.path.join(os.getcwd(), 'ffmpeg'),
            os.path.join(os.getcwd(), 'backend', 'ffmpeg')
        ]

        for path in ffmpeg_paths:
            try:
                process = subprocess.run([path, '-version'], capture_output=True)
                if process.returncode == 0:
                    print(f"正确 找到FFmpeg: {path}", flush=True)
                    return path
            except:
                continue

        raise RuntimeError("FFmpeg未安装或无法找到")

    # 🌟 这里的缩进已经严格对齐为 4 个空格，属于类的方法
    def process_video(self, source_path, output_dir=None, frame_skip=3, progress_callback=None, stop_event=None):
        """主处理函数（支持暂停和实时剪辑）"""
        if output_dir is None:
            output_dir = os.path.abspath(os.path.join(os.getcwd(), 'raw_videos', 'processed'))

        cap = None
        start_time = time.time()
        segment_counter = 0

        self.segments = []
        self.processed_segments = []
        self.generated_files = []

        try:
            if not os.path.exists(source_path):
                raise FileNotFoundError(f"视频不存在: {source_path}")

            self._initialize_models()

            cap = cv2.VideoCapture(source_path)
            if not cap.isOpened():
                raise RuntimeError("无法打开视频流")

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            video_length = total_frames / fps if fps > 0 else 0

            if video_length > 300:
                frame_skip = max(frame_skip, 20)
            elif video_length > 120:
                frame_skip = max(frame_skip, 15)
            elif video_length > 60:
                frame_skip = max(frame_skip, 10)
            else:
                frame_skip = max(frame_skip, 5)

            print(f"⚡ 超激进跳帧: {frame_skip} (视频长度: {video_length:.1f}s)", flush=True)

            # 🌟 核心提速秘籍 2：极限降维！
            # 对于 YOLOv8 来说，看清标牌轮廓 640 像素是黄金尺寸。
            # 像素面积减少 50%，处理速度直接翻倍！
            target_width = 640

            scale = target_width / width

            batch_size = 16
            frame_batch = []

            frame_count = 0
            current_segment = None
            last_seen_time = 0
            active_state_key = None

            last_cut_time = 0
            cut_interval = 30

            while cap.isOpened():
                if stop_event and stop_event.is_set():
                    print("停止 接收到暂停信号，保存当前进度", flush=True)
                    break

                ret, frame = cap.read()
                if not ret:
                    print(f"完成 视频读取完毕，共 {frame_count} 帧", flush=True)
                    break

                frame_count += 1
                current_time = frame_count / fps if fps > 0 else frame_count / 30

                if frame_count % 100 == 0:
                    elapsed = time.time() - start_time
                    fps_processing = frame_count / elapsed if elapsed > 0 else 0
                    print(f"性能 处理速度: {fps_processing:.1f} fps", flush=True)

                if frame_count % frame_skip == 0:
                    if scale < 1.0:
                        ai_frame = cv2.resize(frame, (target_width, int(height * scale)), interpolation=cv2.INTER_AREA)
                    else:
                        ai_frame = frame

                    frame_batch.append((ai_frame, current_time, frame_count, frame))

                if len(frame_batch) >= batch_size:
                    batch_results = self._process_batch(frame_batch, scale)

                    for current_detected_key, current_time, frame_count, original_frame in batch_results:
                        if current_detected_key:
                            if current_segment is None:
                                start_t = max(0, current_time - 5)
                                current_segment = {'state': current_detected_key, 'start': start_t}
                                print(f"工序开始: {self.state_names[current_detected_key]} 于 {start_t:.1f}s", flush=True)
                            elif current_segment['state'] != current_detected_key:
                                current_segment['end'] = current_time
                                self.segments.append(current_segment)

                                segment_counter += 1
                                result = self._cut_video_immediate(source_path, output_dir, current_segment, segment_counter)
                                if result:
                                    self.processed_segments.append(current_segment)
                                    self.generated_files.append(result)

                                print(f"工序切换: {self.state_names[current_segment['state']]} -> {self.state_names[current_detected_key]}", flush=True)
                                start_t = max(0, current_time - 5)
                                current_segment = {'state': current_detected_key, 'start': start_t}

                            last_seen_time = current_time
                            active_state_key = current_detected_key

                            if current_time - last_cut_time > cut_interval:
                                if current_segment and len(self.segments) > len(self.processed_segments):
                                    pending_segment = self.segments[-1]
                                    pending_segment['end'] = current_time
                                    segment_counter += 1
                                    result = self._cut_video_immediate(source_path, output_dir, pending_segment, segment_counter)
                                    if result:
                                        self.processed_segments.append(pending_segment.copy())
                                        self.generated_files.append(result)
                                        last_cut_time = current_time
                                        print(f"定时保存: 剪辑当前片段", flush=True)
                        else:
                            if (current_segment is not None and current_time - last_seen_time > 60):
                                current_segment['end'] = current_time
                                self.segments.append(current_segment)

                                segment_counter += 1
                                result = self._cut_video_immediate(source_path, output_dir, current_segment, segment_counter)
                                if result:
                                    self.processed_segments.append(current_segment)
                                    self.generated_files.append(result)

                                print(f"工序超时结束: {self.state_names[current_segment['state']]}", flush=True)
                                current_segment = None
                                active_state_key = None

                    frame_batch = []

                # 🌟 核心修复：解除黑屏封印！并且提高帧率，AI 每处理一帧就立刻推给前端！
                if progress_callback and frame_count % frame_skip == 0:
                    progress_percent = int((frame_count / total_frames) * 100) if total_frames > 0 else 0
                    current_state_name = self.state_names.get(active_state_key, "扫描中...")
                    
                    display_frame = cv2.resize(frame, (640, 360))
                    display_frame = self._put_chinese_text(
                        display_frame, 
                        f"AI状态判定: {current_state_name}", 
                        (20, 30), 
                        font_size=24, 
                        color=(0, 255, 0)
                    )

                    progress_callback(frame_count, total_frames, f"{current_state_name}", display_frame)
                    progress_callback(frame_count, total_frames, f"已剪辑: {len(self.generated_files)} 个文件", display_frame)

            if current_segment is not None:
                current_segment['end'] = current_time
                self.segments.append(current_segment)

                segment_counter += 1
                result = self._cut_video_immediate(source_path, output_dir, current_segment, segment_counter)
                if result:
                    self.processed_segments.append(current_segment)
                    self.generated_files.append(result)

                print(f"最后工序结束: {self.state_names[current_segment['state']]}", flush=True)

            if frame_batch:
                batch_results = self._process_batch(frame_batch, scale)
                for current_detected_key, current_time, frame_count, original_frame in batch_results:
                    if current_detected_key:
                        if len(self.segments) == 0 or self.segments[-1]['state'] != current_detected_key:
                            start_t = max(0, current_time - 5)
                            self.segments.append({'state': current_detected_key, 'start': start_t, 'end': current_time})

            total_time = time.time() - start_time
            print(f"统计 处理完成: {frame_count} 帧 / {total_time:.1f}s ({frame_count/total_time:.1f} fps)", flush=True)
            print(f"统计 识别到 {len(self.segments)} 个时间戳，已剪辑 {len(self.generated_files)} 个文件", flush=True)

            if len(self.segments) > len(self.processed_segments):
                unprocessed = [s for s in self.segments if s not in self.processed_segments]
                if unprocessed:
                    print(f"完整剪辑: {len(unprocessed)} 个剩余片段", flush=True)
                    if progress_callback:
                        dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
                        progress_callback(total_frames, total_frames, "完整剪辑剩余片段...", dummy_frame)

                    complete_files = self._cut_video_with_ffmpeg(source_path, output_dir, unprocessed)
                    self.generated_files.extend(complete_files)

        except Exception as e:
            print(f"错误 处理过程中发生错误: {e}", flush=True)
            import traceback
            traceback.print_exc()
            raise e
        finally:
            if cap is not None:
                cap.release()
            print("完成 处理任务结束", flush=True)

        return self.generated_files