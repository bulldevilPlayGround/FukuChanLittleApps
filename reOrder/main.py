# -------------------------------------------------
# 程序入口
# -------------------------------------------------
import sys
import subprocess
from tkinter import messagebox

# 导入 GUI
from gui import VideoReorderApp

# -------------------------------------------------
# 1. 前置依赖检查
# -------------------------------------------------
def check_dependencies():
    """检查程序运行所需的外部依赖（如 FFmpeg）"""
    # 检查 FFmpeg
    try:
        # 在Windows上，创建一个无窗口的进程
        creation_flags = 0
        if sys.platform == 'win32':
            creation_flags = subprocess.CREATE_NO_WINDOW
        subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creation_flags)
    except (subprocess.CalledProcessError, FileNotFoundError):
        messagebox.showerror("依赖缺失", "错误：找不到 FFmpeg。\n\n请确保您已经正确安装了 FFmpeg，并将其添加到了系统的环境变量 (PATH) 中。")
        sys.exit(1)

    # tkinterdnd2 的检查已经在 gui.py 中完成，如果导入失败会直接退出
    # 为了让主程序也能处理这个导入，我们需要在这里尝试导入
    try:
        from tkinterdnd2 import TkinterDnD
    except ImportError:
        # 这个错误理论上已经在 gui.py 中被捕获并显示，这里作为一个备用检查
        if 'tkinterdnd2' not in sys.modules:
            messagebox.showerror("依赖缺失", "错误: 找不到 tkinterdnd2 模块。\n\n请通过 pip install tkinterdnd2 命令安装它。")
        sys.exit(1)

# -------------------------------------------------
# 2. 主函数
# -------------------------------------------------
def main():
    """主函数，用于启动应用"""
    check_dependencies()

    # 必须从 tkinterdnd2 导入 TkinterDnD 来创建主窗口
    from tkinterdnd2 import TkinterDnD
    root = TkinterDnD.Tk()
    app = VideoReorderApp(root)
    root.mainloop()

# -------------------------------------------------
# 3. 程序入口
# -------------------------------------------------
if __name__ == "__main__":
    main()