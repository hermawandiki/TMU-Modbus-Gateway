import sys
import os
import json
import time
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, 
                             QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QStackedWidget, QScrollArea, QFrame, QSizePolicy)
from PyQt6.QtCore import Qt, QTimer

GUI_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui_data.json")

UNITS = {
    "Oil Level": "%",
    "Oil Temperature": "C",
    "Oil Pressure": "bar",
    "Bus U Temperature": "C",
    "Bus V Temperature": "C",
    "Bus W Temperature": "C",
    "WIT U Temperature": "C",
    "WIT V Temperature": "C",
    "WIT W Temperature": "C",
    "U-N Phase Voltage": "V",
    "V-N Phase Voltage": "V",
    "W-N Phase Voltage": "V",
    "U-V Phase Voltage": "V",
    "V-W Phase Voltage": "V",
    "U-W Phase Voltage": "V",
    "U Phase Current": "A",
    "V Phase Current": "A",
    "W Phase Current": "A",
    "Average Current": "A",
}

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        
        self.label_val = {} 
        self.scroll_areas = {}
        self.scroll_dir = 1
        self.last_updated_at = 0.0
        
        self.init_gui()
        self.setup_auto_scroll()
        self.setup_data_polling()

    def init_gui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(800, 480)
        self.setStyleSheet("background-color: #F9F6EE;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.page_data = QStackedWidget()
        main_layout.addWidget(self.page_data)
        
        main_page = self.create_main_page()
        self.page_data.addWidget(main_page)
        
        data_physical = [
            "Oil Level", "Oil Temperature", "Oil Pressure", 
            "Bus U Temperature", "Bus V Temperature", "Bus W Temperature", 
            "WIT U Temperature", "WIT V Temperature", "WIT W Temperature"
        ]
        
        data_electrical = [
            "U-N Phase Voltage", "V-N Phase Voltage", "W-N Phase Voltage", 
            "U-V Phase Voltage", "V-W Phase Voltage", "U-W Phase Voltage", 
            "U Phase Current", "V Phase Current", "W Phase Current", 
            "Average Current"
        ]
        
        hal_phys, scroll_phys = self.create_page_data("Physical Data Monitoring", data_physical)
        hal_elec, scroll_elec = self.create_page_data("Electrical Data Monitoring", data_electrical)
        
        self.page_data.addWidget(hal_phys)
        self.scroll_areas[1] = scroll_phys
        
        self.page_data.addWidget(hal_elec)
        self.scroll_areas[2] = scroll_elec
        
        self.showFullScreen()

    def setup_auto_scroll(self):
        self.timer_scroll = QTimer(self)
        self.timer_scroll.timeout.connect(self.run_auto_scroll)
        self.timer_scroll.start(50) 
        
        self.page_data.currentChanged.connect(self.reset_pos_scroll)

    def setup_data_polling(self):
        self.timer_data = QTimer(self)
        self.timer_data.timeout.connect(self.refresh_data_from_file)
        self.timer_data.start(500)
        self.refresh_data_from_file()

    def refresh_data_from_file(self):
        if not os.path.exists(GUI_DATA_FILE):
            return

        try:
            with open(GUI_DATA_FILE, "r") as f:
                payload = json.load(f)

            updated_at = float(payload.get("updated_at", 0.0))
            self.last_updated_at = updated_at

            values = payload.get("values", {})
            for name, label in self.label_val.items():
                if name in values:
                    label.setText(self.format_value_with_unit(name, values[name]))
        except Exception: pass

    def format_value_with_unit(self, name, value):
        unit = UNITS.get(name, "")
        if isinstance(value, float):
            text_val = f"{value:.2f}"
        elif isinstance(value, int):
            text_val = str(value)
        else:
            text_val = str(value)

        return f"{text_val} {unit}".strip()

    def run_auto_scroll(self):
        idx = self.page_data.currentIndex()
        if idx == 0 or idx not in self.scroll_areas:
            return
        current_scroll_area = self.scroll_areas[idx]
        scrollbar = current_scroll_area.verticalScrollBar()
        max_pos = scrollbar.maximum()
        if max_pos == 0:
            return
        now_pos = scrollbar.value()
        if now_pos >= max_pos:
            self.dir_scroll = -1
        elif now_pos <= 0:
            self.dir_scroll = 1
        scrollbar.setValue(now_pos + self.dir_scroll)
        
    def reset_pos_scroll(self, idx):
        self.dir_scroll = 1
        if idx in self.scroll_areas:
            self.scroll_areas[idx].verticalScrollBar().setValue(0)

    def create_main_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 20, 30, 20)
        
        exit_layout = QHBoxLayout()
        btn_exit = QPushButton("X")
        btn_exit.setFixedSize(40, 40)
        btn_exit.setStyleSheet("""
            QPushButton { background-color: #AF3F3E; color: white; font-weight: bold; font-size: 16px; border-radius: 5px; }
            QPushButton:pressed { background-color: #8F3332; }
        """)
        btn_exit.clicked.connect(QApplication.quit)
        exit_layout.addStretch()
        exit_layout.addWidget(btn_exit)
        
        label_header = QLabel("Transformer Monitoring Unit\nPT Bambang Djaja")
        label_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_header.setStyleSheet("font-size: 32px; font-weight: bold; color: #333333;")
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(40)
        
        btn_physical = QPushButton("Physical Data")
        btn_physical.setStyleSheet("""
            QPushButton { background-color: #F0A04B; color: #333333; font-size: 26px; font-weight: bold; border-radius: 15px; }
            QPushButton:pressed { background-color: #D18534; } 
        """)
        btn_physical.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn_physical.clicked.connect(lambda: self.page_data.setCurrentIndex(1)) 
        
        btn_electrical = QPushButton("Electrical Data")
        btn_electrical.setStyleSheet("""
            QPushButton { background-color: #FBDA7B; color: #333333; font-size: 26px; font-weight: bold; border-radius: 15px; }
            QPushButton:pressed { background-color: #DCAE47; }
        """)
        btn_electrical.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn_electrical.clicked.connect(lambda: self.page_data.setCurrentIndex(2)) 
        
        button_layout.addWidget(btn_physical)
        button_layout.addWidget(btn_electrical)
        
        label_footer = QLabel("Transformer Monitoring Unit (TMU)\nPT Bambang Djaja © 2026")
        label_footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_footer.setStyleSheet("font-size: 14px; color: #666666;")
        
        layout.addLayout(exit_layout)
        layout.addWidget(label_header)
        layout.addSpacing(30)
        layout.addLayout(button_layout)
        layout.addSpacing(30)
        layout.addWidget(label_footer)
        
        return widget

    def create_page_data(self, title, list_param):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        header_layout = QHBoxLayout()
        
        btn_back = QPushButton("◀ HOME")
        btn_back.setFixedSize(120, 40)
        btn_back.setStyleSheet("""
            QPushButton { background-color: #AF3F3E; color: white; font-weight: bold; font-size: 14px; border-radius: 5px; }
            QPushButton:pressed { background-color: #8F3332; }
        """)
        btn_back.clicked.connect(lambda: self.page_data.setCurrentIndex(0))
        
        label_title = QLabel(title)
        label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333333;")

        header_layout.addWidget(btn_back)
        header_layout.addWidget(label_title, stretch=1)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; }
            QScrollBar:vertical { width: 0px; } 
        """)
        
        content_widget = QWidget()
        grid_layout = QGridLayout(content_widget) 
        grid_layout.setSpacing(10)
        
        for row, name in enumerate(list_param):
            frame_row = QFrame()
            frame_row.setStyleSheet("background-color: white; border-radius: 8px;")
            layout_row = QHBoxLayout(frame_row)
            layout_row.setContentsMargins(15, 10, 15, 10)
            
            label_name = QLabel(name)
            label_name.setStyleSheet("font-size: 18px; color: #555555; font-weight: bold;")
            
            label_number = QLabel("0.0") 
            label_number.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label_number.setStyleSheet("font-size: 22px; color: #000080; font-weight: bold;")
            
            layout_row.addWidget(label_name)
            layout_row.addWidget(label_number)
            
            grid_layout.addWidget(frame_row, row, 0)
            
            self.label_val[name] = label_number
            
        grid_layout.setRowStretch(len(list_param), 1)
        scroll_area.setWidget(content_widget)
        
        main_layout.addLayout(header_layout)
        main_layout.addSpacing(15)
        main_layout.addWidget(scroll_area)
        
        return main_widget, scroll_area

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec())