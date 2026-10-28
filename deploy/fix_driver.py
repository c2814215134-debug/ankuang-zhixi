"""
Milk-V Duo 网卡驱动修复工具
将误识别为 MIDI function 的设备强制切换到网络适配器驱动
需要管理员权限运行
"""
import subprocess
import sys
import os


def run_cmd(cmd):
    """Run a command and return output"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return result.stdout + result.stderr


def fix_driver():
    print("=" * 60)
    print("Milk-V Duo 网卡驱动修复")
    print("=" * 60)

    # The device instance ID
    instance_id = r"USB\VID_18D1&PID_4EE8&MI_00\8&20a20ef8&1&0000"

    print(f"\n设备实例ID: {instance_id}")

    # Step 1: Check if device exists
    print("\n[1] 检查设备状态...")
    out = run_cmd(f'pnputil /enum-devices /instanceid "{instance_id}"')
    print(out)

    if "MIDI function" not in out and "实例" not in out:
        print("\n[WARN] 未找到 MIDI function 设备，可能已被拔出")
        print("请确认板子已通过 USB OTG 口连接并上电")
        return

    # Step 2: Uninstall the MIDI function driver
    print("\n[2] 卸载 MIDI function 驱动...")
    out = run_cmd(f'pnputil /remove-device "{instance_id}"')
    print(out)

    # Step 3: Try to install the correct driver using the hardware ID
    # We'll use the compatible ID for NCM
    hardware_id = r"USB\VID_18D1&PID_4EE8&MI_00"

    print("\n[3] 扫描硬件改动...")
    out = run_cmd('pnputil /scan-devices')
    print(out)

    print("\n[4] 检查设备管理器...")
    print("如果设备重新出现为未知设备，请手动:")
    print("  右键 → 更新驱动程序 → 浏览我的电脑 → 让我从列表选取")
    print("  → 网络适配器 → Microsoft → UsbNcm Host Device")

    print("\n" + "=" * 60)
    print("修复完成！")
    print("=" * 60)


def install_ncm_driver():
    """
    Alternative: Try to install NCM driver by creating a driver package
    """
    print("尝试安装 UsbNcm 驱动...")

    # Check if the usbncm driver is available
    out = run_cmd('pnputil /enum-drivers')
    if 'usbncm' in out.lower() or 'ncm' in out.lower():
        print("[OK] UsbNcm 驱动已存在于系统中")

    # Force the device to use the correct driver
    # The compatible ID for CDC-NCM
    compat_id = r"USB\VID_18D1&PID_4EE8&MI_00"

    # Use devcon if available
    devcon_paths = [
        r"C:\Windows\System32\devcon.exe",
        r"C:\Windows\SysWOW64\devcon.exe",
    ]

    devcon = None
    for path in devcon_paths:
        if os.path.exists(path):
            devcon = path
            break

    if devcon:
        print(f"Found devcon: {devcon}")
        # Update driver
        cmd = f'"{devcon}" update C:\\Windows\\INF\\usbncm.inf "{compat_id}"'
        print(f"Running: {cmd}")
        out = run_cmd(cmd)
        print(out)
    else:
        print("[INFO] devcon 未找到，请手动更新驱动")


if __name__ == '__main__':
    # Check admin
    try:
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        if not is_admin:
            print("[WARN] 建议以管理员权限运行此脚本")
            print("右键 → 以管理员身份运行\n")
    except Exception:
        pass

    fix_driver()
    print()
    install_ncm_driver()
