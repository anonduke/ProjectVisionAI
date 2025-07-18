import os
import json
import threading
from datetime import datetime
from pathlib import Path

from pynput import keyboard
from transformers import pipeline
from win10toast import ToastNotifier
import pystray
from PIL import Image, ImageDraw
import torch
import tkinter as tk
from tkinter import ttk

# ---------------------- Configuration ----------------------
CONFIG_FILE = Path.home() / '.keyboard_vision_settings.json'
SUMMARY_FILE = Path.home() / '.keyboard_vision_alerts.log'

# Default settings if CONFIG_FILE does not exist
DEFAULT_SETTINGS = {
    'threshold': 0.90,    # Confidence threshold for alerts (0.0 - 1.0)
    'buffer_size': 100    # Max characters before running classification
}

# ---------------------- Settings Management ----------------------
def load_settings():
    """Load settings from disk, or create defaults if missing/corrupt."""
    if not CONFIG_FILE.exists():
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    try:
        data = json.loads(CONFIG_FILE.read_text())
        # Ensure all keys present
        for key, default in DEFAULT_SETTINGS.items():
            data.setdefault(key, default)
        return data
    except (json.JSONDecodeError, IOError):
        return DEFAULT_SETTINGS.copy()

def save_settings(settings: dict):
    """Persist settings to disk as JSON."""
    try:
        CONFIG_FILE.write_text(json.dumps(settings, indent=4))
    except IOError as e:
        print(f"Error saving settings: {e}")

# Load or initialize settings
settings = load_settings()
threshold = settings['threshold']
buffer_size = settings['buffer_size']

# ---------------------- Model Initialization ----------------------
# Use GPU if available, otherwise CPU
device = 0 if torch.cuda.is_available() else -1
classifier = pipeline(
    'text-classification',
    model='distilbert-base-uncased-finetuned-sst-2-english',
    device=device
)

# ---------------------- Notification ----------------------
toaster = ToastNotifier()

def send_notification(text: str, score: float):
    """Show a desktop toast and log the alert to SUMMARY_FILE with custom icon."""
    icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "images", "keyboard_vision_icon.ico"))

    toaster.show_toast(
        "Keyboard Vision Alert",
        f"Risk detected: '{text[:50]}...' (score={score:.2f})",
        duration=5,
        icon_path=icon_path  # ✅ custom icon here
    )

    timestamp = datetime.now().isoformat()
    with open(SUMMARY_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{timestamp}\t{score:.2f}\t{text}\n")


def classify_and_alert(text: str):
    """Run the text through the model and trigger notification if above threshold."""
    result = classifier(text)[0]
    label = result['label'].lower()
    score = result['score']
    # Adjust labels based on your fine-tuning
    if label in ['negative', 'self-harm', 'toxic'] and score >= threshold:
        send_notification(text, score)

def schedule_classification(text: str):
    """Run classification in background to avoid blocking keystroke listener."""
    threading.Thread(
        target=classify_and_alert,
        args=(text,),
        daemon=True
    ).start()

# ---------------------- Keystroke Listener ----------------------
buffer = ''

def on_press(key):
    """Callback for each key press: accumulate chars and flush on whitespace or limit."""
    global buffer
    try:
        char = key.char or ''
    except AttributeError:
        # Non-character key treated as a space (flush point)
        char = ' '
    buffer += char
    if char.isspace() or len(buffer) >= buffer_size:
        snippet = buffer.strip()
        buffer = ''
        if snippet:
            schedule_classification(snippet)

# ---------------------- System Tray & Settings UI ----------------------
def create_tray_icon_image():
    """Generate a simple 64×64 icon for the tray."""
    img = Image.new('RGB', (64, 64), 'white')
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 63, 63), outline='black')
    draw.text((18, 18), 'K', fill='red')
    return img

def open_settings_window(icon, item):
    """Display a Tkinter window to adjust threshold and buffer_size."""
    window = tk.Tk()
    window.title('Keyboard Vision Settings')
    window.geometry('300x180')
    ttk.Label(window, text='Confidence Threshold (0.0–1.0)').pack(pady=(10, 0))
    thr_var = tk.DoubleVar(value=threshold)
    ttk.Scale(window, from_=0.0, to=1.0, variable=thr_var, orient='horizontal').pack(padx=20)
    ttk.Label(window, text='Buffer Size (chars)').pack(pady=(10, 0))
    buf_var = tk.IntVar(value=buffer_size)
    ttk.Entry(window, textvariable=buf_var).pack(pady=(0, 10))
    def save_and_close():
        global threshold, buffer_size, settings
        threshold = float(thr_var.get())
        buffer_size = int(buf_var.get())
        settings['threshold'] = threshold
        settings['buffer_size'] = buffer_size
        save_settings(settings)
        window.destroy()
    ttk.Button(window, text='Save', command=save_and_close).pack(side='left', padx=(40, 5))
    ttk.Button(window, text='Cancel', command=window.destroy).pack(side='right', padx=(5, 40))
    window.mainloop()

def quit_app(icon, item):
    """Stop the tray icon and keyboard listener, then exit."""
    icon.stop()
    listener.stop()

# Build the tray menu
menu = pystray.Menu(
    pystray.MenuItem('Settings', open_settings_window),
    pystray.MenuItem('Quit', quit_app)
)

tray_icon = pystray.Icon(
    'KeyboardVisionAI',
    create_tray_icon_image(),
    'Keyboard Vision AI',
    menu
)

# ---------------------- Main Execution ----------------------
if __name__ == '__main__':
    # Start listening to keystrokes
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    # Launch system tray icon (blocks until Quit)
    tray_icon.run()