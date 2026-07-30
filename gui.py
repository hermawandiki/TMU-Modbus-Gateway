import sys
import os
import json
import time
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, 
                             QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QScrollArea, QFrame)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GUI_DATA_FILE = os.path.join(BASE_DIR, "gui_data.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

lcd_items = [
    ("TSU Oil Level", "Level"),
    ("TSU Oil Temperature", "°C"),
    ("TSU Oil Pressure", "bar"),
    ("eDMCR Oil Level", "%"),
    ("eDMCR Oil Temperature", "°C"),
    ("eDMCR Oil Pressure", "bar"),
    ("Bus U Temperature", "°C"),
    ("Bus V Temperature", "°C"),
    ("Bus W Temperature", "°C"),
    ("WIT U Temperature", "°C"),
    ("WIT V Temperature", "°C"),
    ("WIT W Temperature", "°C"),
    ("U-N Phase Voltage", "V"),
    ("V-N Phase Voltage", "V"),
    ("W-N Phase Voltage", "V"),
    ("U-V Phase Voltage", "V"),
    ("V-W Phase Voltage", "V"),
    ("U-W Phase Voltage", "V"),
    ("U Phase Current", "A"),
    ("V Phase Current", "A"),
    ("W Phase Current", "A"),
    ("Average Current", "A"),
]

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.label_val = {} 
        self.label_stat = {} 
        self.dir_scroll = 1
        self.init_gui()
        self.setup_auto_scroll()
        self.setup_data_polling()

    def get_visible_lcd_items(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f: cfg = json.load(f)
                vis = cfg.get("lcd_visible_items", None)
                if isinstance(vis, list): return [item for item in lcd_items if item[0] in vis]
            except Exception: pass
        return lcd_items
    
    def init_gui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(800, 480)
        self.setStyleSheet("background-color: #F9F6EE;")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.create_main_page())
        self.showFullScreen()

    def create_main_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(25, 15, 25, 15)

        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 0, 0, 0)

        label_logo_bd = QLabel()
        logo_bd = QPixmap(os.path.join(BASE_DIR, "assets/logoBD.png"))
        if not logo_bd.isNull(): label_logo_bd.setPixmap(logo_bd.scaledToHeight(45, Qt.TransformationMode.SmoothTransformation))

        label_logo_tmu = QLabel()
        logo_tmu = QPixmap(os.path.join(BASE_DIR, "assets/logoTMU.png"))
        if not logo_tmu.isNull(): label_logo_tmu.setPixmap(logo_tmu.scaledToHeight(35, Qt.TransformationMode.SmoothTransformation))

        label_header = QLabel("Transformer Monitoring Unit\nPT Bambang Djaja")
        label_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_header.setStyleSheet("font-size: 20px; font-weight: bold; color: #333333; line-height: 1.1;")

        btn_minimize = QPushButton("—")
        btn_minimize.setFixedSize(40, 40)
        btn_minimize.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_minimize.setStyleSheet("QPushButton { background-color: #34495E; color: white; font-weight: bold; font-size: 16px; border-radius: 5px; } QPushButton:pressed { background-color: #1A252F; }")
        btn_minimize.clicked.connect(self.showMinimized)

        top_bar_layout.addWidget(label_logo_bd, alignment=Qt.AlignmentFlag.AlignVCenter)
        top_bar_layout.addSpacing(12)
        top_bar_layout.addWidget(label_logo_tmu, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignVCenter)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(label_header, alignment=Qt.AlignmentFlag.AlignVCenter)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(btn_minimize, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        self.main_scroll_area = QScrollArea()
        self.main_scroll_area.setWidgetResizable(True)
        self.main_scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; } QScrollArea > QWidget > QWidget { background-color: transparent; } QScrollBar:vertical { width: 0px; }")
        
        content_widget = QWidget()
        grid_layout = QGridLayout(content_widget) 
        grid_layout.setSpacing(8) 
        
        for row, item in enumerate(self.get_visible_lcd_items()):
            name, _unit = item
            frame_row = QFrame()
            frame_row.setStyleSheet("background-color: white; border-radius: 8px;")
            layout_row = QHBoxLayout(frame_row)
            layout_row.setContentsMargins(15, 8, 15, 8)
            
            label_name = QLabel(name)
            label_name.setStyleSheet("font-size: 19px; color: #555555; font-weight: bold;")
            
            label_status = QLabel("")
            label_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label_status.setStyleSheet("font-size: 14px; font-weight: bold; padding-right: 15px;")
            
            label_number = QLabel("0.0") 
            label_number.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label_number.setTextFormat(Qt.TextFormat.RichText)
            
            layout_row.addWidget(label_name); layout_row.addStretch(); layout_row.addWidget(label_status); layout_row.addWidget(label_number)
            grid_layout.addWidget(frame_row, row, 0)
            self.label_val[name] = label_number; self.label_stat[name] = label_status  
            
        grid_layout.setRowStretch(len(self.get_visible_lcd_items()), 1)
        self.main_scroll_area.setWidget(content_widget)

        self.label_timestamp = QLabel("Last Update: --:--:--")
        self.label_timestamp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_timestamp.setStyleSheet("font-size: 15px; font-weight: bold; color: #1670BE;")

        label_footer = QLabel("Transformer Monitoring Unit (TMU) | PT Bambang Djaja © 2026")
        label_footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_footer.setStyleSheet("font-size: 12px; color: #888888;")
        
        layout.addLayout(top_bar_layout); layout.addSpacing(4); layout.addWidget(self.main_scroll_area); layout.addSpacing(2); layout.addWidget(self.label_timestamp); layout.addSpacing(2); layout.addWidget(label_footer)
        return widget

    def setup_auto_scroll(self):
        self.timer_scroll = QTimer(self)
        self.timer_scroll.timeout.connect(self.run_auto_scroll)
        self.timer_scroll.start(50) 

    def run_auto_scroll(self):
        if not hasattr(self, 'main_scroll_area'): return
        sc = self.main_scroll_area.verticalScrollBar(); max_p = sc.maximum()
        if max_p <= 7: return
        now_p = sc.value()
        if now_p >= max_p: self.dir_scroll = -1
        elif now_p <= 0: self.dir_scroll = 1
        sc.setValue(now_p + self.dir_scroll)

    def setup_data_polling(self):
        self.timer_data = QTimer(self)
        self.timer_data.timeout.connect(self.refresh_data_from_file)
        self.timer_data.start(500)
        self.refresh_data_from_file()

    def hitung_dan_tampilkan_status(self, name, val):
        try: val = float(val)
        except (ValueError, TypeError): return
        text, color = "", "#388E3C"

        if "Temperature" in name:
            if val >= 80.0: text, color = "TRIP", "#D32F2F"
            elif val >= 70.0: text, color = "ALARM", "#F57C00"
            elif val >= 30.0: text, color = "NORMAL", "#388E3C"
            else: text, color = "LOW", "#F57C00"
        elif "Pressure" in name:
            if val >= 0.6: text, color = "TRIP", "#D32F2F"
            elif val >= 0.5: text, color = "ALARM", "#F57C00"
            elif val >= 0.3: text, color = "NORMAL", "#388E3C"
            else: text, color = "LOW", "#F57C00"
        elif "Level" in name:
            if val <= 1: text, color = "EXTREME LOW", "#D32F2F"
            elif val <= 2: text, color = "ALARM", "#F57C00"
            elif val >= 3: text, color = "NORMAL", "#388E3C"

        if name in self.label_stat:
            self.label_stat[name].setText(text)
            self.label_stat[name].setStyleSheet(f"font-size: 14px; font-weight: 800; color: {color}; padding-right: 15px;")

    def refresh_data_from_file(self):
        if not os.path.exists(GUI_DATA_FILE): return
        try:
            with open(GUI_DATA_FILE, "r") as f: payload = json.load(f)
            self.label_timestamp.setText(f"Last Update: {payload.get('updated_at', '--:--:--')}")
            values = payload.get("values", [])

            if isinstance(values, list):
                for index, (name, unit) in enumerate(lcd_items):
                    if index < len(values) and name in self.label_val:
                        val_aktual = values[index]
                        self.label_val[name].setText(self.format_value_with_unit(unit, val_aktual))
                        self.hitung_dan_tampilkan_status(name, val_aktual)
            elif isinstance(values, dict):
                for name, label in self.label_val.items():
                    if name in values:
                        val_aktual = values[name]
                        unit = next((item_unit for item_name, item_unit in lcd_items if item_name == name), "")
                        label.setText(self.format_value_with_unit(unit, val_aktual))
                        self.hitung_dan_tampilkan_status(name, val_aktual)
        except Exception: pass

    def format_value_with_unit(self, unit, value):
        text_val = f"{value:.2f}" if isinstance(value, float) else str(value)
        if not unit: return f'<span style="font-size:24px; color:#000080; font-weight:700;">{text_val}</span>'
        return f'<span style="font-size:24px; color:#000080; font-weight:700;">{text_val}</span><span style="font-size:16px; color:#8A8A8A; font-weight:400;"> {unit}</span>'

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("TMU Dashboard")
    window = MainWindow()
    sys.exit(app.exec())