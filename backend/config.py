import os
import platform

class Config:
    # 基础配置
    DEBUG = True
    JSON_AS_ASCII = False  # 支持中文返回
    
    # 获取当前 config.py 文件所在的目录 (即 backend 根目录)
    BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # ================= 配置你的视频路径 =================
    # ✅ 关键修改：不再使用硬编码的 D盘 或 桌面路径
    # 而是直接指向项目内的 raw_videos/processed 目录
    # 这样，AI 分析生成的视频 (存放在这里) 就能立刻被视频库读取到了
    
    BASE_VIDEO_PATH = os.path.join(BACKEND_DIR, 'raw_videos', 'processed')

    # 如果环境变量中有设置，则优先使用环境变量 (方便容器化部署)
    VIDEO_FOLDER = os.environ.get('VIDEO_ROOT', BASE_VIDEO_PATH)

    # 自动创建目录防止报错
    if not os.path.exists(VIDEO_FOLDER):
        try:
            os.makedirs(VIDEO_FOLDER, exist_ok=True)
        except Exception:
            pass

   # 缓存设置
    CACHE_TIMEOUT = 60  # 目录扫描缓存时间 (秒)
    
    # 缩略图缓存目录 (也建议改为动态路径)
    THUMBNAIL_FOLDER = os.path.join(BACKEND_DIR, 'thumbnails')