import sys
import cv2
import numpy as np

np.int = int
import torch
import os
import time
import json  
import requests  
import base64  
import imageio_ffmpeg
import subprocess
from datetime import datetime
from ultralytics import YOLO
from paddleocr import PaddleOCR
from PIL import Image, ImageDraw, ImageFont

from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout,
                            QHBoxLayout, QLabel, QFileDialog, QWidget, QSplitter,
                            QProgressBar, QTextEdit, QGroupBox, QFormLayout,
                            QTabWidget, QTextBrowser, QDialog, QLineEdit,
                            QMessageBox, QCheckBox, QComboBox)  # <-- 加了 QComboBox
from PyQt5.QtGui import QPixmap, QImage, QFont, QIcon, QIntValidator

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QObject, QEvent

# 设置CUDA设备
os.environ['CUDA_VISIBLE_DEVICES'] = '0,1,2,3'
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

print(f"OpenCV CUDA支持: {cv2.cuda.getCudaEnabledDeviceCount() > 0}")
print(f"PyTorch设备: {device}")

def put_chinese_text(img, text, position, font_size=20, color=(0, 255, 0)):

    # 将OpenCV的BGR格式转换为PIL的RGB格式
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_pil = Image.fromarray(img_rgb)
    # 创建绘图对象
    draw = ImageDraw.Draw(img_pil)
    # 尝试加载中文字体
    try:
        # 使用系统字体路径，提高兼容性
        if os.name == 'nt':  # Windows
            font = ImageFont.truetype("C:/Windows/Fonts/simhei.ttf", font_size)
        elif os.name == 'posix':  # Linux/macOS
            if sys.platform == 'darwin':  # macOS
                font = ImageFont.truetype("/Library/Fonts/PingFang.ttc", font_size)
            else:  # Linux
                font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", font_size)
    except:
        # 找不到字体时使用默认字体
        font = ImageFont.load_default()
        print("警告: 未找到中文字体文件，使用默认字体")
    # 绘制文本
    draw.text(position, text, font=font, fill=color)
    # 转回OpenCV格式
    result_img = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
    return result_img

# 1. 视频文件配置对话框（用于设置跳帧阈值）
class VideoFileConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("视频文件配置")
        self.setStyleSheet("""
            QDialog{background:#0F1C3F; color:#E0EFFF;} 
            QLabel{color:#E0EFFF;} 
            QLineEdit{background:#1E3A72; color:#FFFFFF; border:1px solid #4A90E2;} 
            QPushButton{background:#3366CC; color:white; border:2px solid #2855AA; border-radius:4px;}
            QPushButton:hover{background:#4A90E2; border:2px solid #5BA0F2; color:#F0F8FF;}
        """)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # 创建表单布局
        form_layout = QFormLayout()
        
        # 添加跳帧策略阈值参数
        self.frame_skip_edit = QLineEdit("2")  # 视频默认跳帧阈值设为3
        self.frame_skip_edit.setValidator(QIntValidator(1, 15))  # 限制输入1-30的整数
        form_layout.addRow("跳帧策略阈值:", self.frame_skip_edit)
        
        # 添加提示文本
        form_hint = QLabel("提示: 每隔N帧进行一次检测，值越小精度越高，值越大速度越快")
        form_hint.setStyleSheet("color:#A4C8F5;")
        form_layout.addRow("", form_hint)
        
        layout.addLayout(form_layout)
        
        # 确认和取消按钮
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("确定")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.resize(350, 150)
        
    # 获取跳帧阈值
    def get_frame_skip_threshold(self):
        """获取用户设置的跳帧阈值，默认为3"""
        try:
            return int(self.frame_skip_edit.text())
        except ValueError:
            return 2 # 输入无效时使用默认值
# 摄像头配置对话框
class CameraConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RTSP摄像头配置")
        self.setStyleSheet("""
            QDialog{background:#0F1C3F; color:#E0EFFF;} 
            QLabel{color:#E0EFFF;} 
            QLineEdit{background:#1E3A72; color:#FFFFFF; border:1px solid #4A90E2;} 
            QCheckBox{color:#E0EFFF;} 
            QPushButton{background:#3366CC; color:white; border:2px solid #2855AA; border-radius:4px;}
            QPushButton:hover{background:#4A90E2; border:2px solid #5BA0F2; color:#F0F8FF;}
        """)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # 创建表单布局
        form_layout = QFormLayout()
        # ===================== 摄像头基础信息 =====================
        self.camera_id_edit = QLineEdit("ZK-001")  # 编号
        form_layout.addRow("编号:", self.camera_id_edit)

        self.camera_place_edit = QLineEdit("西翼1号钻场")  # 地点
        form_layout.addRow("地点:", self.camera_place_edit)

        self.camera_position_edit = QLineEdit("二号矿井")  # 位置
        form_layout.addRow("位置:", self.camera_position_edit)
        # ==============================================================
        # 原有参数保持不变...
        self.username_edit = QLineEdit("admin")
        form_layout.addRow("用户名:", self.username_edit)
        
        self.password_edit = QLineEdit("zhao1999")
        self.password_edit.setEchoMode(QLineEdit.Password)
        form_layout.addRow("密码:", self.password_edit)
        
        self.show_password_checkbox = QCheckBox("显示密码")
        self.show_password_checkbox.stateChanged.connect(self.toggle_password_visibility)
        form_layout.addRow("", self.show_password_checkbox)
        
        self.ip_edit = QLineEdit("192.168.3.64")
        form_layout.addRow("IP地址:", self.ip_edit)
        
        self.port_edit = QLineEdit("554")
        form_layout.addRow("RTSP端口:", self.port_edit)
        
        self.path_edit = QLineEdit("/stream1")
        form_layout.addRow("路径:", self.path_edit)
        
        # 跳帧策略阈值参数
        self.frame_skip_edit = QLineEdit("2")  # 默认值设为5
        self.frame_skip_edit.setValidator(QIntValidator(1, 15))  # 限制输入1-30的整数
        form_layout.addRow("跳帧策略阈值:", self.frame_skip_edit)
        # 添加提示文本说明该参数作用
        form_hint = QLabel("提示: 每隔N帧进行一次检测，值越小精度越高，值越大速度越快")
        form_hint.setStyleSheet("color:#A4C8F5;")
        form_layout.addRow("", form_hint)
        
        layout.addLayout(form_layout)
        
        # 确认和取消按钮保持不变...
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("确定")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.resize(350, 250)  # 适当增大窗口尺寸以容纳新参数
        
    # 方法：获取跳帧阈值
    def get_frame_skip_threshold(self):
        """获取用户设置的跳帧阈值，默认为5"""
        try:
            return int(self.frame_skip_edit.text())
        except ValueError:
            return 2  # 输入无效时使用默认值      
        
    def toggle_password_visibility(self, state):
        """切换密码显示状态"""
        if state == Qt.Checked:
            self.password_edit.setEchoMode(QLineEdit.Normal)
        else:
            self.password_edit.setEchoMode(QLineEdit.Password)
            
    def get_rtsp_url(self):
        """生成RTSP URL"""
        username = self.username_edit.text()
        password = self.password_edit.text()
        ip = self.ip_edit.text()
        port = self.port_edit.text()
        path = self.path_edit.text()
        # ===================== ：把摄像头配置同步给处理器 =====================
        if hasattr(self.parent(), 'processor'):
            p = self.parent().processor
            p.drill_no = self.camera_id_edit.text().strip()  # 编号 → 钻孔号
            p.drill_location = self.camera_place_edit.text().strip()  # 地点 → 钻场位置
            p.mine_name = self.camera_position_edit.text().strip()  # 位置 → 矿井名
        # ========================================================================
        # 构建RTSP URL
        if port:
            rtsp_url = f"rtsp://{username}:{password}@{ip}:{port}{path}"
        else:
            rtsp_url = f"rtsp://{username}:{password}@{ip}{path}"

        return rtsp_url

