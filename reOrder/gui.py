# ------------------------------------------------- 
# GUI 主应用程序类
# ------------------------------------------------- 
import sys
import os
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

# Add this for drag-and-drop
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    messagebox.showerror("依赖缺失", "错误: 找不到 tkinterdnd2 模块。\n\n请通过 pip install tkinterdnd2 命令安装它。")
    sys.exit(1)

import core # 导入核心逻辑

VERSION="1.1"

class VideoReorderApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"视频字幕重排剪辑工具 v{VERSION}")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.srt_path = tk.StringVar()
        self.txt_path = tk.StringVar()
        self.video_path = tk.StringVar()
        self.output_path = tk.StringVar()

        self.log_queue = queue.Queue()

        self.create_widgets()
        self.check_log_queue()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="12 12 12 12")
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.columnconfigure(1, weight=1)

        # --- 文件选择区 ---
        self._create_file_selector(main_frame, "SRT 字幕文件:", self.srt_path, self.select_srt_file, 0)
        self._create_file_selector(main_frame, "文本顺序文件:", self.txt_path, self.select_txt_file, 1)
        self._create_file_selector(main_frame, "源视频文件:", self.video_path, self.select_video_file, 2)

        # --- 控制与状态区 ---
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=10)
        control_frame.columnconfigure(0, weight=1)

        self.start_button = ttk.Button(control_frame, text="开始重排并剪辑", command=self.start_processing)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=2)

        self.progress_bar = ttk.Progressbar(control_frame, mode='indeterminate')
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=2, pady=5)

        # --- 日志输出区 ---
        log_frame = ttk.LabelFrame(main_frame, text="日志输出")
        log_frame.grid(row=5, column=0, columnspan=3, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(5, weight=1)

        self.log_text = ScrolledText(log_frame, height=15, state='disabled', wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

    def _create_file_selector(self, frame, label_text, string_var, command, row):
        label = ttk.Label(frame, text=label_text)
        label.grid(row=row, column=0, sticky="w", padx=5, pady=5)

        entry = ttk.Entry(frame, textvariable=string_var, state="readonly")
        entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)

        entry.drop_target_register(DND_FILES)
        entry.dnd_bind('<<Drop>>', lambda e, sv=string_var: self.handle_drop(e, sv))

        button = ttk.Button(frame, text="浏览...", command=command)
        button.grid(row=row, column=2, sticky="e", padx=5, pady=5)

    def handle_drop(self, event, string_var):
        path = event.data
        if path.startswith('{') and path.endswith('}'):
            path = path[1:-1]
        path = path.strip()
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        string_var.set(path)

    def select_srt_file(self):
        path = filedialog.askopenfilename(title="请选择 SRT 字幕文件", filetypes=[("SRT files", "*.srt"), ("All files", "*.*")])
        if path: self.srt_path.set(path)

    def select_txt_file(self):
        path = filedialog.askopenfilename(title="请选择 TXT 文本顺序文件", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path: self.txt_path.set(path)

    def select_video_file(self):
        path = filedialog.askopenfilename(title="请选择源视频文件", filetypes=[("MP4 files", "*.mp4"), ("All video files", "*.*")])
        if path: self.video_path.set(path)

    def start_processing(self):
        video_path = self.video_path.get()
        paths_to_check = [self.srt_path.get(), self.txt_path.get(), video_path]
        if not all(paths_to_check):
            messagebox.showwarning("输入不完整", "请确保所有输入文件路径都已指定！")
            return

        self.log_text.config(state='normal')
        self.log_text.delete('1.0', tk.END)

        path_without_ext, ext = os.path.splitext(video_path)
        output_path = f"{path_without_ext}_cut粗剪{ext}"
        self.output_path.set(output_path)

        self.log_message(f"输出文件将保存为: {output_path}")
        self.log_text.config(state='disabled')

        self.start_button.config(state="disabled")
        self.progress_bar.start(10)

        self.processing_thread = threading.Thread(
            target=core.processing_logic_thread, # 使用 core 模块的函数
            args=(self.srt_path.get(), self.txt_path.get(), video_path, self.output_path.get(), self.log_queue),
            daemon=True
        )
        self.processing_thread.start()

    def check_log_queue(self):
        try:
            message = self.log_queue.get_nowait()
            if message == "<<DONE>>":
                self.start_button.config(state="normal")
                self.progress_bar.stop()
                if "错误" not in self.log_text.get("1.0", tk.END):
                    self.log_message("\n✅ 任务已全部完成！")
                    messagebox.showinfo("成功", "视频重排剪辑任务已成功完成！")
                else:
                    messagebox.showerror("失败", "处理过程中发生错误，请查看日志获取详细信息。 ")
            else:
                self.log_message(message)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.check_log_queue)

    def log_message(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
