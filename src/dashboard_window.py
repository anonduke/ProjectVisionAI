import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from cryptography.fernet import Fernet
import base64, hashlib
from pathlib import Path
from collections import Counter
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# --- Config ---
SUMMARY_FILE = Path.home() / '.keyboard_vision_alerts.log'
ENCRYPTION_PASSWORD = "parent123"

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

# --- GUI ---
def show_dashboard():
    root = tk.Tk()
    root.withdraw()  # Hide the root window

    password = simpledialog.askstring("Parent Access", "Enter dashboard password:", show='*')
    if not password:
        return

    try:
        logs = decrypt_log_lines(password)
    except ValueError:
        messagebox.showerror("Access Denied", "Incorrect password or corrupted log file.")
        return

    # Make root visible again to hold mainloop
    root.deiconify()
    root.title("Keyboard Vision AI - Risk Log Dashboard")
    root.geometry("900x400")

    columns = ("Timestamp", "Score", "Source", "Labels", "Text")
    tree = ttk.Treeview(root, columns=columns, show='headings')
    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, width=150 if col != "Text" else 300, anchor="w")

    for row in logs:
        tree.insert('', tk.END, values=row)

    tree.pack(expand=True, fill='both', padx=10, pady=10)
    ttk.Button(root, text="Close", command=root.destroy).pack(pady=5)
    # --- Plotting ---
    all_labels = []
    for row in logs:
        label_str = row[3]  # label column
        all_labels.extend([lbl.strip() for lbl in label_str.split(',') if lbl.strip()])

    label_counts = Counter(all_labels)

    if label_counts:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.barh(list(label_counts.keys()), list(label_counts.values()), color='skyblue')
        ax.set_xlabel("Frequency")
        ax.set_title("Risk Label Frequency")
        plt.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=root)
        canvas.draw()
        canvas.get_tk_widget().pack(pady=5)

    root.mainloop()  # ✅ Keeps the dashboard running

if __name__ == '__main__':
    show_dashboard()
