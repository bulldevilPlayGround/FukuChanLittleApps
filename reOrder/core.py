# ------------------------------------------------- 
# 核心处理逻辑
# ------------------------------------------------- 
import sys
import re
import srt
import subprocess
import os

# ------------------------------------------------- 
# 1. 文件读写与解析
# ------------------------------------------------- 

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

# ------------------------------------------------- 
# 2. 文本处理与字幕匹配
# ------------------------------------------------- 

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

# ------------------------------------------------- 
# 3. FFmpeg 视频处理
# ------------------------------------------------- 

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

# ------------------------------------------------- 
# 4. 后台处理线程
# ------------------------------------------------- 

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