class DetectionProcessor:
    """处理目标检测和OCR识别的核心类"""
    def __init__(self, weights_path="weights/best.pt"):
        # ===================== ：摄像头配置字段 =====================
        self.mine_name = "一号矿井"  # 矿井名
        self.drill_no = "ZK-001"  # 钻孔编号
        self.drill_location = "东翼钻场1"  # 钻孔位置
        # ==============================================================
        # ===================== 服务器配置 =====================
        self.server_type = "intranet"
        self.server_ip = "127.0.0.1"
        self.server_port = "2800"
        self.cloud_config = None
        # ======================================================
        self.weights_path = weights_path
        self.yolo_model = None
        self.ocr = None
        self.is_image = False
        #：确保输出目录存在
        self.output_dir = os.path.join(os.getcwd(), "video")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        # 状态变量：初始生成时间戳
        self.current_time = datetime.now().strftime("%Y%m%d-%H%M%S%f")  # %f（微秒），进一步确保唯一

        self.output_writers = {}
        self.current_output = None
        self.last_detected = None

        self.frame_count = 0  # 重置为0，确保计数准确
        #self.detection_states = {str(i): False for i in range(1, 8)}

        # 检测状态
        self.detection_states = {
            '1': False, '2': False, '3': False, '4': False,
            '5': False, '6': False, '7': False
        }
        self.state_names = {
            '1': '开孔', '2': '见煤', '3': '验煤', '4': '止煤',
            '5': '终孔', '6': '验孔', '7': '封孔'
        }
       # ：加载中文字体（优先仓库内置 Noto Sans SC，SIL OFL 可再分发；其次系统 SimHei）
        self.font_path = self._resolve_font_path()
        self.font = None
        self.load_chinese_font()
        # 初始化模型
        self.initialize_models()
    # 【：重置时间戳方法】
    def reset_current_time(self):
        """重新生成当前时间戳，确保新视频输出文件名唯一"""
        self.current_time = datetime.now().strftime("%Y%m%d-%H%M%S%f")  # %f为微秒，避免同一秒内覆盖
    def load_chinese_font(self):
        """加载支持中文的字体"""
        try:
            # 尝试加载指定的中文字体
            if os.path.exists(self.font_path):
                self.font = cv2.FONT_HERSHEY_SIMPLEX  # 备用字体
                print(f"已加载中文字体: {self.font_path}")
            else:
                # 如果字体文件不存在，使用默认字体并警告
                self.font = cv2.FONT_HERSHEY_SIMPLEX
                print(f"警告: 未找到中文字体文件 {self.font_path}，可能导致中文显示异常")
        except Exception as e:
            self.font = cv2.FONT_HERSHEY_SIMPLEX
            print(f"加载字体失败: {e}")

    @staticmethod
    def _resolve_font_path():
        """按优先级解析中文字体：仓库 fonts/ 目录 Noto Sans SC（SIL OFL）优先，
        其次当前目录 SimHei.ttf（系统字体，不随仓库分发）。"""
        for p in [
            os.path.join('fonts', 'NotoSansSC-Regular.otf'),
            os.path.join('..', 'fonts', 'NotoSansSC-Regular.otf'),
            'SimHei.ttf',
        ]:
            if os.path.exists(p):
                return p
        return 'SimHei.ttf'

    def initialize_models(self):
        """初始化YOLO和OCR模型"""
        # 初始化YOLO模型
        if self.yolo_model is None:
            self.yolo_model = YOLO(self.weights_path).to(device)
        
        # 初始化OCR模型
        if self.ocr is None:
            self.ocr = PaddleOCR(use_angle_cls=True, lang="ch", use_gpu=torch.cuda.is_available())

    def initialize_video_writers(self, width, height, fps):
        """初始化视频写入器（改为按需创建，不再一口气建7个空文件）"""
        self.release_writers()
        self.recorded_videos = []  # 记录这次录制了哪些视频文件
        
        # 🔴 核心修改：只把视频的宽高和帧率存起来备用，不在这里创建物理文件
        self.video_width = width
        self.video_height = height
        self.video_fps = fps
        self.output_writers = {} # 清空写入器字典

    def get_or_create_writer(self, state_key):
        """按需获取或创建对应环节的视频写入器"""
        # 如果这个环节是第一次被识别到，字典里还没它的写入器，我们就当场创建！
        if state_key not in self.output_writers:
            state_name = self.state_names.get(state_key, "未知状态")
            output_path = os.path.join(
                self.output_dir,
                f'{state_name}-{self.current_time}.mp4'
            )
            # 建立物理文件
            writer = cv2.VideoWriter(
                output_path,
                cv2.VideoWriter_fourcc(*'mp4v'),  # 依然保持mp4v以便后续FFmpeg转码
                self.video_fps,
                (self.video_width, self.video_height)
            )
            self.output_writers[state_key] = writer
            self.recorded_videos.append(output_path) # 记录到待转码清单
            print(f"🎬 首次检测到【{state_name}】，动态创建视频文件...")
            
        return self.output_writers[state_key]
    def release_writers(self):
        """释放所有视频写入器，并自动转码为网页支持的格式"""
        for key, writer in self.output_writers.items():
            if writer and writer.isOpened():
                writer.release()  # 真正关闭文件
                
        self.output_writers.clear()
        self.current_output = None
        import gc
        gc.collect()

        # 🔴 ：视频释放后，立刻进行网页格式转换
        if hasattr(self, 'recorded_videos') and self.recorded_videos:
            for filepath in self.recorded_videos:
                # 检查文件是否存在且不为空
                if os.path.exists(filepath) and os.path.getsize(filepath) > 1000: 
                    self.convert_to_web_video(filepath)
            self.recorded_videos = [] # 清空记录

    def convert_to_web_video(self, filepath):
        """终极转码：调用 FFmpeg 将视频完美转换为网页前端支持的 H.264"""
        temp_filepath = filepath.replace(".mp4", "_temp.mp4")
        try:
            # 1. 先把 OpenCV 生成的原始视频重命名为 temp
            os.rename(filepath, temp_filepath)
            
            # 🔴 关键绝杀：获取 imageio-ffmpeg 帮我们内置好的 ffmpeg 程序路径
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            
            # 2. 调用 FFmpeg 进行专业网页级转码
            cmd = [
                ffmpeg_exe, "-y", "-i", temp_filepath,
                "-vcodec", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", filepath
            ]
            print(f"⏳ 正在优化网页播放格式: {os.path.basename(filepath)} ...")
            
            # 运行转码命令
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 3. 转码成功，判断新文件是否生成，如果生成则删除临时文件
            if os.path.exists(filepath):
                os.remove(temp_filepath)
                print(f"✅ 格式优化完成，前端可秒开播放！")
                
        except Exception as e:
            print(f"❌ 视频转码失败: {e}")
            # 如果失败，把原文件名字改回来，防止文件丢失
            if os.path.exists(temp_filepath) and not os.path.exists(filepath):
                os.rename(temp_filepath, filepath)
    def reset_all_states(self):
        """完全重置所有检测状态，用于切换检测源时"""
        self.frame_count = 0
        self.last_detected = None  # 清除上一次检测的阶段
        self.detection_states = {k: False for k in self.detection_states.keys()}  # 重置所有阶段状态
        self.current_time = datetime.now().strftime("%Y%m%d-%H%M%S%f")  # 生成新时间戳
        self.release_writers()  # 释放之前的视频写入器
    def process_frame(self, frame, is_image=False):
        """处理单帧图像，进行检测和识别"""
        self.is_image = is_image
        t1 = time.time()

        detected_states = {k: False for k in self.detection_states.keys()}
        current_detected_state = None  # ：记录当前检测到的状态
        
        # 确保模型已初始化
        self.initialize_models()
        
        # 使用YOLO进行目标检测
        results = self.yolo_model(frame, conf=0.9)
        
        # 处理检测结果
        for result in results:
            for box in result.boxes:
                class_id = int(box.cls)
                if self.yolo_model.names[class_id] == 'signage':  
                    # 裁剪指示牌区域
                    print("检测到signage ")
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    sign_image = frame[y1:y2, x1:x2]
                    
                    # 绘制边界框
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    
                    # 使用PaddleOCR进行文字识别
                    ocr_result = self.ocr.ocr(sign_image, det=False)
                    
                    # 处理OCR结果
                    if ocr_result and ocr_result[0]:
                        for line in ocr_result[0]:
                            if line is not None:
                                text = line[0]  # 文本内容
                                confidence = line[1]  # 置信度
                                # 打印识别结果到屏幕
                                #print(f"检测到文本: {text}，置信度: {confidence:.2f}")
                                # 在图像上绘制识别结果
                                # cv2.putText(frame, f"{text}: {confidence:.2f}", 
                                #            (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 
                                #            0.9, (0, 255, 0), 2)
                                # 替换原有的cv2.putText调用
                                # cv2.putText(frame, f"{text}: {confidence:.2f}", 
                                #         (x1, y1 - 10), self.font,  # 使用加载的字体
                                #         0.9, (0, 255, 0), 2)
                                frame = put_chinese_text(
                                    frame, 
                                    f"{text}: {confidence:.2f}", 
                                    (x1, y1 - 10),  # 位置参数
                                    18, # 字体大小（可选）
                                    (0, 255, 0)  # 颜色（可选）
                                )
                                # 更新检测状态
                                for key, name in self.state_names.items():
                                    if name in text:
                                        detected_states[key] = True
                                        current_detected_state = name  # 记录检测到的状态名称
        
        # 计算处理时间
        process_time = time.time() - t1

        
        self.frame_count += 1
        
        # 对于单张图像，不进行视频写入
        if not is_image:
            # 更新输出状态
            for key in ['1', '2', '3', '4', '5', '6', '7']:
                if detected_states[key]:
                    self.current_output = self.output_writers.get(key)
                    self.last_detected = key
                    break
            else:  # 如果没有检测到新状态，使用上一个状态
                if self.last_detected:
                    self.current_output = self.output_writers.get(self.last_detected)
            
            # 写入当前帧到相应的输出文件
            # if self.current_output and self.current_output.isOpened():
            #     self.current_output.write(frame)
        
        # 确定当前状态 - 优先使用本次检测到的状态
        if current_detected_state:
            current_state = current_detected_state
        else:
            current_state = self.state_names.get(self.last_detected, "未检测到状态")
            
        status_info = {
            "处理时间": f"{process_time:.4f}s",
            #"平均时间": avg_time,
            "当前状态": current_state,
            "帧数": self.frame_count
        }
        
        return frame, status_info
    def direct_ocr_recognition(self, frame):
        """直接对整幅图像进行OCR识别"""
        t1 = time.time()
        detected_states = {k: False for k in self.detection_states.keys()}
        all_texts = []  # 存储「文本+置信度」的组合信息（用于界面显示）
        raw_texts = []  # ：存储原始识别文本（用于状态判断）
        current_detected_state = None  # 记录当前检测到的状态
        confidence_threshold = 0.5  # 置信度阈值，过滤低置信度结果
        
        # 确保模型已初始化
        self.initialize_models()
        
        # 直接对整幅图像进行OCR识别
        ocr_result = self.ocr.ocr(frame, det=True)
        
        # 处理OCR结果：遍历每一行识别结果
        if ocr_result and ocr_result[0]:
            for line in ocr_result[0]:
                if line is not None:
                    # 提取原始文本和置信度（PaddleOCR det=True时，格式为 [边界框, [文本, 置信度]]）
                    raw_text = line[1][0]  # 原始识别文本（无额外信息）
                    confidence = line[1][1]  # 置信度
                    bbox = line[0]  # 边界框坐标
                    
                    # 1. 过滤低置信度结果（避免误判）
                    if confidence < confidence_threshold:
                        print(f"低置信度文本过滤: {raw_text}（置信度: {confidence:.2f} < {confidence_threshold}）")
                        continue  # 跳过低置信度文本
                    
                    # 2. 打印并存储识别结果
                    #print(f"检测到文本: {raw_text}，置信度: {confidence:.2f}")
                    # 存储「文本+置信度」用于界面显示
                    all_texts.append(f"{raw_text} (置信度: {confidence:.2f})")
                    # 存储原始文本用于状态判断（避免格式干扰）
                    raw_texts.append(raw_text)
                    
                    # 3. 绘制边界框和识别结果（保持原功能）
                    pts = np.array(bbox, np.int32)
                    pts = pts.reshape((-1, 1, 2))
                    cv2.polylines(frame, [pts], True, (255, 0, 0), 2)
                    # cv2.putText(frame, f"{raw_text}: {confidence:.2f}", 
                    #             (int(bbox[0][0]), int(bbox[0][1]) - 10), 
                    #             cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)
                    # 替换原有的cv2.putText调用
                    # cv2.putText(frame, f"{raw_text}: {confidence:.2f}", 
                    #             (int(bbox[0][0]), int(bbox[0][1]) - 10), 
                    #             self.font,  # 使用加载的字体
                    #             0.9, (255, 0, 0), 2)
                    frame = put_chinese_text(
                        frame, 
                        f"{raw_text}: {confidence:.2f}", 
                        (int(bbox[0][0]), int(bbox[0][1]) - 10),  # 位置参数
                        18, # 字体大小（可选）
                        (255, 0, 0)  # 颜色（可选）
                    )
                    # 4. 关键修复：在当前原始文本中判断是否包含状态名
                    if not current_detected_state:  # 只保留第一个匹配的状态（避免后续覆盖）
                        for key, name in self.state_names.items():
                            if name in raw_text:  # 基于原始文本判断，而非组合字符串
                                detected_states[key] = True
                                current_detected_state = name  # 更新当前检测状态
                                self.last_detected = key  # 同步更新last_detected（确保后续帧沿用）
                                #print(f"匹配到状态: {current_detected_state}（key: {key}）")
                                break  # 找到第一个匹配状态后退出循环，保证优先级
        
        # 5. 确定当前状态：优先用本次检测结果，无则用上次状态
        if current_detected_state:
            current_state = current_detected_state
        else:
            current_state = self.state_names.get(self.last_detected, "未检测到状态")
        
        # 计算处理时间
        process_time = time.time() - t1
        
        # 构造状态信息（补充识别文本列表，用于界面显示）
        status_info = {
            "处理时间": f"{process_time:.4f}s",
            "当前状态": current_state,
            "帧数": self.frame_count,
            "识别文本": all_texts  # 用于ImageDetectionPage显示所有识别结果
        }
        
        return frame, status_info

    def frame_to_base64(self, frame):
        """图片帧转Base64字符串"""
        # 压缩为JPG
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        # 转Base64
        base64_str = base64.b64encode(buffer).decode('utf-8')
        return base64_str

    def send_detection_data(self, frame, process_name, video_filename="", remark=""):
        """
        发送识别数据到服务器（支持内网/云服务器配置）
        """
        try:
            if frame is None:
                print(f"❌ 上传失败：帧为空")
                return False

            # 1. 生成数据
            base64_img = self.frame_to_base64(frame)
            detect_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # =====================  3 个字段（默认值） =====================
            mine_name = self.mine_name
            drill_no = self.drill_no
            drill_location = self.drill_location
            # ==================================================================

            data = {
                "screenshot_base64": base64_img,
                "process_name": process_name,
                "detect_time": detect_time,
                "video_filename": os.path.basename(video_filename) if video_filename else "stream",
                "remark": remark,

                "mine_name": mine_name,
                "drill_no": drill_no,
                "drill_location": drill_location
            }

            # 2. 云服务器参数
            if self.server_type == "cloud" and self.cloud_config is not None:
                data.update(self.cloud_config)

            # 3. 从配置读取地址
            ip = self.server_ip
            port = self.server_port
            #url = f"http://{ip}:{port}/receive"
            url = f"http://{ip}:{port}/api/detection/receive"
            print(f"\n📤 正在上传到服务器：" + url)
            print(f"📦 识别内容：{process_name}")

            headers = {"Content-Type": "application/json"}
            response = requests.post(
                url,
                data=json.dumps(data, ensure_ascii=False),
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                print(f"✅ 上传成功！服务器返回：{response.status_code}")
                return True
            else:
                print(f"❌ 上传失败，状态码：{response.status_code}")
                return False

        except Exception as e:
            print(f"❌ 上传异常：{str(e)}")
            return False

   
# 视频处理线程
class VideoThread(QThread):

    change_pixmap_signal = pyqtSignal(np.ndarray)
    update_status_signal = pyqtSignal(dict)
    processing_complete = pyqtSignal()
    def __init__(self, source, processor, process_frame=True, detection_interval=5):
        super().__init__()
        self.source = source  # 视频文件路径、摄像头索引或RTSP URL
        self.processor = processor
        self.running = False
        self.process_frame = process_frame  # 是否进行检测处理
        self.detection_interval = detection_interval  # 检测间隔帧数
        self.frame_counter = 0  # 帧计数器（从0开始）
        self.last_detected_frame = None  # 保存上一次检测结果
        self.last_status_info = {}  # 保存上一次状态信息
        self.last_detected_state = None  # 保存上一次检测到的状态    

    
    def run(self):
        self.running = True
        cap = cv2.VideoCapture(self.source)
        
        if not cap.isOpened():
            self.update_status_signal.emit({"错误": "无法打开视频源"})
            self.processing_complete.emit()
            return
        
        # 获取视频信息并初始化写入器
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.processor.initialize_video_writers(width, height, fps)
        
        # 重置帧计数器（关键修复：确保从0开始计数）
        self.frame_counter = 0
        self.processor.frame_count = 0
        
        while self.running and cap.isOpened():
            ret, frame = cap.read()
            if ret:
                # 转换为RGB格式用于显示
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # 1. 第一步：先进行识别检测和状态判断（确保状态是最新的）
                if self.process_frame and self.frame_counter % self.detection_interval == 0:
                    processed_frame, status_info = self.processor.process_frame(frame.copy())
                    self.last_detected_frame = processed_frame.copy()
                    self.last_status_info = status_info
                    self.last_detected_state = self.processor.last_detected
                    self.update_status_signal.emit(status_info)
                    processed_rgb = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB)
                    self.change_pixmap_signal.emit(processed_rgb)
                else:
                    # 使用上一次检测结果或原始帧显示
                    if self.last_detected_frame is not None and self.process_frame:
                        annotated_frame = self.last_detected_frame.copy()
                        annotated_rgb = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
                        self.change_pixmap_signal.emit(annotated_rgb)
                        if self.last_status_info:
                            self.last_status_info["帧数"] = self.frame_counter 
                            self.update_status_signal.emit(self.last_status_info)
                    else:
                        self.change_pixmap_signal.emit(rgb_image)
                
                # 2. 第二步：统一在这里将画面写入视频（杜绝同一帧重复写入的Bug！）
                if self.last_detected_state and not self.processor.is_image:
                    # 🔴 核心修改：通过新方法“获取或创建”写入器
                    self.processor.current_output = self.processor.get_or_create_writer(self.last_detected_state)
                    
                    if self.processor.current_output and self.processor.current_output.isOpened():
                        self.processor.current_output.write(frame)
                
                # 帧计数递增
                self.frame_counter += 1
            else:
                break  # 读取失败或结束，退出循环     
        cap.release()
        self.processor.release_writers()
        self.processing_complete.emit()

    def stop(self):
        self.running = False
        # 退出前强制释放
        # self.processor.release_writers()
        self.wait()   
   

