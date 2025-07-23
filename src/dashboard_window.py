import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import os
import base64
import hashlib
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from collections import Counter, defaultdict
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import requests
from openai import OpenAI
import io
import re

# Load OpenAI key
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SUMMARY_FILE = os.path.expanduser("~/.keyboard_vision_alerts.log")
ENCRYPTION_PASSWORD = "parent123"

# ---------------------- Decryption ----------------------
def generate_key(password: str) -> bytes:
    hashed = hashlib.sha256(password.encode()).digest()
    return base64.urlsafe_b64encode(hashed)

def decrypt_log_lines(password: str):
    key = generate_key(password)
    fernet = Fernet(key)
    logs = []
    with open(SUMMARY_FILE, 'rb') as f:
        for line in f:
            try:
                decrypted = fernet.decrypt(line.strip()).decode()
                parts = decrypted.split('\t')
                if len(parts) == 5:
                    logs.append(parts)
            except Exception:
                continue
    return logs

# ---------------------- OpenAI Feedback ----------------------

client = OpenAI()

def get_openai_feedback(label_counts):
    summary = "\n".join([f"{k}: {v}" for k, v in label_counts.items()])
    prompt = f"""
You are a safety advisor reviewing a child's digital behavior.

Here is a distribution of detected risk types:
{summary}

Write a short and respectful summary for the parent, identifying trends or potential concerns.
Avoid exaggeration. Stay neutral and helpful. Add Keyboardvision AI as the source.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"(OpenAI Error: {str(e)})"

# def get_openai_feedback(label_counts):
#     # GPT-4 feedback temporarily disabled
#     return "(AI feedback is currently disabled for testing.)"

# ---------------------- Telegram Sender ----------------------
def send_chart_and_feedback(fig, feedback):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        messagebox.showerror("Telegram Error", "Bot token or chat ID missing.")
        return

    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)

    files = {'photo': ('chart.png', buf, 'image/png')}
    data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': feedback}

    try:
        res = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
            data=data,
            files=files
        )
        if res.status_code == 200:
            messagebox.showinfo("Telegram", "Report sent successfully!")
        else:
            messagebox.showerror("Telegram Error", f"Failed: {res.text}")
    except Exception as e:
        messagebox.showerror("Telegram Exception", str(e))

# ---------------------- Dashboard ----------------------
def show_dashboard():
    import threading  # Ensure this is imported at the top if not already

    # TEMP ROOT for password dialog only
    auth_root = tk.Tk()
    auth_root.withdraw()
    auth_root.attributes('-topmost', True)
    password = simpledialog.askstring("Parent Access", "Enter dashboard password:", show='*', parent=auth_root)
    auth_root.destroy()

    if password != ENCRYPTION_PASSWORD:
        messagebox.showerror("Access Denied", "Incorrect password.")
        return

    # ACTUAL DASHBOARD WINDOW (new fullscreen root)
    root = tk.Tk()
    root.title("Keyboard Vision AI - Risk Log Dashboard")
    root.state("zoomed")
    root.configure(bg="#f4f6f8")

    logs = decrypt_log_lines(password)

    # ---- Summary + Charts Prep ----
    today = datetime.today().date()
    total_alerts = len(logs)
    unique_labels = set()
    alerts_today = 0
    label_counts = Counter()
    date_counts = defaultdict(int)
    word_freq = Counter()

    for row in logs:
        words = re.findall(r'\b\w+\b', row[4].lower())
        word_freq.update(w for w in words if len(w) > 3 and w not in ["this", "that", "have", "with"])
    top_words = word_freq.most_common(10)

    for row in logs:
        ts, score, src, labels, text = row
        label_list = [l.strip() for l in labels.split(',')]
        unique_labels.update(label_list)
        label_counts.update(label_list)
        dt = datetime.fromisoformat(ts)
        if dt.date() == today:
            alerts_today += 1
        date_counts[dt.date()] += 1

    # ---- Summary Cards ----
    summary_frame = tk.Frame(root, bg="#f4f6f8")
    summary_frame.pack(pady=10)

    def make_card(label, value):
        frame = tk.Frame(summary_frame, bg="white", bd=2, relief="groove")
        tk.Label(frame, text=label, font=("Helvetica", 12, "bold"), bg="white").pack(padx=20, pady=(10, 0))
        tk.Label(frame, text=value, font=("Helvetica", 16), fg="#007bff", bg="white").pack(padx=20, pady=(0, 10))
        return frame

    for lbl, val in [("Total Alerts", total_alerts), ("Unique Labels", len(unique_labels)), ("Today's Alerts", alerts_today)]:
        make_card(lbl, val).pack(side="left", padx=10)

    # ---- Table View ----
    columns = ("Timestamp", "Score", "Source", "Labels", "Text")
    tree = ttk.Treeview(root, columns=columns, show='headings')
    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, width=180 if col != "Text" else 400, anchor="w")
    for row in logs:
        tree.insert('', tk.END, values=row)
    tree.pack(expand=True, fill='both', padx=10, pady=10)

    # ---- Charts ----
    fig, axs = plt.subplots(1, 3, figsize=(15, 4))
    axs[0].barh(list(label_counts.keys()), list(label_counts.values()), color='skyblue')
    axs[0].set_title("Risk Label Frequency")
    axs[0].set_xlabel("Count")
    axs[0].set_ylabel("Label")

    days = sorted(date_counts.keys())
    axs[1].plot(days, [date_counts[d] for d in days], marker='o', color='orange')
    axs[1].set_title("Alerts per Day")
    axs[1].set_xlabel("Date")
    axs[1].set_ylabel("Count")
    axs[1].tick_params(axis='x', rotation=45)

    if top_words:
        axs[2].barh([w for w, _ in reversed(top_words)], [c for _, c in reversed(top_words)], color='crimson')
        axs[2].set_title("Top Risky Words")
        axs[2].set_xlabel("Frequency")
        axs[2].invert_yaxis()
    else:
        axs[2].text(0.5, 0.5, "No word data", ha='center', va='center')

    plt.tight_layout()
    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.draw()
    canvas.get_tk_widget().pack(pady=10)
    
    badge_frame = tk.Frame(root, bg="#f4f6f8")
    badge_frame.pack(pady=5)

    tk.Label(badge_frame, text="Top Risk Types:", font=("Helvetica", 12, "bold"), bg="#f4f6f8").pack(anchor="w", padx=10)

    for label in sorted(label_counts, key=label_counts.get, reverse=True)[:5]:
        tk.Label(badge_frame, text=label, bg="#dc3545", fg="white", font=("Helvetica", 10, "bold"), padx=10, pady=5).pack(side="left", padx=5)

    # ---- Feedback Display (Async + Typing + Glow) ----
    feedback_frame = tk.Frame(root, bg="white", bd=3, relief="sunken", highlightthickness=2)
    feedback_frame.pack(pady=10, padx=20, fill="x")

    tk.Label(feedback_frame, text="AI-Generated Parent Insight", font=("Helvetica", 13, "bold"), bg="white").pack(anchor="w", padx=10, pady=(10, 0))
    feedback_canvas = tk.Canvas(feedback_frame, bg="#f8f9fa", height=120, highlightthickness=0)
    scroll_y = tk.Scrollbar(feedback_frame, orient="vertical", command=feedback_canvas.yview)
    inner_frame = tk.Frame(feedback_canvas, bg="#f8f9fa")
    feedback_canvas.create_window((0, 0), window=inner_frame, anchor="nw")
    feedback_canvas.configure(yscrollcommand=scroll_y.set)

    feedback_canvas.pack(side="left", fill="both", expand=True)
    scroll_y.pack(side="right", fill="y")

    typed_label = tk.Label(inner_frame, text="", justify="left", font=("Helvetica", 11), wraplength=1000, bg="#f8f9fa")
    typed_label.pack(anchor="w", padx=10, pady=10)

    def blink_border(times=20):
        if times <= 0:
            feedback_frame.config(highlightbackground="white")
            return
        current = feedback_frame.cget("highlightbackground")
        next_color = "#bee3f8" if current == "white" else "white"
        feedback_frame.config(highlightbackground=next_color)
        root.after(400, lambda: blink_border(times - 1))

    def type_feedback(text):
        def animate(i=0):
            if i < len(text):
                typed_label.config(text=text[:i+1])
                feedback_canvas.yview_moveto(1.0)
                root.after(15, lambda: animate(i + 1))
        animate()

    def fetch_feedback_async():
        feedback = get_openai_feedback(label_counts)
        root.after(0, lambda: type_feedback(feedback))
        root.after(0, lambda: blink_border())

    threading.Thread(target=fetch_feedback_async, daemon=True).start()

    # ---- Send to Telegram Button ----
    def send_report():
        feedback = get_openai_feedback(label_counts)
        send_chart_and_feedback(fig, feedback)

    send_btn = tk.Button(root, text="Send Report to Telegram", command=send_report,
                         bg="#007bff", fg="white", font=("Helvetica", 13), padx=20, pady=10)
    send_btn.pack(pady=15)

    ttk.Button(root, text="Close", command=root.destroy).pack(pady=(0, 15))
    root.mainloop()

    
