import os
import time
import uuid
import threading
import multiprocessing
import traceback
import re
import sqlite3
from datetime import datetime
from flask import Flask, jsonify, request, Response, abort, send_file
from flask_cors import CORS
from config import Config
from flask_migrate import Migrate
from sqlalchemy import desc, func

# 🌟 核心修改：增加了 DetectionLog 模型的导入
from models import db, Location, Camera, DrillRecord, User, SystemConfig, DetectionLog

# 尝试导入 OpenCV
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("警告 警告: 未检测到 opencv-python，视频功能可能受限")

app = Flask(__name__)
app.config.from_object(Config)

# 基础路径配置
app.config['RAW_VIDEO_FOLDER'] = os.environ.get('RAW_VIDEO_ROOT', os.path.join(app.root_path, 'raw_videos'))
app.config['THUMBNAIL_FOLDER'] = os.path.join(app.root_path, 'thumbnails')
os.makedirs(app.config['RAW_VIDEO_FOLDER'], exist_ok=True)
os.makedirs(app.config['THUMBNAIL_FOLDER'], exist_ok=True)

# 数据库配置
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.root_path, 'coalmine.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)
CORS(app)

# ========== 多进程全局变量 ==========
manager = None
shared_analysis_tasks = {}
task_control_events = {}
frame_queue = None 
local_analysis_frames = {}

def init_multiprocessing():
    global manager, shared_analysis_tasks, frame_queue
    if manager is None:
        try:
            manager = multiprocessing.Manager()
            shared_analysis_tasks = manager.dict()
            frame_queue = multiprocessing.Queue(maxsize=50)
            print("正确 多进程管理器初始化成功")
        except Exception as e:
            print(f"错误 多进程初始化失败: {e}")
            shared_analysis_tasks = {}
            frame_queue = multiprocessing.Queue(maxsize=50)

# ================= 🌟 核心：动态获取路径函数 =================
def get_current_video_path():
    """动态获取最新的视频保存路径"""
    try:
        # 1. 尝试从数据库获取用户配置的路径
        with app.app_context():
            config = SystemConfig.query.filter_by(config_key='localBasePath').first()
            if config and config.config_value:
                # 顺手帮用户建好文件夹（如果不存在的话），防止后续报错
                os.makedirs(config.config_value, exist_ok=True)
                return config.config_value
    except Exception as e:
        print(f"读取数据库配置失败: {e}")
        
    # 2. 🌟 修复：如果数据库没有，直接在当前运行目录下生成一个 raw_videos/processed 作为兜底
    default_path = os.path.abspath(os.path.join(os.getcwd(), 'raw_videos', 'processed'))
    os.makedirs(default_path, exist_ok=True)
    return default_path

# ========== AI 工作进程 ==========
def _resolve_font_path():
    """按优先级解析中文字体：仓库内置 Noto Sans SC（SIL OFL，可再分发）优先，
    其次系统 SimHei（仅本机使用，不随仓库分发），最后交由 PIL 使用默认字体。"""
    candidates = [
        os.path.join(os.getcwd(), 'fonts', 'NotoSansSC-Regular.otf'),
        os.path.join(os.getcwd(), '..', 'fonts', 'NotoSansSC-Regular.otf'),
        os.path.join(os.getcwd(), 'SimHei.ttf'),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]