# 图像检测页面
class ImageDetectionPage(QWidget):
    def __init__(self, processor, main_window):
        super().__init__()
        self.processor = processor
        self.main_window = main_window  # 保存主窗口实例，用于调用通用函数
        self.current_image = None
        self.setStyleSheet("background:#0F1C3F; color:#E0EFFF;")
        self.init_ui()
        
        # 为图像标签添加尺寸变化事件监听
        self.lbl_original.installEventFilter(self)
        self.lbl_yolo_ocr.installEventFilter(self)
        self.lbl_direct_ocr.installEventFilter(self)

    def init_ui(self):
        # 创建主布局
        main_layout = QVBoxLayout()
        
        # 创建按钮布局（合并按钮）
        button_layout = QHBoxLayout()
        
        # 加载图像按钮
        self.btn_load_image = QPushButton("加载图像")
        self.btn_load_image.clicked.connect(self.load_image)
        button_layout.addWidget(self.btn_load_image)
        # 为加载图像按钮添加样式
        self.btn_load_image.setStyleSheet("""
            QPushButton{background:#3366CC; color:white; border:2px solid #2855AA; border-radius:4px; padding:6px 12px;}
            QPushButton:hover{background:#4A90E2; border:2px solid #5BA0F2; color:#F0F8FF;}
        """)

        # 合并后的处理按钮（同时执行YOLO+OCR和直接OCR）
        self.btn_process_both = QPushButton("运行检测与识别")
        self.btn_process_both.clicked.connect(self.process_both_methods)
        button_layout.addWidget(self.btn_process_both)
        # 为检测按钮添加样式
        self.btn_process_both.setStyleSheet("""
            QPushButton{background:#3366CC; color:white; border:2px solid #2855AA; border-radius:4px; padding:6px 12px;}
            QPushButton:hover{background:#4A90E2; border:2px solid #5BA0F2; color:#F0F8FF;}
        """)
        main_layout.addLayout(button_layout)
        
        # 创建图像显示和信息区域
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧图像显示区域
        left_panel = QVBoxLayout()
        
        # 原始图像显示区域
        self.lbl_original = QLabel("原始图像")
        self.lbl_original.setAlignment(Qt.AlignCenter)
        self.lbl_original.setMinimumSize(300, 400)
        self.lbl_original.setStyleSheet("background:#162952; border:2px solid #4A90E2;")
        left_panel.addWidget(self.lbl_original)
        
        # 检测结果显示区域（上：YOLO+OCR，下：直接OCR）
        results_layout = QHBoxLayout()
        
        self.lbl_yolo_ocr = QLabel("YOLO+OCR结果")
        self.lbl_yolo_ocr.setAlignment(Qt.AlignCenter)
        self.lbl_yolo_ocr.setMinimumSize(300, 400)
        self.lbl_yolo_ocr.setStyleSheet("background:#162952; border:2px solid #4A90E2;")
        
        self.lbl_direct_ocr = QLabel("直接OCR结果")
        self.lbl_direct_ocr.setAlignment(Qt.AlignCenter)
        self.lbl_direct_ocr.setMinimumSize(300, 400)
        self.lbl_direct_ocr.setStyleSheet("background:#162952; border:2px solid #4A90E2;")

        results_layout.addWidget(self.lbl_yolo_ocr)
        results_layout.addWidget(self.lbl_direct_ocr)
        left_panel.addLayout(results_layout)
        
        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        splitter.addWidget(left_widget)
        
        # 右侧信息面板
        right_panel = QVBoxLayout()
        
        # 状态信息
        status_group = QGroupBox("处理状态")
        status_layout = QFormLayout()
        self.lbl_result = QLabel("N/A")
        self.status_process_time = QLabel("N/A")
        #self.status_avg_time = QLabel("N/A")
        self.status_current_state = QLabel("未开始")
        self.status_frame_count = QLabel("0")
        self.status_load_time = QLabel("N/A")  # 加载图像用时
        self.status_yolo_ocr_time = QLabel("N/A")  # YOLO+OCR用时
        self.status_direct_ocr_time = QLabel("N/A")  # 直接OCR用时
        self.status_efficiency = QLabel("N/A")  # 效率提升百分比
        

        status_layout.addRow("加载图像用时:", self.status_load_time)
        status_layout.addRow("YOLO+OCR用时:", self.status_yolo_ocr_time)
        status_layout.addRow("直接OCR用时:", self.status_direct_ocr_time)
        status_layout.addRow("效率提升:", self.status_efficiency)
        status_layout.addRow("处理时间:", self.status_process_time)
        #status_layout.addRow("平均时间:", self.status_avg_time)
        status_layout.addRow("当前状态:", self.status_current_state)
        status_layout.addRow("处理帧数:", self.status_frame_count)
        
        status_group.setLayout(status_layout)
        right_panel.addWidget(status_group)
        
        # 检测到的文本信息
        self.text_info = QTextEdit()
        self.text_info.setReadOnly(True)
        self.text_info.setMinimumHeight(200)
        right_panel.addWidget(QLabel("识别结果:"))
        right_panel.addWidget(self.text_info)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        right_panel.addWidget(self.progress_bar)
        
        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        right_widget.setMinimumWidth(400)
        splitter.addWidget(right_widget)
        
        # 设置分割器比例
        splitter.setSizes([800, 400])
        
        main_layout.addWidget(splitter)
        
        self.setLayout(main_layout)
    
    def convert_cv_to_qt(self, cv_img):
        """将OpenCV图像转换为PyQt可用的图像格式，并按比例缩放以适应显示区域"""
        # 转换色彩空间（OpenCV的BGR到PyQt的RGB）
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        
        # 创建QImage对象
        convert_to_Qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        
        # 获取显示区域的尺寸（标签的大小）
        label_width = self.lbl_original.width()
        label_height = self.lbl_original.height()
        
        # 计算缩放比例，确保图像按比例缩小以适应标签，同时不超过原始尺寸
        scale_width = label_width / w
        scale_height = label_height / h
        scale_factor = min(scale_width, scale_height, 1.0)  # 1.0确保不放大图像
        
        # 计算缩放后的尺寸
        new_width = int(w * scale_factor)
        new_height = int(h * scale_factor)
        
        # 按计算的尺寸缩放图像，保持比例并使用平滑转换
        scaled_image = convert_to_Qt_format.scaled(
            new_width, new_height, 
            Qt.KeepAspectRatio,  # 保持宽高比
            Qt.SmoothTransformation  # 平滑缩放，减少锯齿
        )
        
        return QPixmap.fromImage(scaled_image)
    def eventFilter(self, obj, event):
        """监听标签尺寸变化，重新调整图像大小"""
        # 当标签尺寸变化且有图像时，重新显示图像
        if event.type() == QEvent.Resize and self.current_image is not None:
            if obj == self.lbl_original:
                qt_img = self.convert_cv_to_qt(self.current_image)
                self.lbl_original.setPixmap(qt_img)
            elif obj == self.lbl_yolo_ocr:
                # 重新处理YOLO+OCR图像并显示（假设存在处理后的图像）
                if hasattr(self, 'yolo_processed_image'):
                    qt_img = self.convert_cv_to_qt(self.yolo_processed_image)
                    self.lbl_yolo_ocr.setPixmap(qt_img)
            elif obj == self.lbl_direct_ocr:
                # 重新处理直接OCR图像并显示（假设存在处理后的图像）
                if hasattr(self, 'direct_processed_image'):
                    qt_img = self.convert_cv_to_qt(self.direct_processed_image)
                    self.lbl_direct_ocr.setPixmap(qt_img)
        return super().eventFilter(obj, event)
       
 
    def load_image(self):
        """加载图像文件并预先加载模型，同时清空历史检测结果"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图像文件", "", "图像文件 (*.png *.jpg *.jpeg *.bmp)")
        
        if file_path:
            # 1. 清空检测结果图像输出区域
            self.lbl_yolo_ocr.clear()  # 清空YOLO+OCR结果标签
            self.lbl_yolo_ocr.setText("未处理")  # 显示提示文本，提升用户体验
            self.lbl_direct_ocr.clear()  # 清空直接OCR结果标签
            self.lbl_direct_ocr.setText("未处理")  # 显示提示文本
            
            # 2. 清空检测结果相关的属性引用（避免后续缩放时复用旧图）
            if hasattr(self, 'yolo_processed_image'):
                delattr(self, 'yolo_processed_image')
            if hasattr(self, 'direct_processed_image'):
                delattr(self, 'direct_processed_image')
            
            # 3. 记录开始加载时间
            load_start_time = time.time()
            
            # 4. 加载并显示原始图像
            self.current_image = cv2.imread(file_path)
            if self.current_image is not None:
                # 计算加载用时
                load_time = time.time() - load_start_time
                self.status_load_time.setText(f"{load_time:.4f}s")
                
                # 显示原始图像
                qt_img = self.convert_cv_to_qt(self.current_image)
                self.lbl_original.setPixmap(qt_img)
                
                # 5. 清空文本信息和状态显示（可选，保持界面整洁）
                self.text_info.clear()
                self.lbl_result.setText("准备就绪")
                self.status_yolo_ocr_time.setText("未处理")
                self.status_direct_ocr_time.setText("未处理")
                self.status_efficiency.setText("未计算")
                self.status_current_state.setText("就绪")
                self.progress_bar.setValue(0)
                # 6. ：加载完成后单独执行一次YOLO检测（不保留结果）
                self.preload_yolo_detection()
    def preload_yolo_detection(self):
        """单独执行一次YOLO检测，不保留结果，仅用于提前加载模型和预热"""
        if self.current_image is not None:
            # 执行YOLO检测但不保存结果
            try:
                # 复制图像以避免修改原始图像
                temp_img = self.current_image.copy()
                # 执行检测（结果不保存）
                self.processor.process_frame(temp_img, is_image=True)
                # 预处理完成
                #self.status_current_state.setText("预处理检测完成， ready for analysis")
            except Exception as e:
                self.status_current_state.setText(f"预处理检测失败: {str(e)}") 


    def update_status_info(self, status_info):
        # 更新基础状态信息
        self.status_process_time.setText(status_info.get("处理时间", "N/A"))
        self.status_current_state.setText(status_info.get("当前状态", "未知"))
        self.status_frame_count.setText(str(status_info.get("帧数", 0)))

        # ====================== 图像检测上传（修复版） ======================
        current_state = status_info.get("当前状态", "")
        if current_state and current_state != "未检测到状态":
            source_type = "图像"
            new_text = f"{source_type}检测-阶段: {current_state} ({datetime.now().strftime('%H:%M:%S')})"
            self.text_info.append(new_text)
            self.main_window.truncate_text_edit(self.text_info, max_lines=5)
            try:
                # 只在状态变化时上传一次
                if not hasattr(self, 'last_sent_state'):
                    self.last_sent_state = ""

                if current_state != self.last_sent_state:
                    print(f"\n📷 图像识别成功，准备上传：{current_state}")

                    # 图像直接用当前加载的图
                    frame = self.current_image
                    if frame is None:
                        print("❌ 图像为空，不上传")
                        return

                    # 调用上传
                    self.processor.send_detection_data(
                        frame=frame,
                        process_name=current_state,
                        video_filename="image_detection",
                        remark="图像模式识别上传"
                    )

                    # 记录已上传状态
                    self.last_sent_state = current_state

            except Exception as e:
                print(f"❌ 图像上传失败：{str(e)}")
        # ==================================================================
           


    def process_both_methods(self):
        """同时执行YOLO+OCR和直接OCR，并计算效率提升"""
        # 清空结果区域
        self.text_info.clear()
        self.lbl_yolo_ocr.clear()
        self.lbl_direct_ocr.clear()
        self.lbl_yolo_ocr.setText("处理中...")
        self.lbl_direct_ocr.setText("处理中...")
        # 重置进度条
        self.progress_bar.setValue(0)
        if self.current_image is not None:
                      
            # 执行YOLO+OCR
            yolo_start = time.time()
            yolo_img, yolo_status = self.processor.process_frame(self.current_image.copy(), is_image=True)
            self.yolo_processed_image = yolo_img  # 保存处理后的图像引用
          
            yolo_time = time.time() - yolo_start
            self.status_yolo_ocr_time.setText(f"{yolo_time:.4f}s")
            
            # 显示YOLO+OCR结果
            qt_yolo_img = self.convert_cv_to_qt(yolo_img)
            self.lbl_yolo_ocr.setPixmap(qt_yolo_img)
            
            # 更新进度
            self.progress_bar.setValue(50)
            
            # 执行直接OCR
            direct_start = time.time()
            direct_img, direct_status = self.processor.direct_ocr_recognition(self.current_image.copy())
            self.direct_processed_image = direct_img  # 保存处理后的图像引用
           
            direct_time = time.time() - direct_start
            self.status_direct_ocr_time.setText(f"{direct_time:.4f}s")
            
            # 显示直接OCR结果
            qt_direct_img = self.convert_cv_to_qt(direct_img)
            self.lbl_direct_ocr.setPixmap(qt_direct_img)
            
            # 计算效率提升百分比
            # 计算效率提升百分比并设置红色显示
            if direct_time > 0:
                efficiency = ((direct_time - yolo_time) / direct_time) * 100
                # 设置为红色显示
                self.status_efficiency.setText(f"<span style='color: red; font-weight: bold;'>{efficiency:.2f}%</span>")
                # 允许HTML格式
                self.status_efficiency.setTextFormat(Qt.RichText)
            else:
                self.status_efficiency.setText("无法计算")
            
            # 更新状态信息
            self.update_status_info(direct_status)
             # 完成进度
            self.progress_bar.setValue(100)


# 视频检测页面
class VideoDetectionPage(QWidget):
    def __init__(self, processor, main_window):
        super().__init__()
        self.processor = processor
        self.main_window = main_window
        self.video_thread = None
        self.total_frames = 0
        self.detection_start_time = None
        self.is_rtsp_stream = False
        self.setStyleSheet("background:#0F1C3F; color:#E0EFFF;")
        self.init_ui()
        
    def init_ui(self):
        # 创建主布局
        main_layout = QVBoxLayout()
        
        # 创建按钮布局
        button_layout = QHBoxLayout()
        
        # 加载视频按钮
        self.btn_load_video = QPushButton("加载视频文件")
        self.btn_load_video.clicked.connect(self.load_video)
        button_layout.addWidget(self.btn_load_video)
        self.btn_load_video.setStyleSheet("""
                    QPushButton{background:#3366CC; color:white; border:2px solid #2855AA; border-radius:4px; padding:6px 12px;}
                    QPushButton:hover{background:#4A90E2; border:2px solid #5BA0F2; color:#F0F8FF;}
                """)
        # 加载摄像头按钮
        self.btn_load_camera = QPushButton("加载RTSP摄像头")
        self.btn_load_camera.clicked.connect(self.load_camera)
        button_layout.addWidget(self.btn_load_camera)
        self.btn_load_camera.setStyleSheet("""
                     QPushButton{background:#3366CC; color:white; border:2px solid #2855AA; border-radius:4px; padding:6px 12px;}
                     QPushButton:hover{background:#4A90E2; border:2px solid #5BA0F2; color:#F0F8FF;}
                 """)
        # 正确定义暂停/重新检测按钮
        self.btn_toggle_detection = QPushButton("暂停检测")
        self.btn_toggle_detection.clicked.connect(self.toggle_detection)
        self.btn_toggle_detection.setEnabled(False)
        button_layout.addWidget(self.btn_toggle_detection)

        self.btn_toggle_detection.setStyleSheet("""
                             QPushButton{background:#3366CC; color:white; border:2px solid #2855AA; border-radius:4px; padding:6px 12px;}
                             QPushButton:hover{background:#4A90E2; border:2px solid #5BA0F2; color:#F0F8FF;}
                         """)
        # 停止按钮
        self.btn_stop = QPushButton("停止")
        self.btn_stop.clicked.connect(self.stop_processing)
        self.btn_stop.setEnabled(False)
        button_layout.addWidget(self.btn_stop)
        self.btn_stop.setStyleSheet("""
                             QPushButton{background:#3366CC; color:white; border:2px solid #2855AA; border-radius:4px; padding:6px 12px;}
                             QPushButton:hover{background:#4A90E2; border:2px solid #5BA0F2; color:#F0F8FF;}
                         """)
        # 打开输出文件夹按钮
        self.btn_open_folder = QPushButton("打开输出文件夹")
        self.btn_open_folder.clicked.connect(self.open_output_folder)
        button_layout.addWidget(self.btn_open_folder)
        self.btn_open_folder.setStyleSheet("""
                                     QPushButton{background:#3366CC; color:white; border:2px solid #2855AA; border-radius:4px; padding:6px 12px;}
                                     QPushButton:hover{background:#4A90E2; border:2px solid #5BA0F2; color:#F0F8FF;}
                                 """)
        main_layout.addLayout(button_layout)
        
        # 创建视频显示和信息区域
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧视频显示区域
        video_panel = QVBoxLayout()
        
        self.lbl_video = QLabel("视频/摄像头画面")
        self.lbl_video.setAlignment(Qt.AlignCenter)
        self.lbl_video.setMinimumSize(800, 600)
        self.lbl_video.setStyleSheet("background:#162952; border:2px solid #4A90E2;")
        video_panel.addWidget(self.lbl_video)
        
        video_widget = QWidget()
        video_widget.setLayout(video_panel)
        splitter.addWidget(video_widget)
        
        # 右侧信息面板
        right_panel = QVBoxLayout()
        
        # 状态信息 - 扩展统计信息
        status_group = QGroupBox("处理状态与统计")
        status_layout = QFormLayout()
        
        self.status_process_time = QLabel("N/A")
        #self.status_avg_time = QLabel("N/A")
        self.status_current_state = QLabel("未开始")
        self.status_frame_count = QLabel("0")
        
        # 总帧数显示
        self.status_total_frames = QLabel("0")
        # 当前帧/总帧数显示
        self.status_current_frame = QLabel("0/0")
        # 总检测时长
        self.status_total_duration = QLabel("00:00:00")
        # 单帧平均处理时长
        #self.status_avg_frame_time = QLabel("0.000s")
        
        # 添加新的状态项到布局
        status_layout.addRow("总帧数:", self.status_total_frames)
        status_layout.addRow("当前帧:", self.status_current_frame)
        status_layout.addRow("处理时间:", self.status_process_time)
        #status_layout.addRow("平均帧处理时间:", self.status_avg_frame_time)
        status_layout.addRow("总检测时长:", self.status_total_duration)
        status_layout.addRow("当前状态:", self.status_current_state)
        
        status_group.setLayout(status_layout)
        right_panel.addWidget(status_group)

        # 检测到的文本信息
        self.text_info = QTextEdit()
        self.text_info.setReadOnly(True)
        self.text_info.setMinimumHeight(200)
        right_panel.addWidget(QLabel("识别结果:"))
        right_panel.addWidget(self.text_info)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        right_panel.addWidget(self.progress_bar)
        
        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        right_widget.setMinimumWidth(400)
        splitter.addWidget(right_widget)
        
        # 设置分割器比例
        splitter.setSizes([800, 400])
        
        main_layout.addWidget(splitter)
        
        self.setLayout(main_layout)

    def open_output_folder(self):
        """打开当前输出文件夹（自动匹配视频/摄像头）"""
        import subprocess

        # 直接获取处理器当前正在使用的输出目录
        output_dir = self.processor.output_dir

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # 打开对应文件夹
        if os.name == 'nt':
            os.startfile(output_dir)
        else:
            subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', output_dir])

    def load_video(self):
        """加载视频文件，跳帧参数配置"""
        self.stop_processing()
        
        # 【修复1：强制重置RTSP流标记，确保视频文件使用静态帧数逻辑】
        self.is_rtsp_stream = False  # 关键：切换到视频文件时重置为False
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "", "视频文件 (*.mp4 *.avi *.mov *.mkv)")
        
        if file_path:
            # 提前读取视频总帧数，避免线程争抢
            cap = cv2.VideoCapture(file_path)
            if cap.isOpened():
                self.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.release()  # 立即释放，避免占用
            else:
                self.total_frames = 0  # 读取失败设为0

            # 显示视频配置对话框，获取跳帧阈值
            dialog = VideoFileConfigDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                frame_skip_threshold = dialog.get_frame_skip_threshold()
                # 启动视频处理，传入用户设置的跳帧阈值
                self.start_video_processing(file_path, frame_skip_threshold)

    def load_camera(self):
        """加载RTSP摄像头，确保完全重置之前的视频检测状态"""
        self.stop_processing()  # 先停止任何正在运行的处理
        
        # 【关键修复1：完全重置处理器状态，包括清除历史检测阶段】
        self.processor.reset_all_states()  # 重置所有检测状态
        self.processor.reset_current_time()  # 生成新的时间戳，避免文件名冲突
        
        # 显示摄像头配置对话框
        dialog = CameraConfigDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            rtsp_url = dialog.get_rtsp_url()
            frame_skip_threshold = dialog.get_frame_skip_threshold()
            
            # 测试RTSP连接
            test_cap = cv2.VideoCapture(rtsp_url)
            if not test_cap.isOpened():
                QMessageBox.critical(self, "连接失败", "无法连接到RTSP摄像头，请检查配置！")
                return
            test_cap.release()
            
            # 启动RTSP处理时强制重置相关参数
            self.start_video_processing(
                rtsp_url, 
                frame_skip_threshold,
                width=640,  # RTSP默认宽度
                height=480, # RTSP默认高度
                fps=25.0    # RTSP默认帧率
            )

    def start_video_processing(self, source, frame_skip_threshold=2, width=640, height=480, fps=25.0):
        saved_total_frames = self.total_frames
        self.reset_detection_state()

        if not self.is_rtsp_stream and isinstance(source, str):
            self.total_frames = saved_total_frames

        self.is_rtsp_stream = (isinstance(source, str) and source.lower().startswith("rtsp://")) or (
            isinstance(source, int))

        if not self.is_rtsp_stream and isinstance(source, str):
            # ===================== 【修复：以视频文件名创建文件夹】 =====================
            video_name = os.path.splitext(os.path.basename(source))[0]
            # 输出到项目目录下的 video / 视频文件名 / ...
            target_folder = os.path.join(os.getcwd(), "video", video_name)

            # 自动创建文件夹
            if not os.path.exists(target_folder):
                os.makedirs(target_folder, exist_ok=True)

            # 让处理器把文件写入这个文件夹
            self.processor.output_dir = target_folder
            # ==========================================================================

            self.processor.reset_current_time()
            self.processor.initialize_video_writers(width, height, fps)

            if self.total_frames == 0:
                self.status_total_frames.setText("未知")
            else:
                self.status_total_frames.setText(str(self.total_frames))
        else:
            self.total_frames = 0
            self.status_total_frames.setText("实时流")
            
            # 🔴 核心修改：动态拼接文件夹名称 (编号_地点)
            # 例如：ZK-001_西翼1号钻场
            folder_name = f"{self.processor.drill_no}_{self.processor.drill_location}"
            
            # 将输出目录指向 video/编号_地点
            self.processor.output_dir = os.path.join(os.getcwd(), "video", folder_name)

            # 自动创建嵌套的文件夹结构（exist_ok=True 会自动建好外层的 video 文件夹）
            if not os.path.exists(self.processor.output_dir):
                os.makedirs(self.processor.output_dir, exist_ok=True)
                
        self.detection_start_time = time.time()
        detection_interval = frame_skip_threshold

        self.video_thread = VideoThread(
            source,
            self.processor,
            detection_interval=detection_interval
        )
        self.video_thread.change_pixmap_signal.connect(self.update_video_frame)
        self.video_thread.update_status_signal.connect(self.update_status_info)
        self.video_thread.processing_complete.connect(self.processing_finished)
        self.video_thread.start()
        self.update_button_states(running=True)

    def reset_detection_state(self):
        """重置所有检测状态信息，包括阶段状态显示"""
        self.total_frames = 0
        self.status_total_frames.setText("0")
        self.detection_start_time = None
        self.status_process_time.setText("N/A")
        self.status_total_duration.setText("00:00:00")
        self.status_current_state.setText("未开始")
        self.status_current_frame.setText("0/0")
        self.progress_bar.setValue(0)
        self.text_info.clear()  # 清空历史阶段信息
        
        # 【关键修复3：重置处理器内部的帧计数和检测状态】
        self.processor.frame_count = 0
        self.processor.last_detected = None
        self.processor.detection_states = {k: False for k in self.processor.detection_states.keys()}


    def update_video_frame(self, cv_img):
        """更新视频帧显示"""
        qt_img = QPixmap.fromImage(
            QImage(cv_img.data, cv_img.shape[1], cv_img.shape[0], 
                  cv_img.shape[1] * 3, QImage.Format_RGB888))
        # 缩放图像以适应标签大小
        scaled_img = qt_img.scaled(
            self.lbl_video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl_video.setPixmap(scaled_img)
    def toggle_detection(self):
        """切换检测状态：暂停/重新检测"""
        if self.video_thread is not None and self.video_thread.isRunning():
            # 切换process_frame状态
            self.video_thread.process_frame = not self.video_thread.process_frame
            
            # 更新按钮文本和状态信息
            if self.video_thread.process_frame:
                self.btn_toggle_detection.setText("暂停检测")
                self.status_current_state.setText(f"重新开始检测 - {self.status_current_state.text()}")
            else:
                self.btn_toggle_detection.setText("重新检测")
                self.status_current_state.setText(f"已暂停 - {self.status_current_state.text()}")
                
            # 记录状态变化
            state_text = "重新开始检测" if self.video_thread.process_frame else "暂停检测"
            self.text_info.append(f"{state_text} ({datetime.now().strftime('%H:%M:%S')})")
            self.main_window.truncate_text_edit(self.text_info, max_lines=5)

    def update_status_info(self, status_info):
        # 更新基础状态信息
        self.status_process_time.setText(status_info.get("处理时间", "N/A"))
        self.status_current_state.setText(status_info.get("当前状态", "未知"))

        # 获取当前帧数（带安全校验）
        current_frame = status_info.get("帧数", 0)
        if not isinstance(current_frame, int) or current_frame < 0:
            current_frame = 0
        self.status_frame_count.setText(str(current_frame))

        # 更新当前帧/总帧数显示 - 重点修复RTSP部分
        if self.is_rtsp_stream:
            self.status_total_frames.setText("实时流")
            self.status_current_frame.setText(f"{current_frame}/实时流")
            self.progress_bar.setValue(current_frame % 100)
        else:
            if self.total_frames > 0:
                display_frame = min(current_frame, self.total_frames)
                self.status_current_frame.setText(f"{display_frame}/{self.total_frames}")
                progress = int((display_frame / self.total_frames) * 100)
                self.progress_bar.setValue(progress if progress <= 100 else 100)

                if display_frame >= self.total_frames:
                    self.stop_processing()
                    self.status_current_state.setText("视频已播放完毕")
            else:
                self.status_current_frame.setText(f"{current_frame}/未知")

        # 计算并更新总检测时长
        if self.detection_start_time:
            elapsed_time = time.time() - self.detection_start_time
            hours, remainder = divmod(int(elapsed_time), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.status_total_duration.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

        # 更新文本信息
        current_state = status_info.get("当前状态", "")
        if current_state and current_state != "未检测到状态":
            source_type = "摄像头" if self.is_rtsp_stream else "本地视频"
            new_text = f"{source_type}检测-阶段: {current_state} ({datetime.now().strftime('%H:%M:%S')})"
            self.text_info.append(new_text)
            self.main_window.truncate_text_edit(self.text_info, max_lines=5)

            # ====================== 【上传：只在这里加，不影响识别】 ======================
            try:
                if not hasattr(self, 'last_sent_state'):
                    self.last_sent_state = ""

                current_state = status_info.get("当前状态", "")
                if current_state != self.last_sent_state and current_state != "未检测到状态":

                    frame = None
                    if self.video_thread:
                        frame = self.video_thread.last_detected_frame

                    if frame is None:
                        print(f"⚠ 帧为空，无法上传")
                        return

                    ok = self.processor.send_detection_data(
                        frame=frame,
                        process_name=current_state,
                        video_filename=self.video_thread.source if self.video_thread else "rtsp_camera",
                        remark="视频实时识别"
                    )
                    self.last_sent_state = current_state

            except Exception as e:
                print(f"上传异常：{e}")
            # ============================================================================
    def start_detection(self):
        """开始目标检测"""
        # 如果有视频线程在运行，则确保处理帧
        if self.video_thread is not None and self.video_thread.isRunning():
            self.video_thread.process_frame = True
    def stop_processing(self):
        """停止处理并彻底清理资源（延迟重置状态）"""
        if self.video_thread is not None and self.video_thread.isRunning():
            self.video_thread.stop()
            self.video_thread = None
        
        # 关键修复：先释放写入器，暂不重置状态（保留信息供结束窗口使用）
        # self.processor.release_writers()  # 仅释放视频写入器
        self.update_button_states(running=False)
        self.lbl_video.setText("视频/摄像头画面")
    

    def processing_finished(self):
        """处理完成时调用（先弹窗口，再重置状态）"""
        self.update_button_states(running=False)
        self.status_current_state.setText("处理完成")
        
        # 关键修复：主动判断是否为视频文件（不依赖线程的source属性）
        is_video_file = not self.is_rtsp_stream and self.total_frames > 0
        
        # 仅对视频文件检测结束显示提示
        if is_video_file:
            output_dir = os.path.join(os.getcwd(), "video")
            msg = QMessageBox(self)
            msg.setWindowTitle("检测完成")
            msg.setIcon(QMessageBox.Information)
            
            # 统计当前批次生成的文件
            file_count = 0
            if os.path.exists(output_dir):
                current_time = self.processor.current_time
                for file in os.listdir(output_dir):
                    if current_time in file:
                        file_count += 1
            
            # 显示完整的处理信息（包含处理时间、帧数）
            message = f"视频文件检测已完成！\n\n"
            message += f"总帧数：{self.total_frames}\n"
            message += f"处理时间：{self.status_process_time.text()}\n"
            message += f"总检测时长：{self.status_total_duration.text()}\n"
            message += f"共生成 {file_count} 个关键工序视频文件\n"
            message += f"文件已保存至：\n{output_dir}"
            
            msg.setText(message)
            msg.addButton(QPushButton("打开文件夹"), QMessageBox.ActionRole)
            msg.addButton(QPushButton("确定"), QMessageBox.AcceptRole)
            
            # 处理按钮点击
            result = msg.exec_()
            if result == 0:
                self.open_output_folder()
        
        # 关键修复：弹出窗口后，再重置所有状态（避免信息丢失）
        self.reset_detection_state()
    def update_button_states(self, running):
        """更新按钮状态"""
        self.btn_stop.setEnabled(running)
        self.btn_load_video.setEnabled(not running)
        self.btn_load_camera.setEnabled(not running)
        self.btn_toggle_detection.setEnabled(running)  # 只有在运行时才启用暂停/重新检测按钮
        
        # 如果开始运行，设置按钮初始文本为"暂停检测"
        if running and self.btn_toggle_detection.text() != "暂停检测":
            self.btn_toggle_detection.setText("暂停检测")
# ====================== 服务器配置页面 ======================
class ServerConfigPage(QWidget):
    def __init__(self, processor):
        super().__init__()
        self.processor = processor
        self.setStyleSheet("background:#0F1C3F; color:#E0EFFF;")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # 标题
        title = QLabel("<h2>服务器上传配置</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 服务器类型选择
        self.server_type = QComboBox()
        self.server_type.addItems(["内网服务器", "云服务器"])
        self.server_type.currentTextChanged.connect(self.on_server_type_change)
        layout.addWidget(QLabel("服务器类型："))
        layout.addWidget(self.server_type)

        # 内网配置
        self.group_intranet = QGroupBox("内网服务器配置")
        form1 = QFormLayout()
        self.ip_intranet = QLineEdit("127.0.0.1")
        self.port_intranet = QLineEdit("2800")
        form1.addRow("IP地址：", self.ip_intranet)
        form1.addRow("端口：", self.port_intranet)
        self.group_intranet.setLayout(form1)

        # 云服务器配置
        self.group_cloud = QGroupBox("云服务器配置（默认隐藏）")
        form2 = QFormLayout()
        self.ip_cloud = QLineEdit("")
        self.port_cloud = QLineEdit("")
        self.token = QLineEdit("")  # 访问令牌
        self.app_id = QLineEdit("")  # 应用ID
        self.api_key = QLineEdit("")  # API密钥
        form2.addRow("云服务器IP：", self.ip_cloud)
        form2.addRow("端口：", self.port_cloud)
        form2.addRow("应用ID（AppID）：", self.app_id)
        form2.addRow("API密钥：", self.api_key)
        form2.addRow("访问令牌Token：", self.token)
        self.group_cloud.setLayout(form2)
        self.group_cloud.setVisible(False)

        layout.addWidget(self.group_intranet)
        layout.addWidget(self.group_cloud)

        # 保存按钮
        self.btn_save = QPushButton("保存配置")
        self.btn_save.clicked.connect(self.save_config)
        layout.addWidget(self.btn_save)
        self.btn_save.setStyleSheet("""
              QPushButton{background:#3366CC; color:white; border:2px solid #2855AA; border-radius:4px; padding:6px 12px;}
              QPushButton:hover{background:#4A90E2; border:2px solid #5BA0F2; color:#F0F8FF;}
              """)
        # 状态提示
        self.status = QLabel("状态：未配置")
        self.status.setStyleSheet("color:#4A90E2;")
        layout.addWidget(self.status)

        layout.addStretch()
        self.setLayout(layout)

    def on_server_type_change(self, text):
        if text == "内网服务器":
            self.group_intranet.setVisible(True)
            self.group_cloud.setVisible(False)
        else:
            self.group_intranet.setVisible(False)
            self.group_cloud.setVisible(True)

    def save_config(self):
        try:
            server_type = self.server_type.currentText()

            if server_type == "内网服务器":
                ip = self.ip_intranet.text().strip()
                port = self.port_intranet.text().strip()
                self.processor.server_type = "intranet"
                self.processor.server_ip = ip
                self.processor.server_port = port
                self.processor.cloud_config = None
            else:
                ip = self.ip_cloud.text().strip()
                port = self.port_cloud.text().strip()
                app_id = self.app_id.text().strip()
                api_key = self.api_key.text().strip()
                token = self.token.text().strip()
                self.processor.server_type = "cloud"
                self.processor.server_ip = ip
                self.processor.server_port = port
                self.processor.cloud_config = {
                    "app_id": app_id,
                    "api_key": api_key,
                    "token": token
                }

            self.status.setText(f"✅ 配置成功：{server_type}")
            self.status.setStyleSheet("color:#5CDB95;")

        except Exception as e:
            self.status.setText(f"❌ 保存失败：{str(e)}")
            self.status.setStyleSheet("color:#FF6B6B;")
# 开发者信息页面
class DeveloperInfoPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background:#0F1C3F; color:#E0EFFF;")
        self.init_ui()
        
    def init_ui(self):
        # 创建主布局
        main_layout = QVBoxLayout()
        
        # 创建信息显示区域
        info_browser = QTextBrowser()
        info_browser.setReadOnly(True)
        info_browser.setOpenExternalLinks(True)
        info_browser.setStyleSheet("background:#162952; color:#E0EFFF; border:1px solid #4A90E2;")
        # 设置中文字体
        font = QFont("Noto Sans SC, Microsoft YaHei, SimHei")
        info_browser.setFont(font)
        
        # 开发者信息
        info_html = """
        <h2 style='text-align:center; color:#A4C8F5;'>开发者信息</h2>
        <hr style='border-color:#4A90E2;'>
        <h3 style='color:#A4C8F5;'>项目名称</h3>
        <p>煤矿钻场视频智能剪辑与数据管理平台———Client端</p>
        <h3 style='color:#A4C8F5;'>开发团队</h3>
        <p>河南理工大学智能矿山技术研发组</p>
        <h3 style='color:#A4C8F5;'>系统简介</h3>
        <p>本系统基于YOLO目标检测算法和PaddleOCR文字识别技术，实现对煤矿钻场施工过程中关键工序的自动识别、视频剪辑和关键环节归档。</p>
        <p>系统能够自动识别"开孔"、"见煤"、"验煤"、"止煤"、"终孔"、"验孔"和"封孔"七个关键工序状态，并根据识别结果自动剪辑视频，提高工作效率。</p>
        <h3 style='color:#A4C8F5;'>技术架构</h3>
        <ul>
            <li>目标检测：YOLOv11</li>
            <li>文字识别：PaddleOCR</li>
            <li>图形界面：PyQt5</li>
            <li>图像处理：OpenCV</li>
            <li>深度学习框架：PyTorch</li>
        </ul>
        <h3 style='color:#A4C8F5;'>版本信息</h3>
        <p>版本号：v1.0.0</p>
        <p>发布日期：2026年1月</p>
        <h3 style='color:#A4C8F5;'>联系方式</h3>
        <p>邮箱：2814215134@qq.com</p>
        """
        info_browser.setHtml(info_html)
        main_layout.addWidget(info_browser)
        
        self.setLayout(main_layout)

# 主窗口类

class IntelligentMiningEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.processor = DetectionProcessor()  # 初始化检测处理器
        self.init_ui()

    # -------------------------- 全局通用文本截断函数 --------------------------
    def truncate_text_edit(self, text_edit, max_lines=5):
        """
        通用文本截断工具：仅保留QTextEdit的最后N行文本
        :param text_edit: 目标QTextEdit控件（图像/视频检测页面的文本框）
        :param max_lines: 最大显示行数，默认5行
        """
        # 1. 获取当前所有非空文本行（过滤空行，避免空行占用行数）
        current_text = text_edit.toPlainText()
        valid_lines = [line.strip() for line in current_text.split('\n') if line.strip()]
        
        # 2. 若行数超出限制，保留最后max_lines行
        if len(valid_lines) > max_lines:
            truncated_lines = valid_lines[-max_lines:]  # 取最后N行
            new_text = '\n'.join(truncated_lines)       # 重新拼接文本
            text_edit.setPlainText(new_text)            # 更新文本框
            
            # 3. 光标自动定位到最后一行（优化用户体验，看到最新内容）
            text_cursor = text_edit.textCursor()
            text_cursor.movePosition(text_cursor.End)
            text_edit.setTextCursor(text_cursor)
    # ---------------------------------------------------------------------------

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("煤矿钻场视频智能剪辑与数据管理平台———Client端")
        self.setGeometry(100, 100, 1400, 900)
        self.setStyleSheet("""
        QMainWindow{background:#0a192f;}
        QTabWidget::pane{border:2px solid #64ffda; background:#112240;}
        QTabBar::tab{background:#1e3a5f; color:#e6f1ff; padding:8px 16px;}
        QTabBar::tab:selected{background:#0078d7; color:white;}
        QPushButton{background:#0078d7; color:white;}
        """)
        # 添加窗口图标
        try:
            # 替换为你的ICO文件路径
            self.setWindowIcon(QIcon("ppICO.ico"))
        except:
            # 如果图标加载失败，不影响程序运行
            pass
        # 创建标签页控件
        self.tabs = QTabWidget()
        

        self.image_detection_page = ImageDetectionPage(self.processor, self)  # 传递self作为main_window
        self.video_detection_page = VideoDetectionPage(self.processor, self)   # 传递self作为main_window
        # 添加页面到标签页控件
        self.server_config_page = ServerConfigPage(self.processor) 
        self.developer_info_page = DeveloperInfoPage()  # 这个类不需要额外参数

        self.tabs.addTab(self.image_detection_page, "图像检测")
        self.tabs.addTab(self.video_detection_page, "视频检测")
        self.tabs.addTab(self.server_config_page, "服务器配置")  # 新
        self.tabs.addTab(self.developer_info_page, "开发者信息")
        
        # 设置中文字体，确保中文正常显示
        font = QFont("Noto Sans SC, Microsoft YaHei, SimHei")
        self.tabs.setFont(font)
        
        # 设置中央部件
        self.setCentralWidget(self.tabs)

    def closeEvent(self, event):
        """窗口关闭时停止视频线程（原有代码不变）"""
        self.video_detection_page.stop_processing()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 全局设置中文字体，解决中文乱码问题
    font = QFont("Noto Sans SC, Microsoft YaHei, SimHei")
    app.setFont(font)
    app.setStyleSheet("QPushButton:hover{background:#0088ff;}")
    window = IntelligentMiningEditor()
    window.show()
    sys.exit(app.exec_())
    