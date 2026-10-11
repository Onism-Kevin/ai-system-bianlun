# debate_ui.py
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, simpledialog
import threading
import json
import os
import logging
from datetime import datetime
from PIL import Image, ImageTk
from debate_config import ROLES, AVAILABLE_MODELS
from debate_logic import stream_speech, stream_chat
from debate_engine import build_debate_sequence, resolve_role_params, is_debate_round
from debate_utils import text_to_image, generate_wordcloud_from_text

logger = logging.getLogger(__name__)


class DebateApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI辩论赛系统")
        self.root.geometry("1500x850")
        self.root.minsize(1200, 650)

        # 状态变量
        self.debate_history = []
        self.is_running = False
        self.paused = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        
        # 温度：正反方独立控制
        self.temp_zheng = tk.DoubleVar(value=0.5)
        self.temp_fan = tk.DoubleVar(value=0.7)
        
        # 模型：正反方独立选择
        self.model_zheng = tk.StringVar(value="llama3.2")
        self.model_fan = tk.StringVar(value="gemma3:1b")
        self.model_judge = tk.StringVar(value="qwen3.5:4b")
        
        # 模式选择
        self.mode_var = tk.StringVar(value="AI vs AI")
        
        # 发言轮次控制
        self.max_turns = tk.IntVar(value=5)
        self.turn_count = 0
        
        self.avatar_zheng_path = None
        self.avatar_fan_path = None
        self.current_theme = "dark"
        self.current_font = "微软雅黑"
        self.is_quick_mode = False
        self.quick_activated = False
        self.pause_phase_index = 0
        self.current_topic = ""
        self.current_temp = 0.5
        self.debate_thread = None
        self.current_full_reply = ""
        
        # 人 vs AI 模式状态
        self.waiting_for_user = False
        self.ai_first_speech_done = False
        self.is_ai_speaking = False
        self.user_role = "正方"

        # 昵称
        self.nickname_zheng = "正方辩手"
        self.nickname_fan = "反方辩手"

        # 头像提示词（默认值）
        self.zheng_prompt_default = "a cute cartoon character debater, affirmative side, professional, confident, cheerful, avatar, flat illustration, bright colors, simple background"
        self.fan_prompt_default = "a cute cartoon character debater, negative side, professional, thoughtful, serious, avatar, flat illustration, bright colors, simple background"

        # 主题配置
        self.themes = {
            "dark": {
                "bg": "#1e1e2e",
                "fg": "#cdd6f4",
                "frame_bg": "#313244",
                "entry_bg": "#45475a",
                "btn_bg": "#89b4fa",
                "btn_fg": "#1e1e2e",
                "accent": "#cba6f7",
                "success": "#a6e3a1",
                "danger": "#f38ba8",
                "border": "#6c7086",
                "zheng_bg": "#1a2a3a",
                "fan_bg": "#3a1a1a",
                "img_bg": "#313244"
            },
            "light": {
                "bg": "#eff1f5",
                "fg": "#4c4f69",
                "frame_bg": "#dce0e8",
                "entry_bg": "#e6e9ef",
                "btn_bg": "#7287fd",
                "btn_fg": "#ffffff",
                "accent": "#8839ef",
                "success": "#40a02b",
                "danger": "#d20f39",
                "border": "#9ca0b0",
                "zheng_bg": "#d4e4f7",
                "fan_bg": "#f7d4d4",
                "img_bg": "#dce0e8"
            },
            "colorful": {
                "bg": "#f8f0e5",
                "fg": "#2d2a24",
                "frame_bg": "#e8dcc8",
                "entry_bg": "#fdf6ed",
                "btn_bg": "#e67e22",
                "btn_fg": "#ffffff",
                "accent": "#8e44ad",
                "success": "#27ae60",
                "danger": "#e74c3c",
                "border": "#b8a99a",
                "zheng_bg": "#f0e6d4",
                "fan_bg": "#f0d4d4",
                "img_bg": "#e8dcc8"
            }
        }

        self.fonts = {
            "微软雅黑": ("微软雅黑", 11),
            "宋体": ("宋体", 11),
            "黑体": ("黑体", 11),
            "Helvetica": ("Helvetica", 11),
            "Arial": ("Arial", 11)
        }

        self.left_frame = None
        self.mid_frame = None
        self.right_frame = None
        self.input_frame = None

        self.setup_ui()
        self.apply_theme()

    def setup_ui(self):
        """构建界面"""
        # ========== 顶部标题栏 ==========
        self.title_frame = tk.Frame(self.root, height=55)
        self.title_frame.pack(fill=tk.X, padx=10, pady=5)

        title_label = tk.Label(
            self.title_frame,
            text="AI 辩论赛系统",
            font=('Helvetica', 22, 'bold')
        )
        title_label.pack(side=tk.LEFT, padx=10)

        # 主题切换按钮
        theme_btn_frame = tk.Frame(self.title_frame)
        theme_btn_frame.pack(side=tk.RIGHT, padx=10)

        themes = [("深色", "dark"), ("浅色", "light"), ("彩色", "colorful")]
        for text, theme in themes:
            btn = self._create_flat_button(
                theme_btn_frame, text,
                lambda t=theme: self.switch_theme(t),
                width=6
            )
            btn.pack(side=tk.LEFT, padx=2)

        tk.Label(theme_btn_frame, text="字体:", font=('Helvetica', 10)).pack(side=tk.LEFT, padx=(10, 5))
        self.font_var = tk.StringVar(value="微软雅黑")
        font_menu = ttk.Combobox(
            theme_btn_frame,
            textvariable=self.font_var,
            values=list(self.fonts.keys()),
            width=10,
            state="readonly"
        )
        font_menu.pack(side=tk.LEFT, padx=2)
        font_menu.bind("<<ComboboxSelected>>", lambda e: self.switch_font())

        # ========== 控制面板 ==========
        self.control_frame = tk.Frame(self.root, relief=tk.FLAT, bd=2)
        self.control_frame.pack(fill=tk.X, padx=10, pady=5)

        # 第一行：辩题 + 模式选择 + 轮次
        row1 = tk.Frame(self.control_frame)
        row1.pack(fill=tk.X, padx=10, pady=3)

        tk.Label(row1, text="辩题：", font=('Helvetica', 11)).pack(side=tk.LEFT, padx=5)
        self.topic_entry = tk.Entry(row1, width=25, font=('Helvetica', 11), relief=tk.FLAT, bd=2)
        self.topic_entry.pack(side=tk.LEFT, padx=5)
        self.topic_entry.insert(0, "该不该用AI来学编程？")
        self.topic_entry.bind("<Return>", lambda e: self.start_debate())

        # 模式选择
        tk.Label(row1, text="模式：", font=('Helvetica', 11)).pack(side=tk.LEFT, padx=(10, 5))
        mode_menu = ttk.Combobox(
            row1,
            textvariable=self.mode_var,
            values=["AI vs AI", "人 vs AI"],
            width=10,
            state="readonly"
        )
        mode_menu.pack(side=tk.LEFT, padx=5)
        mode_menu.bind("<<ComboboxSelected>>", self._on_mode_change)

        # 轮次控制
        tk.Label(row1, text="轮次：", font=('Helvetica', 11)).pack(side=tk.LEFT, padx=(10, 5))
        self.turns_spinbox = tk.Spinbox(
            row1,
            from_=1, to=20,
            width=4,
            textvariable=self.max_turns,
            font=('Helvetica', 11),
            relief=tk.FLAT, bd=2
        )
        self.turns_spinbox.pack(side=tk.LEFT, padx=5)

        self.progress_bar = ttk.Progressbar(row1, length=80, mode='indeterminate')
        self.progress_bar.pack(side=tk.LEFT, padx=10)
        self.progress_bar.pack_forget()

        # 第二行：主按钮
        row_buttons = tk.Frame(self.control_frame)
        row_buttons.pack(fill=tk.X, padx=10, pady=3)

        self.start_btn = self._create_flat_button(
            row_buttons, "开始辩论", self.start_debate,
            width=10, bg_color="#a6e3a1", fg_color="#1e1e2e"
        )
        self.start_btn.pack(side=tk.LEFT, padx=3)

        self.quick_btn = self._create_flat_button(
            row_buttons, "一键加速", self.quick_debate,
            width=10, bg_color="#f9e2af", fg_color="#1e1e2e",
            state=tk.DISABLED
        )
        self.quick_btn.pack(side=tk.LEFT, padx=3)

        self.pause_btn = self._create_flat_button(
            row_buttons, "暂停", self.toggle_pause,
            width=8, bg_color="#f38ba8", fg_color="#1e1e2e",
            state=tk.DISABLED
        )
        self.pause_btn.pack(side=tk.LEFT, padx=3)

        self.restart_btn = self._create_flat_button(
            row_buttons, "重新开始", self.restart_debate,
            width=10, bg_color="#f5c2e7", fg_color="#1e1e2e",
            state=tk.DISABLED
        )
        self.restart_btn.pack(side=tk.LEFT, padx=3)

        # 第三行：功能按钮
        row2 = tk.Frame(self.control_frame)
        row2.pack(fill=tk.X, padx=10, pady=3)

        func_buttons = [
            ("存档", self.save_history, "#89b4fa"),
            ("载入", self.load_history, "#b4befe"),
            ("词云", self.generate_wordcloud_from_debate, "#94e2d5"),
            ("文生图", self.generate_image_from_prompt, "#f5c2e7"),
        ]

        for text, cmd, color in func_buttons:
            btn = self._create_flat_button(
                row2, text, cmd,
                bg_color=color, fg_color="#1e1e2e",
                width=8
            )
            btn.pack(side=tk.LEFT, padx=3)

        # ========== 主区域 ==========
        self.main_paned = tk.PanedWindow(
            self.root, orient=tk.HORIZONTAL,
            sashwidth=4, sashrelief=tk.FLAT
        )
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # ---- 左：正方区域 ----
        self.left_frame = tk.Frame(self.main_paned, relief=tk.RIDGE, bd=2)
        self.main_paned.add(self.left_frame, width=450, minsize=300)

        zheng_header = tk.Frame(self.left_frame)
        zheng_header.pack(fill=tk.X, padx=8, pady=8)

        self.zheng_img_label = tk.Label(
            zheng_header, text="",
            font=('Helvetica', 20),
            width=14, height=7,
            relief=tk.RIDGE, bd=3,
            bg='#2E86C1'
        )
        self.zheng_img_label.pack(side=tk.LEFT, padx=10, pady=5)

        zheng_info = tk.Frame(zheng_header)
        zheng_info.pack(side=tk.LEFT, padx=15, pady=5)

        self.zheng_nickname_label = tk.Label(
            zheng_info,
            text=self.nickname_zheng,
            font=('Helvetica', 16, 'bold'),
            fg='#2E86C1'
        )
        self.zheng_nickname_label.pack(anchor=tk.W)
        self.zheng_nickname_label.bind("<Double-Button-1>", lambda e: self.edit_nickname("正方"))

        # 正方温度
        zheng_temp_frame = tk.Frame(zheng_info)
        zheng_temp_frame.pack(anchor=tk.W, pady=2)
        tk.Label(zheng_temp_frame, text="温度:", font=('Helvetica', 10)).pack(side=tk.LEFT)
        self.zheng_temp_scale = tk.Scale(
            zheng_temp_frame, from_=0.0, to=1.0,
            resolution=0.1, orient=tk.HORIZONTAL,
            variable=self.temp_zheng, length=80,
            highlightthickness=0, sliderlength=12, width=6
        )
        self.zheng_temp_scale.pack(side=tk.LEFT, padx=5)
        self.zheng_temp_label = tk.Label(zheng_temp_frame, text="0.5", font=('Helvetica', 9, 'bold'), width=3)
        self.zheng_temp_label.pack(side=tk.LEFT)
        self.zheng_temp_scale.configure(
            command=lambda v: self.zheng_temp_label.config(text=f"{float(v):.1f}")
        )

        # 正方模型选择
        zheng_model_frame = tk.Frame(zheng_info)
        zheng_model_frame.pack(anchor=tk.W, pady=2)
        tk.Label(zheng_model_frame, text="模型:", font=('Helvetica', 10)).pack(side=tk.LEFT)
        self.zheng_model_menu = ttk.Combobox(
            zheng_model_frame,
            textvariable=self.model_zheng,
            values=AVAILABLE_MODELS,
            width=12,
            state="readonly"
        )
        self.zheng_model_menu.pack(side=tk.LEFT, padx=5)

        # 正方头像提示词（双击弹出编辑窗口）
        zheng_prompt_frame = tk.Frame(zheng_info)
        zheng_prompt_frame.pack(anchor=tk.W, pady=2)

        tk.Label(zheng_prompt_frame, text="提示词:", font=('Helvetica', 9)).pack(side=tk.LEFT)
        self.zheng_prompt_entry = tk.Entry(zheng_prompt_frame, width=22, font=('Helvetica', 9))
        self.zheng_prompt_entry.pack(side=tk.LEFT, padx=3)
        self.zheng_prompt_entry.insert(0, self.zheng_prompt_default)
        # 双击弹出编辑窗口
        self.zheng_prompt_entry.bind("<Double-Button-1>", lambda e: self._edit_prompt("正方"))

        # 正方按钮
        zheng_btn_frame = tk.Frame(zheng_info)
        zheng_btn_frame.pack(anchor=tk.W, pady=3)
        tk.Button(
            zheng_btn_frame,
            text="加载头像",
            command=lambda: self.load_avatar("正方"),
            font=('Helvetica', 9),
            padx=8, pady=2
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            zheng_btn_frame,
            text="AI生成",
            command=lambda: self.generate_avatar("正方"),
            font=('Helvetica', 9),
            padx=8, pady=2
        ).pack(side=tk.LEFT, padx=3)

        self.zheng_chat = scrolledtext.ScrolledText(
            self.left_frame, wrap=tk.WORD,
            font=('Helvetica', 11), height=18,
            relief=tk.FLAT, bd=2
        )
        self.zheng_chat.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)
        self.zheng_chat.tag_configure("发言", foreground="#2E86C1", font=('Helvetica', 11))
        self.zheng_chat.tag_configure("标题", foreground="#1a5276", font=('Helvetica', 12, 'bold'))
        self.zheng_chat.tag_configure("系统", foreground="#95a5a6", font=('Helvetica', 10, 'italic'))
        self.zheng_chat.tag_configure("用户", foreground="#FF6B6B", font=('Helvetica', 11, 'bold'))
        self.zheng_chat.insert(tk.END, "等待正方发言...\n", "系统")

        # ---- 中：反方区域 ----
        self.mid_frame = tk.Frame(self.main_paned, relief=tk.RIDGE, bd=2)
        self.main_paned.add(self.mid_frame, width=450, minsize=300)

        fan_header = tk.Frame(self.mid_frame)
        fan_header.pack(fill=tk.X, padx=8, pady=8)

        self.fan_img_label = tk.Label(
            fan_header, text="",
            font=('Helvetica', 20),
            width=14, height=7,
            relief=tk.RIDGE, bd=3,
            bg='#E74C3C'
        )
        self.fan_img_label.pack(side=tk.LEFT, padx=10, pady=5)

        fan_info = tk.Frame(fan_header)
        fan_info.pack(side=tk.LEFT, padx=15, pady=5)

        self.fan_nickname_label = tk.Label(
            fan_info,
            text=self.nickname_fan,
            font=('Helvetica', 16, 'bold'),
            fg='#E74C3C'
        )
        self.fan_nickname_label.pack(anchor=tk.W)
        self.fan_nickname_label.bind("<Double-Button-1>", lambda e: self.edit_nickname("反方"))

        # 反方温度
        fan_temp_frame = tk.Frame(fan_info)
        fan_temp_frame.pack(anchor=tk.W, pady=2)
        tk.Label(fan_temp_frame, text="温度:", font=('Helvetica', 10)).pack(side=tk.LEFT)
        self.fan_temp_scale = tk.Scale(
            fan_temp_frame, from_=0.0, to=1.0,
            resolution=0.1, orient=tk.HORIZONTAL,
            variable=self.temp_fan, length=80,
            highlightthickness=0, sliderlength=12, width=6
        )
        self.fan_temp_scale.pack(side=tk.LEFT, padx=5)
        self.fan_temp_label = tk.Label(fan_temp_frame, text="0.7", font=('Helvetica', 9, 'bold'), width=3)
        self.fan_temp_label.pack(side=tk.LEFT)
        self.fan_temp_scale.configure(
            command=lambda v: self.fan_temp_label.config(text=f"{float(v):.1f}")
        )

        # 反方模型选择
        fan_model_frame = tk.Frame(fan_info)
        fan_model_frame.pack(anchor=tk.W, pady=2)
        tk.Label(fan_model_frame, text="模型:", font=('Helvetica', 10)).pack(side=tk.LEFT)
        self.fan_model_menu = ttk.Combobox(
            fan_model_frame,
            textvariable=self.model_fan,
            values=AVAILABLE_MODELS,
            width=12,
            state="readonly"
        )
        self.fan_model_menu.pack(side=tk.LEFT, padx=5)

        # 反方头像提示词（双击弹出编辑窗口）
        fan_prompt_frame = tk.Frame(fan_info)
        fan_prompt_frame.pack(anchor=tk.W, pady=2)

        tk.Label(fan_prompt_frame, text="提示词:", font=('Helvetica', 9)).pack(side=tk.LEFT)
        self.fan_prompt_entry = tk.Entry(fan_prompt_frame, width=22, font=('Helvetica', 9))
        self.fan_prompt_entry.pack(side=tk.LEFT, padx=3)
        self.fan_prompt_entry.insert(0, self.fan_prompt_default)
        # 双击弹出编辑窗口
        self.fan_prompt_entry.bind("<Double-Button-1>", lambda e: self._edit_prompt("反方"))

        # 反方按钮
        fan_btn_frame = tk.Frame(fan_info)
        fan_btn_frame.pack(anchor=tk.W, pady=3)
        tk.Button(
            fan_btn_frame,
            text="加载头像",
            command=lambda: self.load_avatar("反方"),
            font=('Helvetica', 9),
            padx=8, pady=2
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            fan_btn_frame,
            text="AI生成",
            command=lambda: self.generate_avatar("反方"),
            font=('Helvetica', 9),
            padx=8, pady=2
        ).pack(side=tk.LEFT, padx=3)

        self.fan_chat = scrolledtext.ScrolledText(
            self.mid_frame, wrap=tk.WORD,
            font=('Helvetica', 11), height=18,
            relief=tk.FLAT, bd=2
        )
        self.fan_chat.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)
        self.fan_chat.tag_configure("发言", foreground="#E74C3C", font=('Helvetica', 11))
        self.fan_chat.tag_configure("标题", foreground="#7b1a1a", font=('Helvetica', 12, 'bold'))
        self.fan_chat.tag_configure("系统", foreground="#95a5a6", font=('Helvetica', 10, 'italic'))
        self.fan_chat.tag_configure("用户", foreground="#FF6B6B", font=('Helvetica', 11, 'bold'))
        self.fan_chat.insert(tk.END, "等待反方发言...\n", "系统")

        # ---- 右：图片展示区 ----
        self.right_frame = tk.Frame(self.main_paned, relief=tk.RIDGE, bd=2)
        self.main_paned.add(self.right_frame, width=350, minsize=200)

        img_title = tk.Label(
            self.right_frame,
            text="词云 / 头像展示",
            font=('Helvetica', 12, 'bold')
        )
        img_title.pack(pady=5)

        self.img_display = tk.Label(
            self.right_frame,
            text="点击「词云」或「文生图」\n生成图片将显示在此处",
            font=('Helvetica', 12),
            relief=tk.RIDGE, bd=2
        )
        self.img_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ========== 底部输入区域（人 vs AI 模式） ==========
        self.input_frame = tk.Frame(self.root, height=50)
        self.input_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(self.input_frame, text="代表:", font=('Helvetica', 10)).pack(side=tk.RIGHT, padx=5)
        self.side_var = tk.StringVar(value="正方")
        side_menu = ttk.Combobox(
            self.input_frame,
            textvariable=self.side_var,
            values=["正方", "反方"],
            width=6,
            state="readonly"
        )
        side_menu.pack(side=tk.RIGHT, padx=5)

        self.send_btn = self._create_flat_button(
            self.input_frame, "发送", self.send_user_message,
            width=8, bg_color="#89b4fa", fg_color="#1e1e2e"
        )
        self.send_btn.pack(side=tk.RIGHT, padx=5)

        self.input_entry = tk.Entry(self.input_frame, font=('Helvetica', 11), relief=tk.FLAT, bd=2)
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.input_entry.bind("<Return>", self.send_user_message)

        # 默认隐藏输入区域
        self.input_frame.pack_forget()

        # 底部状态栏
        self.status_frame = tk.Frame(self.root, height=30)
        self.status_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

        self.status_label = tk.Label(
            self.status_frame, 
            text=f"就绪 | 模式: AI vs AI | 正方: {self.model_zheng.get()} (0.5) | 反方: {self.model_fan.get()} (0.7)",
            font=('Helvetica', 10)
        )
        self.status_label.pack(side=tk.LEFT, padx=10)

        self.turn_counter = tk.Label(
            self.status_frame, text="轮次: 0",
            font=('Helvetica', 10)
        )
        self.turn_counter.pack(side=tk.RIGHT, padx=10)

        # 绑定更新
        try:
            self.model_zheng.trace_add('write', self._update_status)
            self.model_fan.trace_add('write', self._update_status)
            self.temp_zheng.trace_add('write', self._update_status)
            self.temp_fan.trace_add('write', self._update_status)
            self.mode_var.trace_add('write', self._update_status)
        except AttributeError:
            self.model_zheng.trace('w', self._update_status)
            self.model_fan.trace('w', self._update_status)
            self.temp_zheng.trace('w', self._update_status)
            self.temp_fan.trace('w', self._update_status)
            self.mode_var.trace('w', self._update_status)

    def _update_status(self, *args):
        mode = self.mode_var.get()
        self.status_label.config(
            text=f"就绪 | 模式: {mode} | 轮次: {self.max_turns.get()} | 正方: {self.model_zheng.get()} ({self.temp_zheng.get():.1f}) | 反方: {self.model_fan.get()} ({self.temp_fan.get():.1f})"
        )

    def _on_mode_change(self, *args):
        mode = self.mode_var.get()
        if mode == "人 vs AI":
            self.input_frame.pack(fill=tk.X, padx=10, pady=5)
            self.status_label.config(text="人 vs AI 模式：选择代表方，输入你的发言")
        else:
            self.input_frame.pack_forget()
            self.status_label.config(text="AI vs AI 模式：双方由AI自动辩论")

    def _edit_prompt(self, role):
        """双击提示词输入框弹出编辑窗口"""
        if role == "正方":
            current_text = self.zheng_prompt_entry.get()
            title = "编辑正方头像提示词"
        else:
            current_text = self.fan_prompt_entry.get()
            title = "编辑反方头像提示词"
        
        # 创建编辑窗口
        edit_window = tk.Toplevel(self.root)
        edit_window.title(title)
        edit_window.geometry("600x200")
        edit_window.configure(bg=self.themes[self.current_theme]["bg"])
        edit_window.transient(self.root)
        edit_window.grab_set()
        
        # 提示标签
        tk.Label(
            edit_window,
            text="提示词（将用于AI生成头像）：",
            font=('Helvetica', 11),
            bg=self.themes[self.current_theme]["bg"],
            fg=self.themes[self.current_theme]["fg"]
        ).pack(pady=10)
        
        # 多行文本框
        text_widget = tk.Text(
            edit_window,
            wrap=tk.WORD,
            font=('Helvetica', 11),
            height=5,
            relief=tk.FLAT, bd=2,
            bg=self.themes[self.current_theme]["entry_bg"],
            fg=self.themes[self.current_theme]["fg"]
        )
        text_widget.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        text_widget.insert("1.0", current_text)
        text_widget.focus_set()
        
        # 按钮框架
        btn_frame = tk.Frame(edit_window, bg=self.themes[self.current_theme]["bg"])
        btn_frame.pack(pady=10)
        
        def save_prompt():
            new_text = text_widget.get("1.0", tk.END).strip()
            if new_text:
                if role == "正方":
                    self.zheng_prompt_entry.delete(0, tk.END)
                    self.zheng_prompt_entry.insert(0, new_text)
                else:
                    self.fan_prompt_entry.delete(0, tk.END)
                    self.fan_prompt_entry.insert(0, new_text)
                edit_window.destroy()
                self.status_label.config(text=f"{role}提示词已更新")
        
        tk.Button(
            btn_frame,
            text="保存",
            command=save_prompt,
            font=('Helvetica', 11),
            bg='#a6e3a1', fg='#1e1e2e',
            padx=20, pady=5,
            relief=tk.FLAT
        ).pack(side=tk.LEFT, padx=10)
        
        tk.Button(
            btn_frame,
            text="取消",
            command=edit_window.destroy,
            font=('Helvetica', 11),
            bg='#f38ba8', fg='#1e1e2e',
            padx=20, pady=5,
            relief=tk.FLAT
        ).pack(side=tk.LEFT, padx=10)

    def send_user_message(self, event=None):
        """发送用户消息（人 vs AI 模式）- 用户发言后AI回应，完成一轮"""
        if not self.is_running:
            self.insert_colored_text("系统", "请先点击「开始辩论」\n")
            return

        if self.mode_var.get() != "人 vs AI":
            self.insert_colored_text("系统", "当前不是「人 vs AI」模式\n")
            return

        if not self.waiting_for_user:
            self.insert_colored_text("系统", "请等待AI完成发言\n")
            return

        msg = self.input_entry.get().strip()
        if not msg:
            return
        self.input_entry.delete(0, tk.END)

        role = self.side_var.get()

        # 显示用户发言
        if role == "正方":
            self.zheng_chat.insert(tk.END, f"\n【你】(正方) 第{self.turn_count + 1}轮\n", "标题")
            self.zheng_chat.insert(tk.END, f"{msg}\n", "用户")
            self.zheng_chat.see(tk.END)
        else:
            self.fan_chat.insert(tk.END, f"\n【你】(反方) 第{self.turn_count + 1}轮\n", "标题")
            self.fan_chat.insert(tk.END, f"{msg}\n", "用户")
            self.fan_chat.see(tk.END)

        self.debate_history.append({
            "role": role,
            "phase": f"用户发言 第{self.turn_count + 1}轮",
            "content": msg
        })

        # AI以另一方身份回应
        ai_role = "反方" if role == "正方" else "正方"
        self.waiting_for_user = False
        self._trigger_ai_response(ai_role, msg, is_user_turn=True)

    def _trigger_ai_response(self, role, user_msg, is_user_turn=False):
        """触发AI回应（辩论阶段）"""
        self.is_ai_speaking = True
        self.status_label.config(text=f"AI {role} 正在思考...")

        # 在主线程快照所有 Tk 变量，后台线程禁止访问 Tk 对象
        topic = self.topic_entry.get().strip()
        if not topic:
            topic = self.current_topic or "当前辩题"
        if role == "正方":
            temp, model = resolve_role_params("正方", self.temp_zheng.get(), self.model_zheng.get())
            stance = "支持"
            system_prompt = f"""你是一位优秀的正方辩手，请针对用户刚才的发言进行有力反驳或补充论证。
        辩题：{topic}
        你的立场：坚决{stance}辩题。

        用户刚才的发言是：「{user_msg}」
        请严格按照以下要求回应：
        1. 首先直接回应用户发言中的核心观点
        2. 指出用户观点中的漏洞或不足
        3. 补充你的新论证来强化{stance}辩题的立场
        4. 保持语言生动有力，每次发言控制在200字左右"""
            title_text = "【AI · 正方回应】"
        else:
            temp, model = resolve_role_params("反方", self.temp_fan.get(), self.model_fan.get())
            stance = "反对"
            system_prompt = f"""你是一位犀利的反方辩手，请针对用户刚才的发言进行有力反驳或补充论证。
        辩题：{topic}
        你的立场：坚决{stance}辩题。

        用户刚才的发言是：「{user_msg}」
        请严格按照以下要求回应：
        1. 首先直接回应用户发言中的核心观点
        2. 指出用户观点中的漏洞或不足
        3. 补充你的新论证来强化{stance}辩题的立场
        4. 保持语言犀利干脆，一击即中，每次发言控制在200字左右"""
            title_text = "【AI · 反方回应】"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请回应用户的发言：「{user_msg}」"}
        ]
        max_turns = self.max_turns.get()

        def task():
            try:
                if self.paused:
                    self.pause_event.wait()
                if not self.is_running:
                    return

                full_reply = ""
                if role == "正方":
                    self.root.after(0, lambda: self.zheng_chat.insert(tk.END, f"\n{title_text}\n", "标题"))
                else:
                    self.root.after(0, lambda: self.fan_chat.insert(tk.END, f"\n{title_text}\n", "标题"))

                for content in stream_chat(model, messages, temperature=temp, timeout=120):
                    if self.paused:
                        self.pause_event.wait()
                    if not self.is_running:
                        return
                    full_reply += content
                    if role == "正方":
                        self.root.after(0, lambda c=content: self.zheng_chat.insert(tk.END, c, "发言"))
                        self.root.after(0, lambda: self.zheng_chat.see(tk.END))
                    else:
                        self.root.after(0, lambda c=content: self.fan_chat.insert(tk.END, c, "发言"))
                        self.root.after(0, lambda: self.fan_chat.see(tk.END))
                
                if full_reply:
                    # 只有用户发言触发的AI回应才增加轮次
                    if is_user_turn:
                        self.turn_count += 1
                    
                    self.debate_history.append({
                        "role": role, 
                        "phase": f"AI回应 第{self.turn_count}轮", 
                        "content": full_reply
                    })
                    self.root.after(0, lambda: self.turn_counter.config(
                        text=f"轮次: {self.turn_count}/{max_turns}"
                    ))
                    
                    # 检查是否达到轮次限制
                    if self.turn_count >= max_turns:
                        self.root.after(0, lambda: self.insert_colored_text("系统", f"\n轮次已满（{max_turns}轮），正在生成裁判评判...\n"))
                        self.root.after(0, self._trigger_judge)
                        self.is_ai_speaking = False
                        return
                    
                    # 继续下一轮：轮到用户
                    user_role = "反方" if role == "正方" else "正方"
                    self.root.after(0, lambda: self.status_label.config(text=f"AI 回应完成，轮到你了（{user_role}）第{self.turn_count + 1}轮"))
                    self.root.after(0, lambda: self.insert_colored_text("系统", f"\n【提示】轮到你了（{user_role}），第{self.turn_count + 1}轮\n"))
                    self.waiting_for_user = True
                    self.is_ai_speaking = False
                    
            except Exception as e:
                self.root.after(0, lambda: self.insert_colored_text("系统", f"\n错误: {e}\n"))
                self.is_ai_speaking = False
            finally:
                self.root.after(0, lambda: self.show_progress(False))
        
        self.show_progress(True)
        threading.Thread(target=task, daemon=True).start()

    def _trigger_ai_first_speech(self, role):
        """人 vs AI 模式：AI先发言（立论）"""
        self.is_ai_speaking = True
        self.status_label.config(text=f"AI {role} 正在立论...")
        self.waiting_for_user = False

        # 在主线程快照所有 Tk 变量，后台线程禁止访问 Tk 对象
        topic = self.topic_entry.get().strip()
        if not topic:
            topic = self.current_topic or "当前辩题"
        if role == "正方":
            temp, model = resolve_role_params("正方", self.temp_zheng.get(), self.model_zheng.get())
            stance = "支持"
            system_prompt = f"""你是一位优秀的正方辩手，请进行开场立论。
        辩题：{topic}
        你的立场：坚决{stance}辩题。

        请严格按照以下要求：
        1. 清晰阐述你方核心观点，即为什么应该{stance}辩题
        2. 提供有力的论证
        3. 语言生动有力，每次发言控制在200字左右"""
            title_text = "【AI · 正方立论】"
        else:
            temp, model = resolve_role_params("反方", self.temp_fan.get(), self.model_fan.get())
            stance = "反对"
            system_prompt = f"""你是一位犀利的反方辩手，请进行开场立论。
        辩题：{topic}
        你的立场：坚决{stance}辩题。

        请严格按照以下要求：
        1. 清晰阐述你方核心观点，即为什么应该{stance}辩题
        2. 提供有力的论证
        3. 语言犀利干脆，每次发言控制在200字左右"""
            title_text = "【AI · 反方立论】"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请为辩题「{topic}」进行开场立论"}
        ]
        max_turns = self.max_turns.get()

        def task():
            try:
                if self.paused:
                    self.pause_event.wait()
                if not self.is_running:
                    return

                full_reply = ""
                if role == "正方":
                    self.root.after(0, lambda: self.zheng_chat.insert(tk.END, f"\n{title_text}\n", "标题"))
                else:
                    self.root.after(0, lambda: self.fan_chat.insert(tk.END, f"\n{title_text}\n", "标题"))

                for content in stream_chat(model, messages, temperature=temp, timeout=120):
                    if self.paused:
                        self.pause_event.wait()
                    if not self.is_running:
                        return
                    full_reply += content
                    if role == "正方":
                        self.root.after(0, lambda c=content: self.zheng_chat.insert(tk.END, c, "发言"))
                        self.root.after(0, lambda: self.zheng_chat.see(tk.END))
                    else:
                        self.root.after(0, lambda c=content: self.fan_chat.insert(tk.END, c, "发言"))
                        self.root.after(0, lambda: self.fan_chat.see(tk.END))

                if full_reply:
                    # AI立论增加轮次
                    self.turn_count += 1
                    self.debate_history.append({
                        "role": role, 
                        "phase": "AI立论", 
                        "content": full_reply
                    })
                    self.root.after(0, lambda: self.turn_counter.config(
                        text=f"轮次: {self.turn_count}/{max_turns}"
                    ))
                    
                    # 立论完成后，轮到用户
                    user_role = "反方" if role == "正方" else "正方"
                    self.root.after(0, lambda: self.status_label.config(text=f"AI 立论完成，轮到你了（{user_role}）第{self.turn_count + 1}轮"))
                    self.root.after(0, lambda: self.insert_colored_text("系统", f"\n【提示】轮到你了（{user_role}），第{self.turn_count + 1}轮\n"))
                    self.waiting_for_user = True
                    self.ai_first_speech_done = True
                    self.is_ai_speaking = False
                    
            except Exception as e:
                self.root.after(0, lambda: self.insert_colored_text("系统", f"\n错误: {e}\n"))
                self.is_ai_speaking = False
            finally:
                self.root.after(0, lambda: self.show_progress(False))
        
        self.show_progress(True)
        threading.Thread(target=task, daemon=True).start()

    def _trigger_judge(self):
        """触发裁判评判 - 优化版"""
        if not self.debate_history:
            return
        
        self.status_label.config(text="裁判正在评判...")
        self.insert_colored_text("系统", "\n【裁判评判】\n")

        # 在主线程快照所有 Tk 变量，后台线程禁止访问 Tk 对象
        topic = self.topic_entry.get().strip()
        if not topic:
            topic = self.current_topic or "当前辩题"
        temp, model = resolve_role_params("裁判", model_override=self.model_judge.get())

        def task():
            try:
                system_prompt = f"""你是辩论赛裁判，请对以下辩论进行简洁评判。
        辩题：{topic}

        要求：
        1. 评价双方论点的质量和反驳力度
        2. 指出双方的亮点与不足
        3. 给出建设性总结（100字以内）"""
                
                recent_history = self.debate_history[-12:] if len(self.debate_history) > 12 else self.debate_history
                
                history_text = "\n".join([
                    f"【{entry['role']}】{entry['content'][:300]}..." if len(entry['content']) > 300 else f"【{entry['role']}】{entry['content']}"
                    for entry in recent_history
                ])
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请评判以下辩论内容：\n{history_text}"}
                ]
                
                if self.paused:
                    self.pause_event.wait()
                if not self.is_running:
                    return

                full_reply = ""
                for content in stream_chat(model, messages, temperature=temp, timeout=180):
                    if self.paused:
                        self.pause_event.wait()
                    if not self.is_running:
                        return
                    full_reply += content
                    self.root.after(0, lambda c=content: self._insert_judge_text(c))
                
                if full_reply:
                    self.debate_history.append({"role": "裁判", "phase": "评判", "content": full_reply})
                    self.root.after(0, lambda: self.status_label.config(text="辩论结束"))
                    self.root.after(0, self.debate_finished)
                    
            except Exception as e:
                self.root.after(0, lambda: self.insert_colored_text("系统", f"\n裁判评判错误: {e}\n"))
            finally:
                self.root.after(0, lambda: self.show_progress(False))
        
        self.show_progress(True)
        threading.Thread(target=task, daemon=True).start()

    def _insert_judge_text(self, text):
        """插入裁判文本（不带额外标签）"""
        self.zheng_chat.insert(tk.END, text, "系统")
        self.fan_chat.insert(tk.END, text, "系统")
        self.zheng_chat.see(tk.END)
        self.fan_chat.see(tk.END)

    # ========== 以下方法保持不变 ==========
    
    def edit_nickname(self, role):
        current = self.nickname_zheng if role == "正方" else self.nickname_fan
        new_name = simpledialog.askstring("修改昵称", f"请输入{role}的新昵称：", initialvalue=current)
        if new_name and new_name.strip():
            if role == "正方":
                self.nickname_zheng = new_name.strip()
                self.zheng_nickname_label.config(text=self.nickname_zheng)
            else:
                self.nickname_fan = new_name.strip()
                self.fan_nickname_label.config(text=self.nickname_fan)

    def load_avatar(self, role):
        from debate_utils import load_avatar_from_file
        path = load_avatar_from_file(self.root, f"选择{role}头像")
        if path:
            if role == "正方":
                self.avatar_zheng_path = path
                self._display_avatar_in_label(path, self.zheng_img_label)
                self._display_image(path)
            else:
                self.avatar_fan_path = path
                self._display_avatar_in_label(path, self.fan_img_label)
                self._display_image(path)
            self.status_label.config(text=f"{role}头像已加载")

    def generate_avatar(self, role):
        if role == "正方":
            prompt = self.zheng_prompt_entry.get().strip()
            if not prompt:
                prompt = self.zheng_prompt_default
        else:
            prompt = self.fan_prompt_entry.get().strip()
            if not prompt:
                prompt = self.fan_prompt_default

        self.show_progress(True)
        self.status_label.config(text=f"正在生成{role}头像...")

        def task():
            try:
                img_path = text_to_image(prompt)
                if img_path:
                    label = self.zheng_img_label if role == "正方" else self.fan_img_label
                    if role == "正方":
                        self.avatar_zheng_path = img_path
                    else:
                        self.avatar_fan_path = img_path
                    self.root.after(0, lambda: self._display_avatar_in_label(img_path, label))
                    self.root.after(0, lambda: self._display_image(img_path))
                    self.root.after(0, lambda: self.status_label.config(text=f"{role}头像已生成"))
                else:
                    self.root.after(0, lambda: self.status_label.config(text=f"{role}头像生成失败"))
            except Exception as e:
                self.root.after(0, lambda: self.status_label.config(text=f"生成失败: {e}"))
            finally:
                self.root.after(0, lambda: self.show_progress(False))

        threading.Thread(target=task, daemon=True).start()

    def _display_avatar_in_label(self, img_path, label_widget):
        try:
            img = Image.open(img_path)
            img.thumbnail((120, 120), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            label_widget.config(image=photo, text="")
            label_widget.image = photo
        except Exception:
            label_widget.config(text="X", image="")

    def _display_image(self, img_path):
        if not img_path or not os.path.exists(img_path):
            return
        try:
            width = self.img_display.winfo_width() - 20
            height = self.img_display.winfo_height() - 20
            if width < 10 or height < 10:
                width, height = 300, 250
            img = Image.open(img_path)
            img.thumbnail((width, height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.img_display.config(image=photo, text="")
            self.img_display.image = photo
        except Exception as e:
            self.img_display.config(text=f"显示失败: {e}")

    def _create_flat_button(self, parent, text, command, width=10,
                            bg_color="#89b4fa", fg_color="#1e1e2e", state=tk.NORMAL):
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            font=('Helvetica', 10),
            bg=bg_color,
            fg=fg_color,
            padx=8,
            pady=4,
            relief=tk.FLAT,
            bd=0,
            width=width,
            state=state,
            cursor="hand2"
        )
        def on_enter(e):
            if btn['state'] != tk.DISABLED:
                btn['bg'] = self._adjust_brightness(bg_color, 1.2)
        def on_leave(e):
            if btn['state'] != tk.DISABLED:
                btn['bg'] = bg_color
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        return btn

    def _adjust_brightness(self, hex_color, factor):
        if not hex_color.startswith('#'):
            return hex_color
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        r = min(255, int(r * factor))
        g = min(255, int(g * factor))
        b = min(255, int(b * factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    def apply_theme(self):
        theme = self.themes[self.current_theme]
        self.root.configure(bg=theme["bg"])
        self.title_frame.configure(bg=theme["bg"])
        for child in self.title_frame.winfo_children():
            if isinstance(child, tk.Label):
                child.configure(bg=theme["bg"], fg=theme["fg"])
            elif isinstance(child, tk.Frame):
                child.configure(bg=theme["bg"])
                for sub in child.winfo_children():
                    if isinstance(sub, tk.Label):
                        sub.configure(bg=theme["bg"], fg=theme["fg"])
        self.control_frame.configure(bg=theme["frame_bg"])
        for frame in self.control_frame.winfo_children():
            if isinstance(frame, tk.Frame):
                frame.configure(bg=theme["frame_bg"])
            for child in frame.winfo_children():
                if str(child.winfo_class()) in ["TCombobox", "TProgressbar"]:
                    continue
                try:
                    if isinstance(child, tk.Label):
                        child.configure(bg=theme["frame_bg"], fg=theme["fg"])
                    elif isinstance(child, tk.Entry):
                        child.configure(bg=theme["entry_bg"], fg=theme["fg"])
                    elif isinstance(child, tk.Scale):
                        child.configure(bg=theme["frame_bg"], fg=theme["fg"])
                    elif isinstance(child, tk.Frame):
                        child.configure(bg=theme["frame_bg"])
                    elif isinstance(child, tk.Button):
                        pass
                    elif isinstance(child, tk.Spinbox):
                        child.configure(bg=theme["entry_bg"], fg=theme["fg"])
                    else:
                        child.configure(bg=theme["frame_bg"])
                except Exception:
                    pass
        self.main_paned.configure(bg=theme["bg"])
        if self.left_frame:
            self.left_frame.configure(bg=theme["zheng_bg"])
            for child in self.left_frame.winfo_children():
                if isinstance(child, tk.Frame):
                    child.configure(bg=theme["zheng_bg"])
                    for sub in child.winfo_children():
                        if str(sub.winfo_class()) in ["TCombobox", "TProgressbar"]:
                            continue
                        try:
                            if isinstance(sub, tk.Label):
                                sub.configure(bg=theme["zheng_bg"], fg=theme["fg"])
                            elif isinstance(sub, tk.Frame):
                                sub.configure(bg=theme["zheng_bg"])
                            elif isinstance(sub, tk.Entry):
                                sub.configure(bg=theme["entry_bg"], fg=theme["fg"])
                            elif isinstance(sub, tk.Button):
                                pass
                            elif isinstance(sub, tk.Spinbox):
                                sub.configure(bg=theme["entry_bg"], fg=theme["fg"])
                            else:
                                sub.configure(bg=theme["zheng_bg"])
                        except Exception:
                            pass
                elif isinstance(child, scrolledtext.ScrolledText):
                    child.configure(bg=theme["entry_bg"], fg=theme["fg"])
        if self.mid_frame:
            self.mid_frame.configure(bg=theme["fan_bg"])
            for child in self.mid_frame.winfo_children():
                if isinstance(child, tk.Frame):
                    child.configure(bg=theme["fan_bg"])
                    for sub in child.winfo_children():
                        if str(sub.winfo_class()) in ["TCombobox", "TProgressbar"]:
                            continue
                        try:
                            if isinstance(sub, tk.Label):
                                sub.configure(bg=theme["fan_bg"], fg=theme["fg"])
                            elif isinstance(sub, tk.Frame):
                                sub.configure(bg=theme["fan_bg"])
                            elif isinstance(sub, tk.Entry):
                                sub.configure(bg=theme["entry_bg"], fg=theme["fg"])
                            elif isinstance(sub, tk.Button):
                                pass
                            elif isinstance(sub, tk.Spinbox):
                                sub.configure(bg=theme["entry_bg"], fg=theme["fg"])
                            else:
                                sub.configure(bg=theme["fan_bg"])
                        except Exception:
                            pass
                elif isinstance(child, scrolledtext.ScrolledText):
                    child.configure(bg=theme["entry_bg"], fg=theme["fg"])
        if self.right_frame:
            self.right_frame.configure(bg=theme["img_bg"])
            for child in self.right_frame.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=theme["img_bg"], fg=theme["fg"])
                elif isinstance(child, tk.Frame):
                    child.configure(bg=theme["img_bg"])
        if self.input_frame:
            self.input_frame.configure(bg=theme["frame_bg"])
            for child in self.input_frame.winfo_children():
                if str(child.winfo_class()) in ["TCombobox", "TProgressbar"]:
                    continue
                try:
                    if isinstance(child, tk.Label):
                        child.configure(bg=theme["frame_bg"], fg=theme["fg"])
                    elif isinstance(child, tk.Entry):
                        child.configure(bg=theme["entry_bg"], fg=theme["fg"])
                    elif isinstance(child, tk.Frame):
                        child.configure(bg=theme["frame_bg"])
                    elif isinstance(child, tk.Button):
                        pass
                    else:
                        child.configure(bg=theme["frame_bg"])
                except Exception:
                    pass
        self.img_display.configure(bg=theme["frame_bg"], fg=theme["border"])
        self.status_frame.configure(bg=theme["frame_bg"])
        self.status_label.configure(bg=theme["frame_bg"], fg=theme["fg"])
        self.turn_counter.configure(bg=theme["frame_bg"], fg=theme["border"])

    def switch_theme(self, theme_name):
        self.current_theme = theme_name
        self.apply_theme()
        self.status_label.config(text=f"主题已切换: {theme_name}")

    def switch_font(self):
        font_name = self.font_var.get()
        font_tuple = self.fonts.get(font_name, ("微软雅黑", 11))
        self.zheng_chat.configure(font=font_tuple)
        self.fan_chat.configure(font=font_tuple)
        self.input_entry.configure(font=font_tuple)
        self.status_label.config(text=f"字体已切换: {font_name}")

    def show_progress(self, show=True):
        if show:
            self.progress_bar.pack(side=tk.LEFT, padx=10)
            self.progress_bar.start(10)
        else:
            self.progress_bar.stop()
            self.progress_bar.pack_forget()

    def insert_colored_text(self, role, text):
        if role == "正方":
            self.zheng_chat.insert(tk.END, text, "发言")
            self.zheng_chat.see(tk.END)
        elif role == "反方":
            self.fan_chat.insert(tk.END, text, "发言")
            self.fan_chat.see(tk.END)
        else:
            self.zheng_chat.insert(tk.END, text, "系统")
            self.fan_chat.insert(tk.END, text, "系统")
            self.zheng_chat.see(tk.END)
            self.fan_chat.see(tk.END)

    def start_debate(self):
        topic = self.topic_entry.get().strip()
        if not topic:
            self.zheng_chat.insert(tk.END, "请输入辩题！\n", "系统")
            return
        if self.paused:
            self._resume_debate()
            return
        if self.is_running:
            return
        if self.current_topic and self.current_topic != topic and self.debate_history:
            self._reset_state()
        self.turn_count = 0
        self.waiting_for_user = False
        self.ai_first_speech_done = False
        self.is_ai_speaking = False
        self.user_role = self.side_var.get()
        if self.mode_var.get() == "人 vs AI":
            self._start_human_vs_ai(topic)
        else:
            self._start_new_debate(topic)

    def _start_human_vs_ai(self, topic):
        """人 vs AI 模式 - 正方先立论"""
        self.is_running = True
        self.paused = False
        self.pause_event.set()
        self.quick_activated = False
        self.debate_history = []
        self.pause_phase_index = 0
        self.current_topic = topic
        self.current_full_reply = ""
        self.turn_count = 0
        self.waiting_for_user = False
        self.ai_first_speech_done = False
        self.is_ai_speaking = False

        self.zheng_chat.delete(1.0, tk.END)
        self.fan_chat.delete(1.0, tk.END)
        
        self.user_role = self.side_var.get()
        
        self.zheng_chat.insert(tk.END, f"辩题：{topic}\n", "标题")
        self.zheng_chat.insert(tk.END, "=" * 40 + "\n\n", "系统")
        self.fan_chat.insert(tk.END, f"辩题：{topic}\n", "标题")
        self.fan_chat.insert(tk.END, "=" * 40 + "\n\n", "系统")
        
        info_text = f"【人 vs AI 模式】共{self.max_turns.get()}轮\n你代表「{self.user_role}」\n"
        self.zheng_chat.insert(tk.END, info_text, "系统")
        self.fan_chat.insert(tk.END, info_text, "系统")
        
        self.start_btn.config(state=tk.DISABLED, text="辩论中...")
        self.pause_btn.config(state=tk.NORMAL, text="暂停")
        self.quick_btn.config(state=tk.DISABLED)
        self.restart_btn.config(state=tk.NORMAL, text="重新开始")
        
        # 正方先发言
        if self.user_role == "正方":
            # 用户是正方 → 用户先发言
            self.zheng_chat.insert(tk.END, "【提示】你是正方，请先发言！\n", "系统")
            self.fan_chat.insert(tk.END, "【提示】正方正在准备发言...\n", "系统")
            self.waiting_for_user = True
            self.ai_first_speech_done = True
            self.status_label.config(text=f"人 vs AI 模式 | 辩题: {topic} | 轮到你了（正方）")
        else:
            # 用户是反方 → AI正方先发言
            self.zheng_chat.insert(tk.END, "AI 正方正在立论...\n", "系统")
            self.fan_chat.insert(tk.END, "AI 正方正在立论...\n", "系统")
            self.waiting_for_user = False
            self.ai_first_speech_done = False
            self.status_label.config(text=f"人 vs AI 模式 | 辩题: {topic} | AI 正方立论中...")
            self._trigger_ai_first_speech("正方")

    def _reset_state(self):
        self.is_running = False
        self.paused = False
        self.pause_event.set()
        self.quick_activated = False
        self.debate_history = []
        self.pause_phase_index = 0
        self.current_full_reply = ""
        self.turn_count = 0
        self.waiting_for_user = False
        self.ai_first_speech_done = False
        self.is_ai_speaking = False
        self.start_btn.config(state=tk.NORMAL, text="开始辩论")
        self.pause_btn.config(state=tk.DISABLED, text="暂停")
        self.quick_btn.config(state=tk.DISABLED)
        self.restart_btn.config(state=tk.DISABLED)
        self.show_progress(False)

    def _start_new_debate(self, topic):
        self.is_running = True
        self.paused = False
        self.pause_event.set()
        self.quick_activated = False
        self.debate_history = []
        self.pause_phase_index = 0
        self.current_topic = topic
        self.current_temp = self.temp_zheng.get()
        self.current_full_reply = ""
        self.turn_count = 0
        self.waiting_for_user = False
        self.ai_first_speech_done = False

        self.zheng_chat.delete(1.0, tk.END)
        self.fan_chat.delete(1.0, tk.END)
        self.zheng_chat.insert(tk.END, f"辩题：{topic}\n", "标题")
        self.zheng_chat.insert(tk.END, "=" * 40 + "\n\n", "系统")
        self.fan_chat.insert(tk.END, f"辩题：{topic}\n", "标题")
        self.fan_chat.insert(tk.END, "=" * 40 + "\n\n", "系统")

        self.start_btn.config(state=tk.DISABLED, text="辩论中...")
        self.pause_btn.config(state=tk.NORMAL, text="暂停")
        self.quick_btn.config(state=tk.NORMAL, text="一键加速")
        self.restart_btn.config(state=tk.NORMAL, text="重新开始")
        self.show_progress(True)
        self.status_label.config(text=f"AI vs AI 辩论进行中... {topic}")
        self.turn_counter.config(text=f"辩论进度: 0/{self.max_turns.get()}轮")

        self._run_debate_task(topic, 0)

    def _resume_debate(self):
        if not self.paused:
            return
        self.paused = False
        self.pause_event.set()
        self.is_running = True
        self.pause_btn.config(state=tk.NORMAL, text="暂停")
        self.start_btn.config(state=tk.DISABLED, text="辩论中...")
        self.quick_btn.config(state=tk.NORMAL, text="一键加速")
        self.show_progress(True)
        self.status_label.config(text=f"继续辩论... {self.current_topic}")

    def _run_debate_task(self, topic, start_index):
        # 在主线程快照所有 Tk 变量，后台线程禁止访问 Tk 对象
        max_turns = self.max_turns.get()
        temp_zheng, model_zheng = resolve_role_params("正方", self.temp_zheng.get(), self.model_zheng.get())
        temp_fan, model_fan = resolve_role_params("反方", self.temp_fan.get(), self.model_fan.get())
        debate_sequence = build_debate_sequence(max_turns)

        def task():
            try:
                debate_round_count = 0

                for i in range(start_index, len(debate_sequence)):
                    if self.paused:
                        self.pause_event.clear()
                        self.pause_event.wait()
                    if not self.is_running:
                        return
                    
                    role, phase = debate_sequence[i]
                    
                    if self.quick_activated:
                        self._execute_quick_remaining_from_index(topic, i, debate_sequence)
                        return
                    
                    if is_debate_round(phase) and debate_round_count >= max_turns:
                        continue
                    
                    title = f"\n{'─'*30}\n【{role} · {phase}】\n"
                    self.root.after(0, lambda r=role, t=title: self._insert_title(r, t))
                    
                    if role == "正方":
                        temp, model = temp_zheng, model_zheng
                    else:
                        temp, model = temp_fan, model_fan
                    
                    full_reply = ""
                    for chunk in stream_speech(self.debate_history, role, phase, topic, temp, model):
                        if self.paused:
                            self.pause_event.clear()
                            self.pause_event.wait()
                            if not self.is_running:
                                return
                        if not self.is_running or self.quick_activated:
                            break
                        full_reply += chunk
                        self.current_full_reply = full_reply
                        self.root.after(0, lambda c=chunk, r=role: self.insert_colored_text(r, c))
                    
                    if full_reply:
                        self.debate_history.append({"role": role, "phase": phase, "content": full_reply})
                        if is_debate_round(phase):
                            debate_round_count += 1
                        self.current_full_reply = ""
                        self.root.after(0, lambda: self.turn_counter.config(
                            text=f"辩论进度: {debate_round_count}/{max_turns}轮"
                        ))
                    
                    if self.paused:
                        # 记录进度供 UI 展示；下一轮循环顶部会阻塞等待继续
                        self.pause_phase_index = i + 1

                if self.is_running and not self.paused and not self.quick_activated:
                    self.root.after(0, lambda: self.insert_colored_text("系统", f"\n辩论完成，裁判评判中...\n"))
                    self.root.after(0, self._trigger_judge)

            except Exception as e:
                self.root.after(0, lambda: self.insert_colored_text("系统", f"\n错误: {e}\n"))
            finally:
                if not self.paused:
                    self.root.after(0, self.debate_finished)

        self.debate_thread = threading.Thread(target=task, daemon=True)
        self.debate_thread.start()

    def _execute_quick_remaining_from_index(self, topic, start_index, debate_sequence):
        # 在主线程快照所有 Tk 变量，后台线程禁止访问 Tk 对象
        max_turns = self.max_turns.get()
        temp_zheng, model_zheng = resolve_role_params("正方", self.temp_zheng.get(), self.model_zheng.get())
        temp_fan, model_fan = resolve_role_params("反方", self.temp_fan.get(), self.model_fan.get())

        def task():
            try:
                if start_index >= len(debate_sequence):
                    self.root.after(0, self.debate_finished)
                    return
                for i in range(start_index, len(debate_sequence)):
                    if not self.is_running:
                        break
                    role, phase = debate_sequence[i]
                    self.root.after(0, lambda r=role: self.status_label.config(text=f"加速生成 {r}..."))
                    title = f"\n{'─'*30}\n【{role} · {phase}】\n"
                    self.root.after(0, lambda r=role, t=title: self._insert_title(r, t))
                    if role == "正方":
                        temp, model = temp_zheng, model_zheng
                    else:
                        temp, model = temp_fan, model_fan
                    full_reply = ""
                    for chunk in stream_speech(self.debate_history, role, phase, topic, temp, model):
                        if not self.is_running:
                            break
                        full_reply += chunk
                    if full_reply:
                        self.debate_history.append({"role": role, "phase": phase, "content": full_reply})
                        self.turn_count += 1
                        self.root.after(0, lambda r=role, c=full_reply: self.insert_colored_text(r, c))
                        self.root.after(0, lambda: self.turn_counter.config(text=f"轮次: {self.turn_count}/{max_turns}"))
                has_judge = any(h.get("role") == "裁判" for h in self.debate_history)
                if self.is_running and not has_judge:
                    self.root.after(0, self._trigger_judge)
            except Exception as e:
                self.root.after(0, lambda: self.insert_colored_text("系统", f"\n错误: {e}\n"))
            finally:
                self.root.after(0, self.debate_finished)

        threading.Thread(target=task, daemon=True).start()

    def _insert_title(self, role, title):
        if role == "正方":
            self.zheng_chat.insert(tk.END, title, "标题")
            self.zheng_chat.see(tk.END)
        elif role == "反方":
            self.fan_chat.insert(tk.END, title, "标题")
            self.fan_chat.see(tk.END)
        else:
            self.zheng_chat.insert(tk.END, title, "标题")
            self.fan_chat.insert(tk.END, title, "标题")

    def toggle_pause(self):
        if not self.is_running and not self.paused:
            return
        if not self.paused:
            self.paused = True
            self.pause_event.clear()
            self.pause_btn.config(state=tk.NORMAL, text="继续")
            self.start_btn.config(state=tk.DISABLED, text="已暂停")
            self.quick_btn.config(state=tk.DISABLED)
            self.show_progress(False)
            self.status_label.config(text="已暂停")
            if self.is_ai_speaking:
                self.insert_colored_text("系统", "\n【AI发言已暂停】\n")
            else:
                self.insert_colored_text("系统", "\n【辩论已暂停】\n")
        else:
            self._resume_debate()
            self.insert_colored_text("系统", "\n【辩论继续】\n")

    def restart_debate(self):
        self.is_running = False
        self.paused = False
        self.pause_event.set()
        self.quick_activated = False
        self.debate_history = []
        self.pause_phase_index = 0
        self.current_full_reply = ""
        self.turn_count = 0
        self.waiting_for_user = False
        self.ai_first_speech_done = False
        self.is_ai_speaking = False
        self.zheng_chat.delete(1.0, tk.END)
        self.fan_chat.delete(1.0, tk.END)
        self.zheng_chat.insert(tk.END, "已重置，点击「开始辩论」\n", "系统")
        self.fan_chat.insert(tk.END, "已重置，点击「开始辩论」\n", "系统")
        self.img_display.config(image="", text="点击「词云」或「文生图」\n生成图片将显示在此处")
        self.start_btn.config(state=tk.NORMAL, text="开始辩论")
        self.pause_btn.config(state=tk.DISABLED, text="暂停")
        self.quick_btn.config(state=tk.DISABLED)
        self.restart_btn.config(state=tk.DISABLED)
        self.show_progress(False)
        self.status_label.config(text="已重置")
        self.turn_counter.config(text="轮次: 0")

    def quick_debate(self):
        if self.is_running or self.paused:
            if not self.quick_activated:
                # 只置标志并唤醒辩论线程：由存活的辩论线程在下一个检查点
                # 自行保存半截发言并从当前进度转交加速流程（避免双写）
                self.quick_activated = True
                self.paused = False
                self.pause_event.set()
                self.is_running = True
                self.quick_btn.config(state=tk.DISABLED, text="加速中...")
                self.pause_btn.config(state=tk.DISABLED)
                self.start_btn.config(state=tk.DISABLED)
                self.show_progress(True)
                self.status_label.config(text="正在加速生成...")

    def debate_finished(self):
        self.is_running = False
        self.paused = False
        self.pause_event.set()
        self.quick_activated = False
        self.is_quick_mode = False
        self.current_full_reply = ""
        self.waiting_for_user = False
        self.ai_first_speech_done = False
        self.is_ai_speaking = False
        self.start_btn.config(state=tk.NORMAL, text="开始辩论")
        self.pause_btn.config(state=tk.DISABLED, text="暂停")
        self.quick_btn.config(state=tk.DISABLED, text="一键加速")
        self.restart_btn.config(state=tk.NORMAL, text="重新开始")
        self.show_progress(False)
        self.status_label.config(text=f"辩论结束 | 共 {len(self.debate_history)} 轮发言")

    def generate_wordcloud_from_debate(self):
        if not self.debate_history:
            self.status_label.config(text="没有辩论内容")
            return
        text = " ".join([entry.get("content", "") for entry in self.debate_history])
        if not text.strip():
            self.status_label.config(text="辩论内容为空")
            return
        self.show_progress(True)
        self.status_label.config(text="正在生成词云...")
        def task():
            try:
                os.makedirs("output", exist_ok=True)
                output_path = os.path.join("output", f"debate_wordcloud_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                img_path = generate_wordcloud_from_text(text, output_path)
                if img_path:
                    self.root.after(0, lambda: self._display_image(img_path))
                    self.root.after(0, lambda: self.status_label.config(text="词云已生成"))
            except Exception as e:
                self.root.after(0, lambda: self.status_label.config(text=f"词云失败: {e}"))
            finally:
                self.root.after(0, lambda: self.show_progress(False))
        threading.Thread(target=task, daemon=True).start()

    def generate_image_from_prompt(self):
        prompt = self.topic_entry.get().strip()
        if not prompt:
            self.status_label.config(text="请输入提示词")
            return
        self.show_progress(True)
        self.status_label.config(text="正在生成图片...")
        def task():
            try:
                img_path = text_to_image(prompt)
                if img_path:
                    self.root.after(0, lambda: self._display_image(img_path))
                    self.root.after(0, lambda: self.status_label.config(text="图片已生成"))
            except Exception as e:
                self.root.after(0, lambda: self.status_label.config(text=f"生图失败: {e}"))
            finally:
                self.root.after(0, lambda: self.show_progress(False))
        threading.Thread(target=task, daemon=True).start()

    def save_history(self):
        if not self.debate_history:
            self.status_label.config(text="没有可保存的记录")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"history/debate_{timestamp}.json"
        os.makedirs("history", exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({
                "topic": self.topic_entry.get(),
                "mode": self.mode_var.get(),
                "max_turns": self.max_turns.get(),
                "temp_zheng": self.temp_zheng.get(),
                "temp_fan": self.temp_fan.get(),
                "model_zheng": self.model_zheng.get(),
                "model_fan": self.model_fan.get(),
                "model_judge": self.model_judge.get(),
                "history": self.debate_history,
                "timestamp": timestamp
            }, f, ensure_ascii=False, indent=2)
        self.status_label.config(text=f"已保存: {os.path.basename(filename)}")

    def load_history(self):
        filepath = filedialog.askopenfilename(
            title="选择辩论存档",
            filetypes=[("JSON文件", "*.json")],
            initialdir="history" if os.path.exists("history") else "."
        )
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.zheng_chat.delete(1.0, tk.END)
            self.fan_chat.delete(1.0, tk.END)
            for entry in data.get("history", []):
                role = entry.get("role", "")
                phase = entry.get("phase", "")
                content = entry.get("content", "")
                if role == "正方":
                    self.zheng_chat.insert(tk.END, f"\n【{role} · {phase}】\n", "标题")
                    self.zheng_chat.insert(tk.END, content + "\n", "发言" if phase != "用户发言" else "用户")
                elif role == "反方":
                    self.fan_chat.insert(tk.END, f"\n【{role} · {phase}】\n", "标题")
                    self.fan_chat.insert(tk.END, content + "\n", "发言" if phase != "用户发言" else "用户")
                else:
                    self.zheng_chat.insert(tk.END, f"\n【裁判评判】\n", "标题")
                    self.zheng_chat.insert(tk.END, content + "\n", "系统")
                    self.fan_chat.insert(tk.END, f"\n【裁判评判】\n", "标题")
                    self.fan_chat.insert(tk.END, content + "\n", "系统")
            self.debate_history = data.get("history", [])
            self.turn_counter.config(text=f"辩论进度: {len([h for h in self.debate_history if h.get('role') != '裁判'])}条")
            self.status_label.config(text=f"已载入存档: {os.path.basename(filepath)}")
            if "mode" in data:
                self.mode_var.set(data["mode"])
            if "max_turns" in data:
                self.max_turns.set(data["max_turns"])
            if "model_zheng" in data:
                self.model_zheng.set(data["model_zheng"])
            if "model_fan" in data:
                self.model_fan.set(data["model_fan"])
            if "model_judge" in data:
                self.model_judge.set(data["model_judge"])
        except Exception as e:
            self.insert_colored_text("系统", f"载入失败: {e}\n")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    root = tk.Tk()
    app = DebateApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()