def ai_worker_process(task_id, video_path, output_dir, frame_skip, stop_event, status_dict, frame_q):
    try:
        from ai_engine import MiningVideoAnalyzer
        import cv2

        # 🌟 修复 1：任务刚扔进子进程，立刻将状态变更为“处理中”
        if status_dict is not None:
            task_info = status_dict.get(task_id, {}).copy()
            task_info['status'] = 'running'
            task_info['current_step'] = 'AI 引擎已接管，正在加载模型...'
            status_dict[task_id] = task_info

        def progress_callback(frame, total, state, image_frame):
            try:
                percent = int((frame / total) * 100) if total > 0 else 0
                if status_dict is not None:
                    task_info = status_dict.get(task_id, {}).copy()
                    task_info['status'] = 'running' # 确保进度更新时状态也是 running
                    task_info['progress'] = percent
                    task_info['message'] = f"正在分析: {state}"
                    task_info['current_step'] = state
                    status_dict[task_id] = task_info

                if image_frame is not None and frame_q is not None:
                    try:
                        ret, buffer = cv2.imencode('.jpg', image_frame)
                        if ret:
                            # 🌟 修复 Mac M芯片底层 Bug：绝对不能用 .full()，直接用 block=False 强塞
                            frame_q.put((task_id, buffer.tobytes()), block=False)
                    except Exception: pass
            except Exception: pass

        analyzer = MiningVideoAnalyzer(
            weights_path=os.path.join(os.getcwd(), 'zzbest.pt'),
            font_path=_resolve_font_path()
        )

        generated_files = analyzer.process_video(
            source_path=video_path,
            output_dir=output_dir,
            frame_skip=frame_skip, 
            progress_callback=progress_callback,
            stop_event=stop_event
        )

        if status_dict is not None:
            task_info = status_dict.get(task_id, {}).copy()
            
            # 🌟 修复 2：判断任务是“自然跑完”的，还是被用户“强行叫停”的
            if stop_event and stop_event.is_set():
                task_info['status'] = 'stopped'
                task_info['message'] = '任务已手动终止'
                task_info['current_step'] = '分析已被终止，保留已处理的切片'
                # 终止的任务，进度条保留在终止时的位置，不拉到 100%
            else:
                task_info['status'] = 'completed'
                task_info['progress'] = 100
                task_info['message'] = '分析完成'
                task_info['current_step'] = '所有工序分析完毕，已归档'
                
            task_info['generated_files'] = generated_files
            status_dict[task_id] = task_info

    except Exception as e:
        print(f"错误 [子进程崩溃] {e}")
        traceback.print_exc()
        if status_dict is not None:
            task_info = status_dict.get(task_id, {}).copy()
            task_info['status'] = 'failed'
            task_info['message'] = f"AI引擎错误: {str(e)}"
            task_info['current_step'] = '处理崩溃'
            status_dict[task_id] = task_info

def frame_consumer():
    while True:
        try:
            if frame_queue:
                task_id, frame_bytes = frame_queue.get()
                local_analysis_frames[task_id] = frame_bytes
            else:
                time.sleep(1)
        except Exception:
            time.sleep(0.1)

# ==========================================
#              API 路由定义
# ==========================================

# ================= 🌟 核心：系统参数配置 API =================
@app.route('/api/system/config', methods=['GET'])
def get_system_config():
    configs = SystemConfig.query.all()
    config_dict = {}
    for c in configs:
        if c.config_value == 'true':
            config_dict[c.config_key] = True
        elif c.config_value == 'false':
            config_dict[c.config_key] = False
        else:
            config_dict[c.config_key] = c.config_value
            
    # 🌟 彻底修复：如果数据库里没数据，用动态生成的绝对路径兜底，不再依赖任何死变量！
    if 'localBasePath' not in config_dict or not config_dict['localBasePath']:
        config_dict['localBasePath'] = os.path.abspath(os.path.join(os.getcwd(), 'raw_videos', 'processed'))

    return jsonify({"success": True, "data": config_dict})

@app.route('/api/system/config', methods=['POST'])
def save_system_config():
    data = request.json
    if not data:
        return jsonify({"success": False, "message": "没有收到数据"}), 400

    try:
        for key, value in data.items():
            if isinstance(value, bool):
                str_value = 'true' if value else 'false'
            else:
                str_value = str(value) if value is not None else ''

            config_record = SystemConfig.query.filter_by(config_key=key).first()
            if config_record:
                config_record.config_value = str_value
            else:
                new_config = SystemConfig(config_key=key, config_value=str_value)
                db.session.add(new_config)

        db.session.commit()
        return jsonify({"success": True, "message": "配置保存成功"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"保存失败: {str(e)}"}), 500

# --- 认证体系 (注册/登录) ---
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400

    pattern = r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]+$'
    if not re.match(pattern, username):
        return jsonify({'success': False, 'message': '用户名必须是字母和数字的组合'}), 400

    if len(password) <= 6:
        return jsonify({'success': False, 'message': '密码必须多于6位'}), 400

    if not re.match(pattern, password):
        return jsonify({'success': False, 'message': '密码必须是字母和数字的组合'}), 400

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({'success': False, 'message': '用户名已存在，请更换用户名'}), 400

    try:
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'success': True, 'message': '注册成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': '系统错误，注册失败'}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'success': False, 'message': '用户不存在，请先注册账号'}), 404

    if not user.check_password(password):
        return jsonify({'success': False, 'message': '密码输入错误'}), 401

    return jsonify({
        'success': True, 
        'message': '登录成功',
        'data': user.to_dict()
    })

