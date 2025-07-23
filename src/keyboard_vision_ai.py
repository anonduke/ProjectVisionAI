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
from sklearn.metrics import classification_report
import pandas as pd

# ---------------------- Configuration ----------------------
CONFIG_FILE = Path.home() / '.keyboard_vision_settings.json'
SUMMARY_FILE = Path.home() / '.keyboard_vision_alerts.log'

# Default settings if CONFIG_FILE does not exist
DEFAULT_SETTINGS = {
    'threshold': 0.99,
    'buffer_size': 100
}

RISKY_KEYWORDS = {
    "joder","mierda", "puta", "pendejo", "culo",
}
EXCLUDED_WORDS = {
    "you", "will", "lol", "game", "play", "killstreak", "headshot", "winner", 
    "likes", "nobody", "even", "exist", "myself", "away", "just", "want","whish","t"
}
# ---------------------- Sample Data for Testing ----------------------
test_samples = [
    {"text": "I want to die", "labels": ["self-harm"]},
    {"text": "You are so stupid", "labels": ["bullying"]},
    {"text": "Go to hell", "labels": ["profanity"]},
    {"text": "I love pizza", "labels": []},
    {"text": "You're amazing!", "labels": []},
    {"text": "I will kill you", "labels": ["threat", "violence"]},
]


# ---------------------- Settings Management ----------------------
def load_settings():
    if not CONFIG_FILE.exists():
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    try:
        data = json.loads(CONFIG_FILE.read_text())
        for key, default in DEFAULT_SETTINGS.items():
            data.setdefault(key, default)
        return data
    except (json.JSONDecodeError, IOError):
        return DEFAULT_SETTINGS.copy()

def save_settings(settings: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(settings, indent=4))
    except IOError as e:
        print(f"Error saving settings: {e}")

settings = load_settings()
threshold = settings['threshold']
buffer_size = settings['buffer_size']

# ---------------------- Model Initialization ----------------------
LABELS = ["self-harm", "bullying", "profanity", "harassment", "hate speech", "mental health", "violence", "threat"]
classifier = pipeline(
    "zero-shot-classification",
    #model="facebook/bart-large-mnli",
    #model="facebook--bart-large-cnn"
    #model="distilbert-base-uncased-finetuned-sst-2-english"
    model="MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli", 
    #model="QuantStack--Wan2.1_I2V_14B_FusionX-GGUF",
    #model="typeform/distilbert-base-uncased-mnli",
    device=0 if torch.cuda.is_available() else -1
)

# device = 0 if torch.cuda.is_available() else -1
# classifier = pipeline(
#     'text-classification',
#     model='distilbert-base-uncased-finetuned-sst-2-english',
#     device=device
# )
# ---------------------- Key Generation ----------------------
def generate_key(password: str) -> bytes:
    hashed = hashlib.sha256(password.encode()).digest()
    return base64.urlsafe_b64encode(hashed)

ENCRYPTION_PASSWORD = "parent123"
fernet = Fernet(generate_key(ENCRYPTION_PASSWORD))

# ---------------------- Notification ----------------------
toaster = ToastNotifier()

def send_notification(text: str, score: float, source="model", labels=None):
    label_info = ", ".join(labels) if labels else "unknown"
    threading.Thread(target=lambda: toaster.show_toast(
        "Keyboard Vision Alert",
        f"⚠️ Risk: {text[:50]}..! \n"
        f"Category : {label_info}",
        duration=5,
        icon_path=None
    ), daemon=True).start()

    timestamp = datetime.now().isoformat()
    log_entry = f"{timestamp}	{score:.2f}	{source}	{','.join(labels or [])}	{text}"
    encrypted = fernet.encrypt(log_entry.encode())

    with open(SUMMARY_FILE, 'ab') as f:
        f.write(encrypted + b'')

# ---------------------- Classification & Alerting ----------------------
def classify_and_alert(text: str):
    lowered = text.lower()
    if any(word in lowered for word in EXCLUDED_WORDS):
        if all(w in EXCLUDED_WORDS for w in lowered.split()):
            return

    keyword_trigger = any(keyword in lowered for keyword in RISKY_KEYWORDS)
    result = classifier(text, candidate_labels=LABELS, multi_label=True)
    scores = dict(zip(result["labels"], result["scores"]))
    triggered_labels = {label: score for label, score in scores.items() if score >= threshold}
    model_trigger = bool(triggered_labels)

    # print("----------")
    # print(f"Text: {text}")
    # for label, score in zip(result["labels"], result["scores"]):
    #     print(f"{label}: {score:.2f}")
    # print("----------") 

    if keyword_trigger:
        send_notification(text, 1.00, source="keyword", labels=["custom-keyword"])
    elif model_trigger:
        top_label = max(triggered_labels, key=triggered_labels.get)
        send_notification(text, scores[top_label], source="multi-label", labels=list(triggered_labels.keys()))

def schedule_classification(text: str):
    threading.Thread(target=classify_and_alert, args=(text,), daemon=True).start()

# ---------------------- Keystroke Listener ----------------------
buffer = ''

def on_press(key):
    global buffer
    try:
        char = key.char or ''
    except AttributeError:
        char = ' '
    buffer += char
    if char.isspace() or len(buffer) >= buffer_size:
        snippet = buffer.strip()
        buffer = ''
        if snippet:
            schedule_classification(snippet)

# ---------------------- System Tray & Settings UI ----------------------
def create_tray_icon_image():
    img = Image.new('RGB', (64, 64), 'white')
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 63, 63), outline='black')
    draw.text((18, 18), 'K', fill='red')
    return img

def open_settings_window(icon, item):
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
    icon.stop()
    listener.stop()

# Dashboard launch via tray or hotkey

def launch_dashboard():
    threading.Thread(target=show_dashboard, daemon=True).start()

# Build the tray menu
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
    def ask_password():
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        password = tk.simpledialog.askstring("Authentication Required", "Enter parent password:", show='*')
        root.destroy()
        return password == ENCRYPTION_PASSWORD

    if ask_password():
        print("🔴🔴🔴🔴 Keyboard Vision AI terminated via hotkey. 🔴🔴🔴🔴")
        listener.stop()
        tray_icon.stop()
        os._exit(0)
    else:
        print("Incorrect password. Termination aborted.")

def on_activate_dashboard():
    print("Opening dashboard via hotkey...")
    launch_dashboard()

exit_hotkey = kb.GlobalHotKeys({
    '<ctrl>+<alt>+q': on_activate_exit,
    '<ctrl>+<alt>+d': on_activate_dashboard
})
def evaluate_model(classifier, label_list):
    y_true = []
    y_pred = []

    for sample in test_samples:
        result = classifier(sample["text"], candidate_labels=label_list, multi_label=True)
        pred_labels = [label for label, score in zip(result["labels"], result["scores"]) if score >= 0.7]
        
        y_true.append([1 if l in sample["labels"] else 0 for l in label_list])
        y_pred.append([1 if l in pred_labels else 0 for l in label_list])

    print("\n Evaluation on Test Samples:")
    print(classification_report(
        y_true, y_pred,
        target_names=label_list,
        zero_division=0  # Avoids crashing on undefined metrics
    ))

if __name__ == '__main__':
    evaluate_model(classifier, LABELS)
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    exit_hotkey.start()
    tray_icon.run()
