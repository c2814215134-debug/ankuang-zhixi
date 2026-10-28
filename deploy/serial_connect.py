"""
Milk-V Duo 串口连接调试工具
通过 COM 口连接板子, 执行命令检查系统状态
"""
import serial
import sys
import time

COM_PORT = 'COM10'
BAUD = 115200
TIMEOUT = 0.5


def connect(port=COM_PORT, baud=BAUD):
    ser = serial.Serial(port, baud, timeout=TIMEOUT)
    ser.flushInput()
    ser.flushOutput()
    return ser


def read_until(ser, timeout=3):
    """读取串口输出直到超时"""
    output = b''
    start = time.time()
    while time.time() - start < timeout:
        if ser.in_waiting:
            chunk = ser.read(ser.in_waiting)
            output += chunk
            start = time.time()
        time.sleep(0.05)
    return output.decode('utf-8', errors='replace')


def send_cmd(ser, cmd, wait=1.5):
    """发送命令并读取返回"""
    ser.write((cmd + '\n').encode())
    time.sleep(wait)
    return read_until(ser, timeout=2)


def check_system(ser):
    """检查板子系统状态"""
    print("=" * 60)
    print("Milk-V Duo 系统检查")
    print("=" * 60)

    # 等待提示符
    print("\n[读取初始输出...]")
    initial = read_until(ser, timeout=2)
    if initial.strip():
        print(f"板子输出:\n{initial[-500:]}")

    # 尝试发送回车获取提示符
    print("\n[尝试获取 Shell...]")
    ser.write(b'\n')
    time.sleep(0.5)
    resp = read_until(ser, timeout=1)
    print(f"响应: {resp.strip()[-200:] if resp.strip() else '(无响应)'}")

    # 如果看到登录提示, 尝试登录
    if 'login' in resp.lower():
        print("\n[检测到登录提示, 尝试登录 root/milkv...]")
        ser.write(b'root\n')
        time.sleep(0.5)
        resp = read_until(ser, timeout=1)
        ser.write(b'milkv\n')
        time.sleep(1)
        resp = read_until(ser, timeout=2)
        print(f"登录结果: {resp[-300:] if len(resp)>10 else resp}")

    # 执行系统检查命令
    checks = [
        ('系统信息', 'uname -a'),
        ('IP 地址', 'ip addr show 2>/dev/null || ifconfig'),
        ('内存', 'free -m 2>/dev/null || free'),
        ('存储', 'df -h /'),
        ('Python', 'python3 --version 2>&1 || python --version 2>&1'),
        ('摄像头', 'ls /dev/video* 2>&1'),
        ('USB设备', 'lsusb 2>&1'),
    ]

    for name, cmd in checks:
        print(f"\n--- {name} ---")
        output = send_cmd(ser, cmd, wait=2)
        print(output.strip()[-300:] if len(output) > 10 else '(无输出)')

    ser.close()
    print("\n" + "=" * 60)
    print("检查完成!")
    print("=" * 60)


def interactive(ser):
    """交互式串口终端"""
    import threading
    import msvcrt

    print("\n进入交互模式, 按 Ctrl+Q 退出\n")
    running = True

    def read_thread():
        global running
        while running:
            if ser.in_waiting:
                try:
                    data = ser.read(ser.in_waiting).decode('utf-8', errors='replace')
                    sys.stdout.write(data)
                    sys.stdout.flush()
                except Exception:
                    pass
            time.sleep(0.02)

    t = threading.Thread(target=read_thread, daemon=True)
    t.start()

    while running:
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch == b'\x11':  # Ctrl+Q
                running = False
                break
            ser.write(ch)
        time.sleep(0.01)

    ser.close()


if __name__ == '__main__':
    print(f"连接 COM10 (115200bps)...")
    try:
        ser = connect()
        print("串口已打开")

        if len(sys.argv) > 1 and sys.argv[1] == '--interactive':
            interactive(ser)
        else:
            check_system(ser)

    except serial.SerialException as e:
        print(f"[ERR] 无法打开 COM10: {e}")
        print("请确认:")
        print("  1. 板子已上电 (灯亮)")
        print("  2. 没有其他程序占用 COM10 (关闭 Putty/串口助手等)")
        print("  3. CH340 驱动正常 (设备管理器中 COM10 无感叹号)")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n中断")
