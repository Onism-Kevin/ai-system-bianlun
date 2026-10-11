# debate_utils.py
import os
import json
import time
import logging
import requests
import jieba
from wordcloud import WordCloud
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import filedialog

logger = logging.getLogger(__name__)

# --- ComfyUI 配置 ---
COMFYUI_URL = "http://127.0.0.1:8188"
WORKFLOW_FILE = "workflow_api.json"
COMFYUI_OUTPUT = os.path.expanduser("~/ComfyUI-Shared/output")


# --- 1. 文生图功能 (调用 ComfyUI) ---

def text_to_image(prompt_text, progress_callback=None):
    """
    调用 ComfyUI API，根据提示词生成图片。
    """
    # 1. 检查工作流文件
    if not os.path.exists(WORKFLOW_FILE):
        raise FileNotFoundError(f"工作流文件 {WORKFLOW_FILE} 不存在")

    # 2. 加载工作流
    with open(WORKFLOW_FILE, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    # 3. 修改正面提示词 (节点ID为5)
    if "5" not in workflow:
        raise KeyError("工作流中找不到 ID 为 5 的节点")
    
    workflow["5"]["inputs"]["user_prompt"] = prompt_text

    # 4. 提交任务
    submit_url = f"{COMFYUI_URL}/prompt"
    
    try:
        resp = requests.post(submit_url, json={"prompt": workflow}, timeout=30)
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        logger.exception("提交 ComfyUI 任务失败: url=%s", submit_url)
        raise RuntimeError(f"ComfyUI 任务失败: 提交任务请求异常 ({e})") from e

    prompt_id = result.get("prompt_id")
    if not prompt_id:
        logger.error("ComfyUI 响应中没有 prompt_id: %s", result)
        raise RuntimeError(f"ComfyUI 任务失败: 响应中没有 prompt_id: {result}")

    # 5. 等待 ComfyUI 任务完成
    history_url = f"{COMFYUI_URL}/history"
    elapsed = 0
    timeout = 300
    poll_interval = 2

    history = {}
    task_completed = False
    while elapsed < timeout:
        time.sleep(poll_interval)
        elapsed += poll_interval

        if progress_callback:
            progress_callback(elapsed, "生成中...")

        try:
            resp = requests.get(history_url, timeout=10)
            resp.raise_for_status()
            history = resp.json()

            if prompt_id in history:
                task_completed = True
                break
        except Exception as e:
            logger.warning("轮询 /history 失败（已耗时 %s 秒）: %s", elapsed, e)
            continue

    if not task_completed:
        logger.error("ComfyUI 任务 %s 未在 %s 秒内完成", prompt_id, timeout)
        raise TimeoutError(f"任务未在 {timeout} 秒内完成")

    # 6. 等待1秒让文件写入完成
    time.sleep(1)

    # 7. 精确取图：从 history[prompt_id]["outputs"] 各节点的 images 数组解析文件名
    record = history.get(prompt_id, {})
    outputs = record.get("outputs", {}) if isinstance(record, dict) else {}
    image_entries = []
    if isinstance(outputs, dict):
        for node_id, node_output in outputs.items():
            if not isinstance(node_output, dict):
                continue
            for img in (node_output.get("images") or []):
                if isinstance(img, dict) and img.get("filename"):
                    image_entries.append((node_id, img))

    if image_entries:
        for node_id, img in image_entries:
            filename = img["filename"]
            subfolder = img.get("subfolder") or ""
            img_type = img.get("type") or "output"
            # 按 type 映射根目录：output -> COMFYUI_OUTPUT，其余与 output 同级
            if img_type == "output":
                base_dir = COMFYUI_OUTPUT
            else:
                base_dir = os.path.join(os.path.dirname(COMFYUI_OUTPUT), img_type)
            file_path = os.path.abspath(os.path.join(base_dir, subfolder, filename))
            if os.path.exists(file_path):
                logger.info("ComfyUI 任务 %s 生成图片: %s (节点 %s)", prompt_id, file_path, node_id)
                return file_path
            logger.warning(
                "history 中记录了图片但文件不存在: %s (节点 %s, type=%s)", file_path, node_id, img_type
            )
        # history 有图片信息但文件都找不到：仍然回退到 mtime 扫描兜底
        logger.warning("ComfyUI 任务 %s 的 outputs 图片文件均未落盘，回退到 mtime 扫描", prompt_id)
    else:
        logger.warning("ComfyUI 任务 %s 的 outputs 中无图片信息，回退到 mtime 扫描", prompt_id)

    # 8. 回退：扫描输出目录取 mtime 最新图片（仅在 outputs 无图片信息时使用）
    try:
        if os.path.exists(COMFYUI_OUTPUT):
            all_images = []
            for root, dirs, files in os.walk(COMFYUI_OUTPUT):
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        file_path = os.path.join(root, file)
                        file_mtime = os.path.getmtime(file_path)
                        all_images.append((file_path, file_mtime))

            if all_images:
                all_images.sort(key=lambda x: x[1], reverse=True)
                logger.info("mtime 扫描返回最新图片: %s", all_images[0][0])
                return all_images[0][0]
    except Exception as e:
        logger.warning("回退 mtime 扫描输出目录失败 (%s): %s", COMFYUI_OUTPUT, e)

    logger.error("ComfyUI 任务 %s 完成但未找到生成的图片", prompt_id)
    raise RuntimeError("ComfyUI 任务失败: 任务完成但未找到生成的图片")


# --- 2. 词云生成功能 ---

def generate_wordcloud_from_text(text, output_path="debate_wordcloud.png"):
    """
    从文本生成词云图片。
    """
    if not text or not text.strip():
        return None

    words = jieba.cut(text)
    text_cut = " ".join(words)

    font_paths = [
        # Windows 中文字体（优先）
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        # macOS 字体（回退）
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "PingFang.ttc"
    ]
    font_path = None
    for fp in font_paths:
        if os.path.exists(fp):
            font_path = fp
            break

    if font_path is None:
        logger.warning(
            "未找到任何可用的中文字体（已尝试: %s），词云中文可能无法正常渲染", font_paths
        )

    try:
        wc = WordCloud(
            font_path=font_path,
            width=800,
            height=600,
            background_color="white",
            max_words=80,
            random_state=42
        )
        wc.generate(text_cut)
        wc.to_file(output_path)
        logger.info("词云已生成: %s", output_path)
        return output_path
    except Exception:
        logger.exception("生成词云失败 (output_path=%s, font_path=%s)", output_path, font_path)
        return None


# --- 3. 头像加载功能 ---

def load_avatar_from_file(parent_window, title="选择头像"):
    filepath = filedialog.askopenfilename(
        title=title,
        filetypes=[("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp")],
        parent=parent_window
    )
    return filepath if filepath else None


def display_image_in_label(img_path, label_widget, max_size=(100, 100)):
    if not img_path or not os.path.exists(img_path):
        label_widget.config(image="", text="无图片")
        label_widget.image = None
        return

    try:
        img = Image.open(img_path)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        label_widget.config(image=photo, text="")
        label_widget.image = photo
    except Exception:
        logger.exception("头像图片加载失败: %s", img_path)
        label_widget.config(image="", text="加载失败")
        label_widget.image = None