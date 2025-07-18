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
from pynput import keyboard as kb
from cryptography.fernet import Fernet
import base64
import hashlib
from dashboard_window import show_dashboard

# ---------------------- Configuration ----------------------
CONFIG_FILE = Path.home() / '.keyboard_vision_settings.json'
SUMMARY_FILE = Path.home() / '.keyboard_vision_alerts.log'

# Default settings if CONFIG_FILE does not exist
DEFAULT_SETTINGS = {
    'threshold': 0.99,    # Confidence threshold for alerts (0.0 - 1.0)
    'buffer_size': 100    # Max characters before running classification
}

# ---------------------- Risky & Excluded Keywords ----------------------
RISKY_KEYWORDS = {
    "joder","mierda", "puta", "pendejo", "culo",
}
EXCLUDED_WORDS = {
    "you", "will", "lol", "game", "play", "killstreak", "headshot", "winner"
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
LABELS = ["self-harm", "bullying", "profanity", "harassment", "hate speech", "mental health", "violence", "threat"]

classifier = pipeline(
    "zero-shot-classification",
    model="facebook/bart-large-mnli",  # Good accuracy for zero-shot
    device=0 if torch.cuda.is_available() else -1
)
# ---------------------- Key Generation ----------------------
def generate_key(password: str) -> bytes:
    """Generate a Fernet key from a password string"""
    hashed = hashlib.sha256(password.encode()).digest()
    return base64.urlsafe_b64encode(hashed)

# Generate key from a secure password
ENCRYPTION_PASSWORD = "parent123"
fernet = Fernet(generate_key(ENCRYPTION_PASSWORD))

# ---------------------- Notification ----------------------
toaster = ToastNotifier()

def send_notification(text: str, score: float, source="model", labels=None):
    icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "images", "keyboard_vision_icon.ico"))
    label_info = ", ".join(labels) if labels else "unknown"
    toaster.show_toast(
        "Keyboard Vision Alert",
        f"⚠️ Risk detected!\nCategory: {label_info}\n'{text[:50]}..!'",
        duration=5,
        icon_path=icon_path
    )

    timestamp = datetime.now().isoformat()
    log_entry = f"{timestamp}\t{score:.2f}\t{source}\t{','.join(labels or [])}\t{text}"
    encrypted = fernet.encrypt(log_entry.encode())

    with open(SUMMARY_FILE, 'ab') as f:  # binary mode
        f.write(encrypted + b'\n')
# ---------------------- Classification & Alerting ----------------------
def classify_and_alert(text: str):
    lowered = text.lower()

    # Skip if the entire message is just an excluded word (or mostly noise)
    if any(word in lowered for word in EXCLUDED_WORDS):
        if all(w in EXCLUDED_WORDS for w in lowered.split()):
            return  # Only safe words present → skip check

    keyword_trigger = any(keyword in lowered for keyword in RISKY_KEYWORDS)

    result = classifier(text, candidate_labels=LABELS, multi_label=True)
    scores = dict(zip(result["labels"], result["scores"]))
    triggered_labels = {label: score for label, score in scores.items() if score >= threshold}
    model_trigger = bool(triggered_labels)

    if keyword_trigger:
        send_notification(text, 1.00, source="keyword", labels=["custom-keyword"])
    elif model_trigger:
        top_label = max(triggered_labels, key=triggered_labels.get)
        send_notification(text, scores[top_label], source="multi-label", labels=list(triggered_labels.keys()))



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
def launch_dashboard():
    threading.Thread(target=show_dashboard, daemon=True).start()

menu = pystray.Menu(
    pystray.MenuItem('Dashboard', lambda icon, item: launch_dashboard()),
    pystray.MenuItem('Settings', open_settings_window),
    pystray.MenuItem('Quit', quit_app)
)

tray_icon = pystray.Icon(
    'KeyboardVisionAI',
    create_tray_icon_image(),
    'Keyboard Vision AI',
    menu
)
def on_activate_exit():
    print("🔴 Keyboard Vision AI terminated via hotkey.")
    listener.stop()
    tray_icon.stop()
    os._exit(0)  # force exit

# Define hotkey: CTRL + ALT + Q (you can change this combo)
exit_hotkey = kb.GlobalHotKeys({
    '<ctrl>+<alt>+q': on_activate_exit
})

# ---------------------- Main Execution ----------------------
if __name__ == '__main__':
    # Start listening to keystrokes
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    exit_hotkey.start()
    # Launch system tray icon (blocks until Quit)
    tray_icon.run()