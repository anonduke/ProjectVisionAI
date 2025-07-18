import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from cryptography.fernet import Fernet
import base64, hashlib
from pathlib import Path
from collections import Counter, defaultdict
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import requests
import io
import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
# --- Config ---
SUMMARY_FILE = Path.home() / '.keyboard_vision_alerts.log'
ENCRYPTION_PASSWORD = "parent123"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Crypto Utilities ---
def generate_key(password: str) -> bytes:
    hashed = hashlib.sha256(password.encode()).digest()
    return base64.urlsafe_b64encode(hashed)

def decrypt_log_lines(password: str):
    key = generate_key(password)
    fernet = Fernet(key)
    decrypted_lines = []
    try:
        with open(SUMMARY_FILE, 'rb') as f:
            for line in f:
                decrypted = fernet.decrypt(line.strip())
                parts = decrypted.decode().split('\t')
                if len(parts) == 5:
                    decrypted_lines.append(parts)
    except Exception as e:
        raise ValueError("Failed to decrypt logs or invalid password.")
    return decrypted_lines

# --- Telegram Integration ---
def send_chart_to_telegram(fig):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        messagebox.showerror("Configuration Error", "Telegram bot token or chat ID not set in environment.")
        return
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    files = {'photo': ('chart.png', buf)}
    data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': 'Keyboard Vision AI - Risk Summary Chart'}
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    response = requests.post(url, data=data, files=files)
    if response.status_code == 200:
        messagebox.showinfo("Success", "Chart sent to Telegram.")
    else:
        messagebox.showerror("Error", f"Failed to send chart.\n{response.text}")

# --- GUI ---
def show_dashboard():
    root = tk.Tk()
    root.withdraw()
    password = simpledialog.askstring("Parent Access", "Enter dashboard password:", show='*')
    if not password:
        return

    try:
        logs = decrypt_log_lines(password)
    except ValueError:
        messagebox.showerror("Access Denied", "Incorrect password or corrupted log file.")
        return

    root.deiconify()
    root.title("Keyboard Vision AI - Risk Log Dashboard")
    root.geometry("1400x1000")
    root.configure(bg='#f4f6f8')

    # --- Header cards ---
    card_frame = tk.Frame(root, bg='#f4f6f8')
    card_frame.pack(pady=15)

    total_alerts = len(logs)
    unique_labels = set()
    today_count = 0
    today = datetime.datetime.now().date()

    for row in logs:
        timestamp, score, _, labels, _ = row
        unique_labels.update(labels.split(','))
        if timestamp.startswith(str(today)):
            today_count += 1

    def create_card(parent, title, value, color):
        frame = tk.Frame(parent, bg=color, width=200, height=80, bd=1, relief="solid")
        frame.pack_propagate(False)
        label1 = tk.Label(frame, text=title, bg=color, fg="white", font=("Helvetica", 12, "bold"))
        label2 = tk.Label(frame, text=value, bg=color, fg="white", font=("Helvetica", 16, "bold"))
        label1.pack()
        label2.pack()
        return frame

    create_card(card_frame, "Total Alerts", total_alerts, "#007bff").pack(side='left', padx=20)
    create_card(card_frame, "Unique Labels", len(unique_labels), "#28a745").pack(side='left', padx=20)
    create_card(card_frame, "Today's Alerts", today_count, "#dc3545").pack(side='left', padx=20)

    # --- TreeView ---
    columns = ("Timestamp", "Score", "Source", "Labels", "Text")
    tree = ttk.Treeview(root, columns=columns, show='headings')
    style = ttk.Style()
    style.configure("Treeview.Heading", font=("Helvetica", 13, "bold"))
    style.configure("Treeview", font=("Helvetica", 11))

    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, width=220 if col != "Text" else 500, anchor="w")

    for row in logs:
        tree.insert('', tk.END, values=row)

    tree.pack(expand=True, fill='both', padx=15, pady=(10, 10))

    # --- Charts ---
    all_labels = []
    daily_counts = defaultdict(int)
    for row in logs:
        label_str = row[3]
        all_labels.extend([lbl.strip() for lbl in label_str.split(',') if lbl.strip()])
        day = row[0].split('T')[0]
        daily_counts[day] += 1

    fig, axs = plt.subplots(1, 2, figsize=(14, 4))
    label_counts = Counter(all_labels)

    axs[0].bar(label_counts.keys(), label_counts.values(), color='#007bff')
    axs[0].set_title("Risk Label Frequency")
    axs[0].set_ylabel("Count")
    axs[0].tick_params(axis='x', labelrotation=45)

    axs[1].plot(list(daily_counts.keys()), list(daily_counts.values()), marker='o', color='#dc3545')
    axs[1].set_title("Alerts Per Day")
    axs[1].set_ylabel("Alerts")
    axs[1].tick_params(axis='x', labelrotation=45)

    plt.tight_layout()
    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.draw()
    canvas.get_tk_widget().pack(pady=(0, 20))

    # --- Buttons ---
    btn_frame = tk.Frame(root, bg='#f4f6f8')
    btn_frame.pack(pady=10)

    send_btn = tk.Button(btn_frame, text="Send Report to Telegram", font=("Helvetica", 13), bg="#007bff", fg="white", command=lambda: send_chart_to_telegram(fig))
    close_btn = tk.Button(btn_frame, text="Close Dashboard", font=("Helvetica", 13), bg="#6c757d", fg="white", command=root.destroy)

    send_btn.pack(side='left', padx=30, ipadx=20, ipady=10)
    close_btn.pack(side='left', padx=30, ipadx=20, ipady=10)

    root.mainloop()

if __name__ == '__main__':
    show_dashboard()
