from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# 初始化 SQLAlchemy 实例
db = SQLAlchemy()

# 1. 地点表 (Locations)
class Location(db.Model):
    __tablename__ = 'locations'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # 关系映射
    cameras = db.relationship('Camera', backref='location_rel', lazy=True, cascade="all, delete-orphan")
    drill_holes = db.relationship('DrillRecord', backref='location_rel', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'description': self.description
        }

# 2. 摄像仪表 (Cameras)
class Camera(db.Model):
    __tablename__ = 'cameras'

    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    rtsp_url = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='offline')
    ip_address = db.Column(db.String(50), nullable=True)
    port = db.Column(db.Integer, nullable=True)
    username = db.Column(db.String(50), nullable=True)
    password = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'location_id': self.location_id,
            'name': self.name,
            'code': self.code,
            'rtsp_url': self.rtsp_url,
            'status': self.status,
            'ip_address': self.ip_address,
            'port': self.port,
            'username': self.username,
            'password': self.password
        }

# 3. 钻孔记录表 (DrillRecords)
class DrillRecord(db.Model):
    __tablename__ = 'drill_records'

    id = db.Column(db.Integer, primary_key=True)
    hole_number = db.Column(db.String(50), nullable=False, comment='钻孔编号')
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False, comment='施工地点')
    team_name = db.Column(db.String(100), nullable=False, comment='施工队伍')
    responsible_person = db.Column(db.String(50), nullable=False, comment='责任人')
    status = db.Column(db.String(20), default='未开工', comment='施工状态')
    drill_position = db.Column(db.String(100), nullable=False, comment='钻孔位置')
    opening_elevation = db.Column(db.String(50), nullable=False, comment='开孔标高')
    design_depth = db.Column(db.Float, nullable=False, comment='设计孔深')
    actual_depth = db.Column(db.Float, nullable=False, comment='实际孔深')
    dip_angle = db.Column(db.Float, nullable=False, comment='倾角')
    azimuth = db.Column(db.Float, nullable=False, comment='方位角')
    start_time = db.Column(db.DateTime, nullable=True, comment='开工时间')
    end_time = db.Column(db.DateTime, nullable=True, comment='完工时间')
    video_path = db.Column(db.String(255), nullable=True, comment='视频归档路径')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'hole_number': self.hole_number,
            'location_id': self.location_id,
            'team_name': self.team_name,
            'responsible_person': self.responsible_person,
            'status': self.status,
            'drill_position': self.drill_position,
            'opening_elevation': self.opening_elevation,
            'design_depth': self.design_depth,
            'actual_depth': self.actual_depth,
            'dip_angle': self.dip_angle,
            'azimuth': self.azimuth,
            'start_time': self.start_time.strftime('%Y-%m-%d %H:%M') if self.start_time else None,
            'end_time': self.end_time.strftime('%Y-%m-%d %H:%M') if self.end_time else None,
            'video_path': self.video_path
        }


# 4. 用户表 (Users) - 负责注册登录
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, comment='用户名')
    password_hash = db.Column(db.String(255), nullable=False, comment='密码哈希')
    created_at = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # 👇 核心修复：补充了缺失的 to_dict 方法 👇
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


# ================= 🌟 核心：系统参数配置表 =================
# 5. 系统配置表 (SystemConfig)
class SystemConfig(db.Model):
    __tablename__ = 'system_config'

    id = db.Column(db.Integer, primary_key=True)
    config_key = db.Column(db.String(50), unique=True, nullable=False, comment='配置键名')
    config_value = db.Column(db.Text, nullable=True, comment='配置值')
    description = db.Column(db.String(255), nullable=True, comment='配置描述')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'config_key': self.config_key,
            'config_value': self.config_value,
            'description': self.description,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }

# ================= 🌟 核心：AI 识别记录台账表 =================
# 6. 识别记录表 (DetectionLog) - 接收边缘端发来的数据
class DetectionLog(db.Model):
    __tablename__ = 'detection_logs'

    id = db.Column(db.Integer, primary_key=True)
    process_name = db.Column(db.String(50), nullable=False, comment='工序名称')
    detect_time = db.Column(db.String(50), nullable=False, comment='识别时间')
    video_filename = db.Column(db.String(255), nullable=True, comment='原视频名称')
    remark = db.Column(db.Text, nullable=True, comment='备注信息')
    
    # ⚠️ 关键点：这里必须用 db.Text，因为 Base64 图片字符串非常非常长，普通的 String 存不下！
    screenshot_base64 = db.Column(db.Text, nullable=True, comment='Base64图片数据')
    
    mine_name = db.Column(db.String(100), nullable=True, comment='矿井名称')
    drill_no = db.Column(db.String(50), nullable=True, comment='钻孔号')
    drill_location = db.Column(db.String(255), nullable=True, comment='钻孔位置')
    
    created_at = db.Column(db.DateTime, default=datetime.now, comment='系统接收时间')

    def to_dict(self):
        return {
            'id': self.id,
            'process_name': self.process_name,
            'detect_time': self.detect_time,
            'video_filename': self.video_filename,
            'remark': self.remark,
            # 前端如果直接用 Base64 显示图片，需要带上前缀，如果没带我们可以在这里或者前端拼上
            'screenshot_base64': self.screenshot_base64, 
            'mine_name': self.mine_name,
            'drill_no': self.drill_no,
            'drill_location': self.drill_location,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }