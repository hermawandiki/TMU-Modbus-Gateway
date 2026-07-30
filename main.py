import tkinter as tk
from tkinter import messagebox
import threading
import subprocess
import time
import sys
import os
import json
import logging

from data_handler import start_data_handler_engine, oled_print, GUI_DATA_FILE
from gateway import start_gateway_engine
from db_logger import start_db_logger_engine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ts = time.strftime("%Y%m%d")
log_dir = os.path.join(BASE_DIR, "logsys")
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(filename=os.path.join(log_dir, f"logsys-{ts}.log"), format='%(asctime)s | %(levelname)s: %(message)s', level=logging.INFO)

heartbeats = {
    "Data Handler": {"time": 0.0, "status": "STOPPED"},
    "Modbus Gateway": {"time": 0.0, "status": "STOPPED"},
    "DB & Excel Logger": {"time": 0.0, "status": "STOPPED"},
    "GUI Dashboard": {"time": 0.0, "status": "STOPPED"}
}
stop_events = {}
subprocesses = {"gui": None}
global_bus = None
config_data = {}

def load_config():
    global config_data
    cfg_path = os.path.join(BASE_DIR, "config.json")
    with open(cfg_path, "r") as f: cfg = json.load(f)
    config_data["host"] = cfg.get("host", "0.0.0.0")
    config_data["dummy"] = cfg.get("dummy_mode", False)
    config_data["serial"] = cfg.get("serial_port", {})
    config_data["map"] = {int(k): v for k, v in cfg.get("port_slave_map", {}).items()}
    return config_data

def update_hb(mod_name, t): heartbeats[mod_name]["time"] = t

def start_mod(name):
    global global_bus
    if heartbeats[name]["status"] == "RUNNING": return
    evt = threading.Event(); stop_events[name] = evt
    heartbeats[name]["status"] = "RUNNING"; heartbeats[name]["time"] = time.time()
    
    is_dummy = config_data.get("dummy", False)
    
    if name == "Data Handler":
        global_bus = start_data_handler_engine(config_data["serial"], is_dummy, evt, lambda t: update_hb(name, t))
        textFormat = "\n       ".join([f"{k} -> {v}" for k, v in config_data['map'].items()])
        oled_print(f" TMU MODBUS GATEWAY \nETH  : 192.168.4.120\nPORT : {textFormat}")
    elif name == "Modbus Gateway":
        start_gateway_engine(config_data["host"], config_data["map"], global_bus, is_dummy, evt, lambda t: update_hb(name, t))
    elif name == "DB & Excel Logger":
        start_db_logger_engine(evt, lambda t: update_hb(name, t))
    logging.info(f"{name} started.")

def stop_mod(name):
    if name in stop_events and heartbeats[name]["status"] == "RUNNING":
        stop_events[name].set(); heartbeats[name]["status"] = "STOPPED"; logging.info(f"{name} stopped.")

def restart_mod(name): stop_mod(name); time.sleep(0.5); start_mod(name)

def start_gui_subproc():
    name = "GUI Dashboard"
    if subprocesses["gui"] is None or subprocesses["gui"].poll() is not None:
        script = os.path.join(BASE_DIR, "gui.py")
        subprocesses["gui"] = subprocess.Popen([sys.executable, script])
        heartbeats[name]["status"] = "RUNNING"; heartbeats[name]["time"] = time.time()
        logging.info("GUI Dashboard started.")

def stop_gui_subproc():
    name = "GUI Dashboard"; proc = subprocesses.get("gui")
    if proc and proc.poll() is None:
        try: proc.terminate(); proc.wait(timeout=2)
        except: proc.kill()
        finally: subprocesses["gui"] = None; heartbeats[name]["status"] = "STOPPED"

def restart_gui_subproc(): stop_gui_subproc(); time.sleep(0.5); start_gui_subproc()