# --- 其他原有接口 ---
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'success': True,
        'status': 'online',
        'server_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route('/api/dashboard/stats', methods=['GET'])
def dashboard_stats():
    try:
        total = DrillRecord.query.count()
        finished = DrillRecord.query.filter_by(status='已完工').count()
        ongoing = DrillRecord.query.filter_by(status='施工中').count()
        recent = [d.to_dict() for d in DrillRecord.query.order_by(desc(DrillRecord.id)).limit(5).all()]

        return jsonify({
            'success': True,
            'total_drills': total,
            'recent_drills': recent,
            'status_counts': {
                '已完工': finished,
                '施工中': ongoing
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# 地点管理
@app.route('/api/locations', methods=['GET'])
def get_locations():
    items = Location.query.all()
    return jsonify({'success': True, 'data': [i.to_dict() for i in items]})

@app.route('/api/locations', methods=['POST'])
def create_location():
    data = request.json
    try:
        new_loc = Location(
            code=data.get('code'),
            name=data.get('name'),
            description=data.get('description')
        )
        db.session.add(new_loc)
        db.session.commit()
        return jsonify({'success': True, 'data': new_loc.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/locations/<int:id>', methods=['PUT'])
def update_location(id):
    data = request.json
    try:
        loc = Location.query.get(id)
        if not loc:
            return jsonify({'success': False, 'message': 'Not found'}), 404
        loc.code = data.get('code', loc.code)
        loc.name = data.get('name', loc.name)
        loc.description = data.get('description', loc.description)
        db.session.commit()
        return jsonify({'success': True, 'data': loc.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/locations/<int:id>', methods=['DELETE'])
def delete_location(id):
    try:
        loc = Location.query.get(id)
        if loc:
            db.session.delete(loc)
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# 摄像仪管理
@app.route('/api/cameras', methods=['GET'])
def get_cameras():
    items = Camera.query.all()
    return jsonify({'success': True, 'data': [i.to_dict() for i in items]})

@app.route('/api/cameras', methods=['POST'])
def create_camera():
    data = request.json
    try:
        new_cam = Camera(
            location_id=data.get('location_id'),
            name=data.get('name'),
            code=data.get('code'),
            rtsp_url=data.get('rtsp_url'),
            status=data.get('status', 'offline'),
            ip_address=data.get('ip_address'),
            port=data.get('port'),
            username=data.get('username'),
            password=data.get('password')
        )
        db.session.add(new_cam)
        db.session.commit()
        return jsonify({'success': True, 'data': new_cam.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/cameras/<int:id>', methods=['PUT'])
def update_camera(id):
    data = request.json
    try:
        cam = Camera.query.get(id)
        if not cam:
            return jsonify({'success': False, 'message': 'Not found'}), 404

        cam.location_id = data.get('location_id', cam.location_id)
        cam.name = data.get('name', cam.name)
        cam.code = data.get('code', cam.code)
        cam.rtsp_url = data.get('rtsp_url', cam.rtsp_url)
        cam.status = data.get('status', cam.status)
        cam.ip_address = data.get('ip_address', cam.ip_address)
        cam.port = data.get('port', cam.port)
        cam.username = data.get('username', cam.username)
        cam.password = data.get('password', cam.password)

        db.session.commit()
        return jsonify({'success': True, 'data': cam.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/cameras/<int:id>', methods=['DELETE'])
def delete_camera(id):
    try:
        item = Camera.query.get(id)
        if item:
            db.session.delete(item)
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# 钻孔记录
@app.route('/api/drills', methods=['GET'])
def get_drills():
    items = DrillRecord.query.order_by(desc(DrillRecord.id)).all()
    return jsonify({'success': True, 'data': [i.to_dict() for i in items]})

@app.route('/api/drills', methods=['POST'])
def create_drill():
    data = request.json
    
    # 🌟 1. 严格的必填项拦截器
    required_fields = {
        'hole_number': '钻孔编号',
        'location_id': '施工地点',
        'team_name': '施工队伍',
        'responsible_person': '责任人',
        'drill_position': '钻孔位置',
        'opening_elevation': '开孔标高',
        'design_depth': '设计孔深',
        'actual_depth': '实际孔深',
        'dip_angle': '倾角',
        'azimuth': '方位角'
    }
    
    for key, name in required_fields.items():
        if key not in data or str(data[key]).strip() == '':
            return jsonify({'success': False, 'message': f'保存失败：[{name}] 是必填项，不能为空！'}), 400

    try:
        def parse_time(t_str):
            if not t_str or str(t_str).strip() == '': 
                return None
            clean_str = str(t_str).replace('T', ' ')[:16] 
            return datetime.strptime(clean_str, '%Y-%m-%d %H:%M')
            
        start_t = parse_time(data.get('start_time'))
        end_t = parse_time(data.get('end_time'))

        new_drill = DrillRecord(
            hole_number=str(data['hole_number']),
            location_id=int(data['location_id']),
            team_name=str(data['team_name']),
            responsible_person=str(data['responsible_person']),
            status=data.get('status', '未开工'),
            drill_position=str(data['drill_position']),
            opening_elevation=str(data['opening_elevation']),
            design_depth=float(data['design_depth']),
            actual_depth=float(data['actual_depth']),
            dip_angle=float(data['dip_angle']),
            azimuth=float(data['azimuth']),
            start_time=start_t,
            end_time=end_t,
            video_path=data.get('video_path', '')
        )
        db.session.add(new_drill)
        db.session.commit()
        return jsonify({'success': True, 'data': new_drill.to_dict()})
        
    except ValueError as ve:
        return jsonify({'success': False, 'message': '数据格式错误，请确保孔深、角度等字段填写的是纯数字！'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'系统级保存失败: {str(e)}'}), 500

@app.route('/api/drills/<int:id>', methods=['PUT'])
def update_drill(id):
    data = request.json
    try:
        drill = DrillRecord.query.get(id)
        if not drill:
            return jsonify({'success': False, 'message': '找不到该条钻孔记录'}), 404
            
        required_fields = ['hole_number', 'location_id', 'team_name', 'responsible_person', 
                           'drill_position', 'opening_elevation', 'design_depth', 
                           'actual_depth', 'dip_angle', 'azimuth']
                           
        for key in required_fields:
            if key in data and str(data[key]).strip() == '':
                return jsonify({'success': False, 'message': '修改失败：必填项不能被清空！'}), 400

        drill.hole_number = str(data.get('hole_number', drill.hole_number))
        if data.get('location_id'): drill.location_id = int(data['location_id'])
        drill.team_name = str(data.get('team_name', drill.team_name))
        drill.responsible_person = str(data.get('responsible_person', drill.responsible_person))
        drill.status = data.get('status', drill.status)
        drill.drill_position = str(data.get('drill_position', drill.drill_position))
        drill.opening_elevation = str(data.get('opening_elevation', drill.opening_elevation))
        
        if data.get('design_depth') is not None: drill.design_depth = float(data['design_depth'])
        if data.get('actual_depth') is not None: drill.actual_depth = float(data['actual_depth'])
        if data.get('dip_angle') is not None: drill.dip_angle = float(data['dip_angle'])
        if data.get('azimuth') is not None: drill.azimuth = float(data['azimuth'])
        
        drill.video_path = data.get('video_path', drill.video_path)

        if data.get('start_time'):
            clean_str = str(data['start_time']).replace('T', ' ')[:16]
            drill.start_time = datetime.strptime(clean_str, '%Y-%m-%d %H:%M')
        if data.get('end_time'):
            clean_str = str(data['end_time']).replace('T', ' ')[:16]
            drill.end_time = datetime.strptime(clean_str, '%Y-%m-%d %H:%M')

        db.session.commit()
        return jsonify({'success': True, 'data': drill.to_dict()})
        
    except ValueError as ve:
        return jsonify({'success': False, 'message': '修改失败，请确保数值类字段填入的是纯数字！'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'系统级修改失败: {str(e)}'}), 500

@app.route('/api/drills/<int:id>', methods=['DELETE'])
def delete_drill(id):
    try:
        item = DrillRecord.query.get(id)
        if item:
            db.session.delete(item)
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ==========================================
# 🌟 AI 检测结果台账 API (收发室) - 已加入地点自动同步功能
# ==========================================
@app.route('/api/detection/receive', methods=['POST'])
def receive_detection_result():
    """接收测试服务器发送的 AI 识别结果并入库，同时自动同步到地点管理"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': '未接收到有效数据'}), 400

        # 1. 解析与处理时间格式
        detect_time_str = data.get('detect_time')
        detect_time = None
        if detect_time_str:
            try:
                clean_str = str(detect_time_str).replace('T', ' ')[:19]
                if len(clean_str) == 16:
                    detect_time = datetime.strptime(clean_str, '%Y-%m-%d %H:%M')
                else:
                    detect_time = datetime.strptime(clean_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                detect_time = datetime.now()
        else:
            detect_time = datetime.now()

        # 提取基础字段
        mine_name = data.get('mine_name', '')
        drill_location = data.get('drill_location', '')
        drill_no = data.get('drill_no', '')

        # 2. 生成收发室台账新记录
        new_log = DetectionLog(
            mine_name=mine_name,
            drill_location=drill_location,
            drill_no=drill_no,
            process_name=data.get('process_name', ''),
            detect_time=detect_time,
            video_filename=data.get('video_filename', ''),
            remark=data.get('remark', ''),
            screenshot_base64=data.get('screenshot_base64', '')
        )
        db.session.add(new_log)

        # 3. 🌟 核心：自动同步到 Location 表 (地点管理)
        if drill_no:  # 只要传了钻孔编号，我们就尝试同步
            # 查询是否已经存在这个编号的地点，防止无限重复创建
            existing_loc = Location.query.filter_by(code=drill_no).first()
            
            if existing_loc:
                # 如果存在，顺手把最新的矿井名和地点名更新上去（以防之前信息有误）
                existing_loc.name = drill_location
                existing_loc.description = mine_name
            else:
                # 如果不存在，自动帮用户在“地点管理”里新建一个地点
                new_loc = Location(
                    code=drill_no,
                    name=drill_location,
                    description=mine_name
                )
                db.session.add(new_loc)

        # 4. 一次性提交所有更改（台账记录 + 地点记录）
        db.session.commit()

        return jsonify({'success': True, 'message': '识别结果接收成功，并已同步基础数据', 'id': new_log.id}), 200

    except Exception as e:
        db.session.rollback()
        print(f"❌ [收发室] 接收数据报错: {e}")
        return jsonify({'success': False, 'message': f'系统错误: {str(e)}'}), 500

@app.route('/api/detection/logs', methods=['GET'])
def get_detection_logs():
    """供前端台账页面获取完整的检测结果记录"""
    try:
        # 按时间倒序，最新的数据排在前面
        logs = DetectionLog.query.order_by(desc(DetectionLog.detect_time)).all()
        return jsonify({
            'success': True,
            'data': [log.to_dict() for log in logs] if logs else []
        })
    except Exception as e:
        print(f"❌ [收发室] 获取台账记录报错: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/detection/logs/<int:id>', methods=['DELETE'])
def delete_detection_log(id):
    """支持测试过程中的脏数据清理"""
    try:
        log = DetectionLog.query.get(id)
        if log:
            db.session.delete(log)
            db.session.commit()
            return jsonify({'success': True, 'message': '记录已成功删除'})
        return jsonify({'success': False, 'message': '未找到该条记录'}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# 智能分析
@app.route('/api/analysis/files', methods=['GET'])
def get_raw_files():
    files = []
    folder = app.config['RAW_VIDEO_FOLDER']
    if not os.path.exists(folder):
        return jsonify({'success': True, 'files': []})
    try:
        for f in os.listdir(folder):
            if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv')):
                file_path = os.path.join(folder, f)
                size_mb = os.path.getsize(file_path) / (1024 * 1024)
                files.append({
                    'name': f,
                    'id': f,
                    'value': f,
                    'path': file_path,
                    'size': f"{size_mb:.2f} MB"
                })
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ================= 🌟 核心：接收前端文件流、重命名并自动启动 =================
@app.route('/api/analysis/upload_and_start', methods=['POST'])
def upload_and_start_analysis():
    if manager is None:
        init_multiprocessing()

    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未检测到视频文件流'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '文件名为空'}), 400

        custom_name = request.form.get('customFileName', '未命名任务')
        upload_to_cloud = request.form.get('uploadToCloud', 'false') == 'true'
        frame_skip = int(request.form.get('frame_skip', 3))

        safe_custom_name = custom_name.replace('/', '_').replace('\\', '_')

        _, ext = os.path.splitext(file.filename)
        if not ext:
            ext = '.mp4' 
            
        import time
        new_filename = f"{safe_custom_name}_{int(time.time())}{ext}"

        source_path = os.path.join(app.config['RAW_VIDEO_FOLDER'], new_filename)
        file.save(source_path)

        task_id = str(uuid.uuid4())
        
        base_output_dir = get_current_video_path()
        output_dir = os.path.join(base_output_dir, safe_custom_name)
        os.makedirs(output_dir, exist_ok=True)

        shared_analysis_tasks[task_id] = {
            'id': task_id, 
            'filename': new_filename,
            'status': 'initializing', 
            'progress': 0,
            'message': '文件已保存，正在启动 AI 引擎...', 
            'current_step': '准备中', 
            'generated_files': [],
            'start_time': datetime.now().isoformat(),
            'upload_to_cloud': upload_to_cloud  
        }

        stop_event = multiprocessing.Event()
        task_control_events[task_id] = stop_event

        p = multiprocessing.Process(
            target=ai_worker_process,
            args=(task_id, source_path, output_dir, frame_skip, stop_event, shared_analysis_tasks, frame_queue)
        )
        p.daemon = True
        p.start()

        print(f"✅ 成功接收上传: {new_filename}, 云端备份: {upload_to_cloud}", flush=True)

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '上传成功，AI 已接管任务',
            'output_dir': output_dir
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'系统处理失败: {str(e)}'}), 500

@app.route('/api/analysis/start', methods=['POST'])
def start_analysis():
    if manager is None:
        init_multiprocessing()

    try:
        data = request.json
        filename = data.get('filename')
        if not filename:
            return jsonify({'success': False, 'message': '缺少文件名'}), 400

        video_path = os.path.join(app.config['RAW_VIDEO_FOLDER'], filename)
        if not os.path.exists(video_path):
            return jsonify({'success': False, 'message': f'文件不存在: {video_path}'}), 404

        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return jsonify({'success': False, 'message': '无法打开视频文件'}), 400
            cap.release()
        except:
            return jsonify({'success': False, 'message': '视频文件损坏'}), 400

        frame_skip = int(data.get('frame_skip', 3))
        task_id = str(uuid.uuid4())
        video_name_no_ext = os.path.splitext(filename)[0]
        
        base_output_dir = get_current_video_path()
        output_dir = os.path.join(base_output_dir, video_name_no_ext)
        os.makedirs(output_dir, exist_ok=True)

        shared_analysis_tasks[task_id] = {
            'id': task_id, 'status': 'running', 'progress': 0,
            'message': '正在初始化...', 'current_step': '准备中', 'generated_files': [],
            'start_time': datetime.now().isoformat()
        }

        stop_event = multiprocessing.Event()
        task_control_events[task_id] = stop_event

        p = multiprocessing.Process(
            target=ai_worker_process,
            args=(task_id, video_path, output_dir, frame_skip, stop_event, shared_analysis_tasks, frame_queue)
        )
        p.daemon = True 
        p.start()

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '任务已启动',
            'output_dir': output_dir
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'启动失败: {str(e)}'}), 500

@app.route('/api/analysis/stop/<task_id>', methods=['POST'])
def stop_analysis(task_id):
    if task_id in task_control_events:
        task_control_events[task_id].set()
        return jsonify({'success': True, 'message': '停止信号已发送'})
    return jsonify({'success': False, 'message': '任务不存在'}), 404

@app.route('/api/analysis/status/<task_id>', methods=['GET'])
def get_analysis_status(task_id):
    try:
        if manager is None:
            init_multiprocessing()

        task = shared_analysis_tasks.get(task_id)
        if not task:
            return jsonify({'success': False, 'message': '任务不存在'}), 404

        # 🌟 修复：预先定义 elapsed 变量，防止下面的 UnboundLocalError 隐患
        elapsed = 0
        if 'start_time' in task:
            start_time = datetime.fromisoformat(task['start_time'])
            elapsed = (datetime.now() - start_time).total_seconds()

            # 🌟 修复：超时检测从 86400秒（24小时）改成了符合注释和逻辑要求的 1800秒（30分钟） 
            if elapsed > 1800 and task['status'] == 'running':                           
                task['status'] = 'failed'
                task['message'] = '处理超时（30分钟）'                                                                       
                print(f"时钟 [主进程] 任务 {task_id} 超时，强制标记为失败", flush=True)

        task_copy = task.copy()
        task_copy['elapsed_time'] = elapsed

        return jsonify({'success': True, 'data': task_copy})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'获取状态失败: {str(e)}'}), 500

@app.route('/api/analysis/feed/<task_id>')
def analysis_feed(task_id):
    def generate():
        import cv2, numpy as np
        placeholder = np.zeros((360, 640, 3), dtype=np.uint8)
        cv2.putText(placeholder, "AI Engine Initializing...", (120, 160), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(placeholder, "Loading YOLO & OCR Models", (120, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(placeholder, "Please wait 5-10 seconds...", (120, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        ret, buf = cv2.imencode('.jpg', placeholder)
        placeholder_bytes = buf.tobytes()

        while True:
            if manager is None: break
            task = shared_analysis_tasks.get(task_id)
            
            if not task or task.get('status') not in ['initializing', 'running', 'stopping']: 
                break
            
            frame_bytes = local_analysis_frames.get(task_id)
            if frame_bytes and task.get('status') == 'running':
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            else:
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + placeholder_bytes + b'\r\n')
            
            time.sleep(0.05) 
            
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

# 视频文件夹
@app.route('/api/folders', methods=['GET'])
def handle_folders():
    root = get_current_video_path()
    if not root or not os.path.exists(root): return jsonify({'success': True, 'folders': []})
    folders = []
    try:
        for d in os.listdir(root):
            path = os.path.join(root, d)
            if os.path.isdir(path):
                v_count = len([f for f in os.listdir(path) if f.endswith('.mp4')])
                folders.append({'name': d, 'video_count': v_count})
        root_videos = len([f for f in os.listdir(root) if f.endswith('.mp4')])
        if root_videos > 0: folders.insert(0, {'name': '.', 'video_count': root_videos, 'display_name': '根目录'})
    except Exception: pass
    return jsonify({'success': True, 'folders': folders})

@app.route('/api/folder/<path:folder_name>', methods=['GET'])
def get_folder_videos(folder_name):
    base_root = get_current_video_path()
    folder_path = base_root if folder_name == '.' else os.path.join(base_root, folder_name)
    if not os.path.exists(folder_path): return jsonify({'success': False, 'message': 'Directory not found'}), 404
    videos = []
    try:
        for f in os.listdir(folder_path):
            if f.lower().endswith(('.mp4', '.avi', '.mov')):
                videos.append({
                    'name': f,
                    'path': f if folder_name == '.' else f"{folder_name}/{f}",
                    'size': f"{os.path.getsize(os.path.join(folder_path, f))/(1024*1024):.1f} MB"
                })
    except Exception as e: return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': True, 'videos': videos})

@app.route('/api/video/<path:filename>')
def serve_video(filename):
    dynamic_path = get_current_video_path()
    dynamic_file_path = os.path.join(dynamic_path, filename)
    if os.path.exists(dynamic_file_path): 
        return send_file(dynamic_file_path)

    raw_path = os.path.join(app.config['RAW_VIDEO_FOLDER'], filename)
    if os.path.exists(raw_path): return send_file(raw_path)
    
    archive_path = os.path.join(Config.VIDEO_FOLDER, filename)
    if os.path.exists(archive_path): return send_file(archive_path)
    
    return abort(404)

def gen_frames(camera_id_or_str):
    with app.app_context():
        camera = None
        if isinstance(camera_id_or_str, str) and camera_id_or_str.startswith('cam-'):
            try:
                real_id = int(camera_id_or_str.replace('cam-', ''))
                camera = Camera.query.get(real_id)
            except ValueError:
                pass
        elif str(camera_id_or_str).isdigit():
            camera = Camera.query.get(int(camera_id_or_str))

    if not camera: 
        return 

    if camera.port == 0 or camera.ip_address == '0':
        video_source = 0 
    else:
        video_source = camera.rtsp_url

    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        return 

    while True:
        success, frame = cap.read()
        if not success:
            break
        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

    cap.release()

@app.route('/api/video_feed/<camera_id>')
def video_feed(camera_id):
    return Response(gen_frames(camera_id), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    multiprocessing.freeze_support()
    init_multiprocessing()
    t = threading.Thread(target=frame_consumer, daemon=True)
    t.start()
    with app.app_context():
        # 这里会自动创建新建的 User、DetectionLog 等表
        db.create_all()
    print("🚀 煤矿系统后端 V2.0 已启动: http://0.0.0.0:2800")
    app.run(host='0.0.0.0', port=2800, debug=False, threaded=True)