# -------------------------------------------------
# 1. 导入所需模块
# -------------------------------------------------
import sys
import threading
import queue
import re
import srt
import subprocess
import os

# GUI
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

# Add this for drag-and-drop
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    messagebox.showerror("依赖缺失", "错误: 找不到 tkinterdnd2 模块。\n\n请通过 pip install tkinterdnd2 命令安装它。")
    sys.exit(1)

VERSION="1.1"
# -------------------------------------------------
# 2. 后端核心逻辑 (从 reoder.py 移植并优化)
# -------------------------------------------------
# 注意：我们将原始脚本中的 print 函数替换为了一个回调函数 (log_callback)，
# 这样可以将日志信息灵活地发送到UI或控制台。
FFMPEG_CREATION_FLAGS = 0
if sys.platform == 'win32':
    FFMPEG_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW

def read_file(path, encoding='utf-8'):
    """读取文件内容"""
    try:
        with open(path, 'r', encoding=encoding) as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"错误: 文件 '{path}' 未找到。")
    except Exception as e:
        raise IOError(f"读取文件 '{path}' 时出错: {e}")

def read_txt_lines(path):
    """读取 TXT 文件的非空行并去除首尾空白"""
    content = read_file(path)
    return [line.strip() for line in content.splitlines() if line.strip()]

def parse_srt_file(path):
    """解析 SRT 文件并返回字幕对象列表"""
    srt_content = read_file(path)
    return list(srt.parse(srt_content))

def normalize_text(text):
    """规范化文本中的空白字符"""
    return re.sub(r'\s+', ' ', text.strip())

def extract_srt_texts(subtitles):
    """提取并规范化 SRT 字幕文本"""
    return [normalize_text(sub.content) for sub in subtitles]

def find_txt_indices_in_srt(txt_lines, srt_texts):
    """查找 TXT 行在 SRT 字幕中的索引（只记录第一个匹配）"""
    indices = []
    found_indices = set()
    for txt_line in txt_lines:
        txt_line_norm = normalize_text(txt_line)
        for idx, srt_text in enumerate(srt_texts):
            # 确保每个 SRT 字幕只被匹配一次
            if txt_line_norm == srt_text and idx not in found_indices:
                indices.append(str(idx + 1))  # SRT index starts from 1
                found_indices.add(idx)
                break
    return indices

def merge_indices(indices):
    """按原始顺序合并连续的字幕索引"""
    if not indices:
        return []
    indices = [int(i) for i in indices]
    merged = []
    if not indices:
        return merged
    group = [indices[0]]
    for cur in indices[1:]:
        if cur == group[-1] + 1:  # 连续
            group.append(cur)
        else:
            merged.append(group)
            group = [cur]
    merged.append(group)
    return merged

def get_bitrate(video_file):
    """获取视频的比特率"""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=bit_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_file
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, creationflags=FFMPEG_CREATION_FLAGS)
    if not result.stdout.strip().isdigit():
        return "2000k" # 返回一个安全的默认值
    return result.stdout.strip()

def cut_video(subtitles, merged_groups, video_file, log_callback=print):
    """根据合并后的索引组剪辑视频"""
    temp_clips = []
    try:
        bit_rate = get_bitrate(video_file)
        log_callback(f"获取到视频比特率: {bit_rate}")

        for i, group in enumerate(merged_groups, 1):
            start = subtitles[group[0]-1].start.total_seconds()
            end = subtitles[group[-1]-1].end.total_seconds()
            output = f"temp_clip_{i}.mp4"
            temp_clips.append(output)

            cmd = [
                "ffmpeg", "-y", "-i", video_file,
                "-ss", str(start), "-to", str(end),
                "-c:v", "h264_nvenc", "-b:v", str(bit_rate),
                "-c:a", "aac", "-hide_banner", "-loglevel", "error",
                output
            ]
            subprocess.run(cmd, check=True, creationflags=FFMPEG_CREATION_FLAGS)
            log_callback(f"成功生成片段: {output} ({start:.2f}s ~ {end:.2f}s)")
        return temp_clips
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg 剪辑时出错: {e}")
    except Exception as e:
        raise RuntimeError(f"剪辑视频时发生未知错误: {e}")


def concat_videos(clips, output_file, log_callback=print):
    """使用 ffmpeg 将多个片段拼接成一个视频"""
    list_file = "temp_file_list.txt"
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for clip in clips:
                f.write(f"file '{os.path.abspath(clip)}'\n")

        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file, "-c", "copy", output_file
        ]
        subprocess.run(cmd, check=True, creationflags=FFMPEG_CREATION_FLAGS)
        log_callback(f"已成功生成合并视频: {output_file}")
    finally:
        # 清理工作
        if os.path.exists(list_file):
            os.remove(list_file)
        for clip in clips:
            if os.path.exists(clip):
                os.remove(clip)
        log_callback("已清理所有临时片段文件。")


def processing_logic_thread(srt_path, txt_path, video_path, output_path, log_queue):
    """在后台线程中运行的完整处理逻辑"""
    try:
        log_queue.put(">>> 任务开始：正在解析文件...")
        subtitles = parse_srt_file(srt_path)
        txt_lines = read_txt_lines(txt_path)
        srt_texts = extract_srt_texts(subtitles)
        log_queue.put(f"SRT 文件加载了 {len(subtitles)} 条字幕。")
        log_queue.put(f"TXT 文件加载了 {len(txt_lines)} 行文本。")

        log_queue.put("\n>>> 正在匹配字幕索引...")
        indices = find_txt_indices_in_srt(txt_lines, srt_texts)
        if not indices:
            raise ValueError("在 SRT 文件中没有匹配到任何 TXT 文本行，请检查文件内容。")
        log_queue.put(f"原始匹配到的字幕序号: {', '.join(indices)}")

        merged_groups = merge_indices(indices)
        log_queue.put(f"合并后的连续字幕段落: {merged_groups}")

        log_queue.put("\n>>> 正在剪辑视频片段...")
        temp_clips = cut_video(subtitles, merged_groups, video_path, log_callback=log_queue.put)

        log_queue.put("\n>>> 正在合并所有片段...")
        concat_videos(temp_clips, output_path, log_callback=log_queue.put)

    except Exception as e:
        log_queue.put(f"\n!!!!!! 处理出错 !!!!!!\n错误详情: {e}")
    finally:
        log_queue.put("<<DONE>>") # 发送完成信号

# -------------------------------------------------
# 3. GUI 主应用程序类
# -------------------------------------------------
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
            target=processing_logic_thread,
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

# -------------------------------------------------
# 4. 程序入口
# -------------------------------------------------
if __name__ == "__main__":
    # 前置依赖检查
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (subprocess.CalledProcessError, FileNotFoundError):
        messagebox.showerror("依赖缺失", "错误：找不到 FFmpeg。\n\n请确保您已经正确安装了 FFmpeg，并将其添加到了系统的环境变量 (PATH) 中。")
        sys.exit(1)

    root = TkinterDnD.Tk()
    app = VideoReorderApp(root)
    root.mainloop()