class ControlPanel:
    def __init__(self, root):
        self.root = root; self.root.title("TMU Gateway - Control Panel"); self.root.geometry("700x420"); self.root.configure(bg="#2C3E50"); self.root.resizable(False, False)
        tk.Label(root, text="TMU MODBUS GATEWAY CONTROL PANEL", font=("Helvetica", 16, "bold"), bg="#2C3E50", fg="#ECF0F1").pack(pady=10)
        self.frame_t = tk.Frame(root, bg="#34495E", bd=2, relief=tk.GROOVE); self.frame_t.pack(padx=15, pady=5, fill=tk.BOTH, expand=True)
        
        for col, (h, w) in enumerate(zip(["Subprocess", "Status", "Last Heartbeat", "   Start   |   Stop   |   Restart   "], [22, 10, 22, 26])):
            tk.Label(self.frame_t, text=h, font=("Helvetica", 11, "bold"), bg="#1ABC9C", fg="white", width=w, pady=6).grid(row=0, column=col, padx=1, pady=1)

        self.rows = {}; self.mods_cfg = [
            ("Data Handler", lambda: start_mod("Data Handler"), lambda: stop_mod("Data Handler"), lambda: restart_mod("Data Handler")),
            ("Modbus Gateway", lambda: start_mod("Modbus Gateway"), lambda: stop_mod("Modbus Gateway"), lambda: restart_mod("Modbus Gateway")),
            ("DB & Excel Logger", lambda: start_mod("DB & Excel Logger"), lambda: stop_mod("DB & Excel Logger"), lambda: restart_mod("DB & Excel Logger")),
            ("GUI Dashboard", start_gui_subproc, stop_gui_subproc, restart_gui_subproc)
        ]

        for idx, (m_name, c_start, c_stop, c_res) in enumerate(self.mods_cfg, start=1):
            tk.Label(self.frame_t, text=m_name, font=("Helvetica", 10), bg="#34495E", fg="white", anchor="w", padx=10).grid(row=idx, column=0, sticky="ew", pady=4)
            l_stat = tk.Label(self.frame_t, text="STOPPED", font=("Helvetica", 10, "bold"), bg="#E74C3C", fg="white"); l_stat.grid(row=idx, column=1, sticky="ew", padx=2, pady=4)
            l_hb = tk.Label(self.frame_t, text="-- : -- : --", font=("Courier", 10, "bold"), bg="#2C3E50", fg="#BDC3C7"); l_hb.grid(row=idx, column=2, sticky="ew", padx=2, pady=4)
            f_btn = tk.Frame(self.frame_t, bg="#34495E"); f_btn.grid(row=idx, column=3, pady=3)
            tk.Button(f_btn, text="START", font=("Helvetica", 8, "bold"), bg="#27AE60", fg="white", width=6, command=c_start).pack(side=tk.LEFT, padx=2)
            tk.Button(f_btn, text="STOP", font=("Helvetica", 8, "bold"), bg="#E74C3C", fg="white", width=6, command=c_stop).pack(side=tk.LEFT, padx=2)
            tk.Button(f_btn, text="RESTART", font=("Helvetica", 8, "bold"), bg="#F39C12", fg="white", width=8, command=c_res).pack(side=tk.LEFT, padx=2)
            self.rows[m_name] = {"stat": l_stat, "hb": l_hb}

        f_glob = tk.Frame(root, bg="#2C3E50"); f_glob.pack(pady=15)
        tk.Button(f_glob, text="START ALL", font=("Helvetica", 10, "bold"), bg="#27AE60", fg="white", width=12, pady=5, command=self.start_all).grid(row=0, column=0, padx=6)
        tk.Button(f_glob, text="RESTART ALL", font=("Helvetica", 10, "bold"), bg="#F39C12", fg="white", width=12, pady=5, command=self.restart_all).grid(row=0, column=1, padx=6)
        tk.Button(f_glob, text="STOP ALL", font=("Helvetica", 10, "bold"), bg="#D35400", fg="white", width=12, pady=5, command=self.stop_all).grid(row=0, column=2, padx=6)
        tk.Button(f_glob, text="STOP ALL & EXIT", font=("Helvetica", 10, "bold"), bg="#C0392B", fg="white", width=15, pady=5, command=self.exit_all).grid(row=0, column=3, padx=6)
        self.update_ui_loop()

    def start_all(self):
        start_mod("Data Handler"); start_mod("Modbus Gateway"); start_mod("DB & Excel Logger"); start_gui_subproc()

    def restart_all(self): self.stop_all(); time.sleep(1); self.start_all()
    def stop_all(self):
        for name in ["Data Handler", "Modbus Gateway", "DB & Excel Logger"]: stop_mod(name)
        stop_gui_subproc()

    def exit_all(self):
        if messagebox.askyesno("Confirmation", "Are you sure you want to stop all processes and exit?"): self.stop_all(); self.root.quit(); sys.exit(0)

    def update_ui_loop(self):
        now = time.time(); proc_gui = subprocesses.get("gui")
        if proc_gui and proc_gui.poll() is None:
            if os.path.exists(GUI_DATA_FILE):
                try: heartbeats["GUI Dashboard"]["time"] = os.path.getmtime(GUI_DATA_FILE)
                except: heartbeats["GUI Dashboard"]["time"] = now
            else:
                heartbeats["GUI Dashboard"]["time"] = now
        else:
            heartbeats["GUI Dashboard"]["status"] = "STOPPED"

        for m_name, widgets in self.rows.items():
            data = heartbeats[m_name]
            if data["status"] == "RUNNING":
                widgets["stat"].config(text="RUNNING", bg="#27AE60")
                if data["time"] > 0:
                    t_str = time.strftime('%H:%M:%S', time.localtime(data["time"])); diff = int(now - data["time"])
                    widgets["hb"].config(text=f"{t_str} (Active)" if diff < 5 else f"{t_str} ({diff}s delay)", fg="#2ECC71" if diff < 5 else "#F1C40F")
                else: widgets["hb"].config(text="Starting...", fg="#F39C12")
            else: widgets["stat"].config(text="STOPPED", bg="#C0392B"); widgets["hb"].config(text="-- : -- : --", fg="#BDC3C7")
        self.root.after(500, self.update_ui_loop)

if __name__ == "__main__":
    load_config(); root = tk.Tk(); app = ControlPanel(root); root.after(1000, app.start_all); root.mainloop()