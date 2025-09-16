import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font
import re
VERSION="1.0"
# --- Drag and Drop Support ---
# This application uses tkinterdnd2 for drag-and-drop functionality.
# If not installed, the feature will be disabled.
# You can install it via pip: pip install tkinterdnd2
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_ENABLED = True
except ImportError:
    DND_ENABLED = False
# -------------------------

class SrtComparer(ttk.Frame):
    def __init__(self, master=None):
        super().__init__(master, padding="10")
        self.master = master
        self.master.title(f"字幕比较工具 v{VERSION}")
        self.grid(sticky=(tk.W, tk.E, tk.N, tk.S))
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)

        self.original_srt_data = []
        self.modified_srt_data = []

        self.setup_styles()
        self.create_widgets()

    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('vista') # or 'clam', 'alt', 'default', 'classic'

        # Define fonts
        self.normal_font = font.Font(family="Segoe UI", size=15)
        self.strikethrough_font = font.Font(family="Segoe UI", size=15, overstrike=True)

        # Configure styles
        self.style.configure('TLabel', font=self.normal_font, wraplength=350, justify=tk.LEFT)
        self.style.configure('TButton', font=self.normal_font, padding=5)
        self.style.configure('TCheckbutton', font=self.normal_font, indicatorpadding=5, wraplength=350)
        self.style.configure('Strikethrough.TCheckbutton', font=self.strikethrough_font, foreground='red', indicatorpadding=5, wraplength=350)

    def create_widgets(self):
        # Top frame for file selection
        top_frame = ttk.Frame(self, padding="0 0 0 10")
        top_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        ttk.Button(top_frame, text="加载原始SRT", command=self.load_original_srt).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(top_frame, text="加载修改SRT", command=self.load_modified_srt).pack(side=tk.LEFT)

        # Main content area
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)

        # Left column (Original)
        ttk.Label(self, text="原始 (可拖放文件)").grid(row=1, column=0, sticky=tk.W, padx=5)
        left_frame = ttk.Frame(self, padding=5)
        left_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(0, weight=1)

        self.left_canvas = tk.Canvas(left_frame, borderwidth=0, highlightthickness=0)
        self.left_list_frame = ttk.Frame(self.left_canvas)
        left_scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.left_canvas.yview)
        self.left_canvas.configure(yscrollcommand=left_scrollbar.set)

        self.left_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        left_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.left_canvas.create_window((0,0), window=self.left_list_frame, anchor="nw")
        self.left_list_frame.bind("<Configure>", lambda e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all")))

        # Right column (Modified)
        ttk.Label(self, text="修改 (可拖放文件)").grid(row=1, column=1, sticky=tk.W, padx=5)
        right_frame = ttk.Frame(self, padding=5)
        right_frame.grid(row=2, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)

        self.right_canvas = tk.Canvas(right_frame, borderwidth=0, highlightthickness=0)
        self.right_list_frame = ttk.Frame(self.right_canvas)
        right_scrollbar = ttk.Scrollbar(right_frame, orient="vertical", command=self.right_canvas.yview)
        self.right_canvas.configure(yscrollcommand=right_scrollbar.set)

        self.right_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.right_canvas.create_window((0,0), window=self.right_list_frame, anchor="nw")
        self.right_list_frame.bind("<Configure>", lambda e: self.right_canvas.configure(scrollregion=self.right_canvas.bbox("all")))

        # Drag and drop setup
        if DND_ENABLED:
            self.left_canvas.drop_target_register(DND_FILES)
            self.left_canvas.dnd_bind('<<Drop>>', self.drop_original)
            self.right_canvas.drop_target_register(DND_FILES)
            self.right_canvas.dnd_bind('<<Drop>>', self.drop_modified)

        # Bottom frame for export
        bottom_frame = ttk.Frame(self)
        bottom_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        bottom_frame.columnconfigure(0, weight=1)
        bottom_frame.columnconfigure(1, weight=1)
        ttk.Button(bottom_frame, text="导出最终SRT", command=self.export_srt).grid(row=0, column=0, sticky=tk.E, padx=5)
        ttk.Button(bottom_frame, text="导出纯文本", command=self.export_txt).grid(row=0, column=1, sticky=tk.W, padx=5)

        # Sync scrollbars
        self.left_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.right_canvas.bind("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        self.left_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.right_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        return "break"

    def parse_srt(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except (UnicodeDecodeError, IOError):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

        srt_blocks = content.strip().split('\n\n')
        parsed_data = []

        block_pattern = re.compile(
            r"^(?P<index>\d+(-D)?)\r?\n"
            r"(?P<start>\d{2}:\d{2}:\d{2},\d{3}) \--> (?P<end>\d{2}:\d{2}:\d{2},\d{3})\r?\n"
            r"(?P<text>.+?)$",
            re.MULTILINE | re.DOTALL
        )

        for block in srt_blocks:
            match = block_pattern.match(block.strip())
            if match:
                data = match.groupdict()
                is_deleted = "-D" in data['index']
                data['index'] = data['index'].replace('-D', '')
                parsed_data.append({
                    'index': int(data['index']),
                    'time': f"{data['start']} --> {data['end']}",
                    'text': data['text'].strip(),
                    'is_deleted': is_deleted
                })
        return parsed_data

    def drop_original(self, event):
        file_path = self.master.tk.splitlist(event.data)[0]
        self.load_srt('original', file_path)

    def drop_modified(self, event):
        file_path = self.master.tk.splitlist(event.data)[0]
        self.load_srt('modified', file_path)

    def load_srt(self, srt_type, file_path=None):
        if not file_path:
            file_path = filedialog.askopenfilename(filetypes=[("SRT files", "*.srt")])

        if not file_path:
            return

        try:
            if not file_path.lower().endswith('.srt'):
                messagebox.showerror("Error", "Please drop a .srt file.")
                return

            data = self.parse_srt(file_path)
            if srt_type == 'original':
                self.original_srt_data = data
            else:
                self.modified_srt_data = data
            self.populate_lists()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse SRT file: {e}")

    def load_original_srt(self):
        self.load_srt('original')

    def load_modified_srt(self):
        self.load_srt('modified')

    def populate_lists(self):
        for widget in self.left_list_frame.winfo_children():
            widget.destroy()
        for widget in self.right_list_frame.winfo_children():
            widget.destroy()

        original_data = self.original_srt_data
        modified_data = self.modified_srt_data

        max_len = max(len(original_data), len(modified_data))

        for i in range(max_len):
            # Populate left list
            if i < len(original_data):
                item = original_data[i]
                text = f"{item['index']}: {item['text']}"
                ttk.Label(self.left_list_frame, text=text).pack(anchor='w', fill='x')

            # Populate right list
            if i < len(modified_data):
                item = modified_data[i]
                var = tk.BooleanVar(value=item.get('is_deleted', False))
                text = f"{item['index']}: {item['text']}"

                cb = ttk.Checkbutton(self.right_list_frame, text=text, variable=var, style='TCheckbutton')
                cb.pack(anchor='w', fill='x')

                def update_style(widget=cb, variable=var):
                    widget.configure(style='Strikethrough.TCheckbutton' if variable.get() else 'TCheckbutton')

                cb.configure(command=update_style)
                update_style()
                item['var'] = var

    def export_srt(self):
        if not self.modified_srt_data:
            messagebox.showerror("Error", "No modified SRT data to export.")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".srt", filetypes=[("SRT files", "*.srt")])
        if not file_path:
            return

        srt_content = []
        for item in self.modified_srt_data:
            index = item['index']
            if item['var'].get():
                index = f"{index}-D"

            srt_content.append(f"{index}\n{item['time']}\n{item['text']}")

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n\n'.join(srt_content) + '\n')

        messagebox.showinfo("Success", f"SRT file saved to {file_path}")

    def export_txt(self):
        if not self.modified_srt_data:
            messagebox.showerror("Error", "No modified SRT data to export.")
            return

        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if not file_path:
            return

        txt_content = []
        for item in self.modified_srt_data:
            if not item['var'].get(): # Only include if not marked for deletion
                txt_content.append(item['text'])

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(txt_content))

        messagebox.showinfo("Success", f"Text file saved to {file_path}")

if __name__ == '__main__':
    if DND_ENABLED:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
        # Only show message if the app is started, not on import
        root.after(100, lambda: messagebox.showinfo("Info", "Drag and drop is disabled.\nPlease install tkinterdnd2 (`pip install tkinterdnd2`) to enable it."))

    root.geometry("900x700")
    app = SrtComparer(master=root)
    app.mainloop()