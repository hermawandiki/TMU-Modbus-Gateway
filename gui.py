import sys
import os
import json
import time
import hashlib
import hmac
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, 
                             QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QStackedWidget, QScrollArea, QFrame, QSizePolicy,
                             QGraphicsDropShadowEffect, QToolButton, QDialog,
                             QLineEdit)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QPixmap, QIcon

GUI_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui_data.json")
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

lcd_items = [
    ("TSU Oil Level", "%"),
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
        self.scroll_areas = {}
        self.scroll_dir = 1
        self.last_updated_at = 0.0
        
        self.init_gui()
        self.setup_auto_scroll()
        self.setup_data_polling()

    def add_shadow(self, widget, blur=22, x_offset=0, y_offset=5, alpha=90):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(blur)
        shadow.setXOffset(x_offset)
        shadow.setYOffset(y_offset)
        shadow.setColor(Qt.GlobalColor.black)
        color = shadow.color()
        color.setAlpha(alpha)
        shadow.setColor(color)
        widget.setGraphicsEffect(shadow)

    def init_gui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(800, 480)
        self.setStyleSheet("background-color: #F9F6EE;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.page_data = QStackedWidget()
        main_layout.addWidget(self.page_data)
        
        main_page = self.create_main_page()
        self.page_data.addWidget(main_page)
        
        hal_phys, scroll_phys = self.create_page_data("Physical Data Monitoring", lcd_items[:12])
        hal_elec, scroll_elec = self.create_page_data("Electrical Data Monitoring", lcd_items[12:])
        
        self.page_data.addWidget(hal_phys)
        self.scroll_areas[1] = scroll_phys
        
        self.page_data.addWidget(hal_elec)
        self.scroll_areas[2] = scroll_elec

        hal_setting = self.create_settings_page()
        self.page_data.addWidget(hal_setting)
        
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

            values = payload.get("values", [])
            if isinstance(values, list):
                for index, (name, unit) in enumerate(lcd_items):
                    if index < len(values) and name in self.label_val:
                        self.label_val[name].setText(self.format_value_with_unit(unit, values[index]))
            elif isinstance(values, dict):
                for name, label in self.label_val.items():
                    if name in values:
                        unit = next((item_unit for item_name, item_unit in lcd_items if item_name == name), "")
                        label.setText(self.format_value_with_unit(unit, values[name]))
        except Exception: pass

    def format_value_with_unit(self, unit, value):
        if isinstance(value, float):
            text_val = f"{value:.2f}"
        elif isinstance(value, int):
            text_val = str(value)
        else:
            text_val = str(value)

        if not unit:
            return text_val

        return (
            f'<span style="font-size:28px; color:#000080; font-weight:700;">{text_val}</span>'
            f'<span style="font-size:16px; color:#8A8A8A; font-weight:400;"> {unit}</span>'
        )

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

    def verify_settings_password(self, password_text):
        if not os.path.exists(CONFIG_FILE):
            return False

        try:
            with open(CONFIG_FILE, "r") as f:
                payload = json.load(f)

            auth_payload = payload.get("settings_auth", {})
            salt_hex = auth_payload.get("salt", "")
            hash_hex = auth_payload.get("password_hash", "")
            iterations = int(auth_payload.get("iterations", 200000))

            if not salt_hex or not hash_hex:
                return False

            salt = bytes.fromhex(str(salt_hex))
            expected_hash = bytes.fromhex(str(hash_hex))
            calculated_hash = hashlib.pbkdf2_hmac(
                "sha256", password_text.encode("utf-8"), salt, iterations
            )
            return hmac.compare_digest(calculated_hash, expected_hash)
        except Exception:
            return False

    def show_settings_login_popup(self):
        popup = QDialog(self)
        popup.setWindowTitle("Settings Login")
        popup.setFixedSize(250, 150)
        popup.setModal(True)
        popup.setStyleSheet("background-color: #F9F6EE;")

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        label_title = QLabel("Masukkan Password")
        label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_title.setStyleSheet("font-size: 18px; color: #333333;")

        input_password = QLineEdit()
        input_password.setPlaceholderText("Password")
        input_password.setEchoMode(QLineEdit.EchoMode.Password)
        input_password.setStyleSheet(
            "QLineEdit {"
            "background-color: white;"
            "border: 1px solid #D0D0D0;"
            "border-radius: 6px;"
            "padding: 8px 10px;"
            "font-size: 14px;"
            "}"
        )

        btn_login = QPushButton("Login")
        btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_login.setFixedHeight(36)
        btn_login.setStyleSheet("""
            QPushButton {
                background-color: #1670BE;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:pressed {
                background-color: #07223A;
            }
        """)

        login_ok = {"status": False}

        def handle_login():
            if self.verify_settings_password(input_password.text()):
                login_ok["status"] = True
                popup.accept()
            else:
                popup.reject()

        btn_login.clicked.connect(handle_login)
        input_password.returnPressed.connect(handle_login)

        layout.addWidget(label_title)
        layout.addWidget(input_password)
        layout.addSpacing(4)
        layout.addWidget(btn_login)

        popup.exec()

        if login_ok["status"]:
            self.page_data.setCurrentIndex(3)
        else:
            self.page_data.setCurrentIndex(0)

    def create_settings_page(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)

        header_layout = QHBoxLayout()

        btn_back = QPushButton("◀ HOME")
        btn_back.setFixedSize(120, 40)
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.setStyleSheet("""
            QPushButton { background-color: #1670BE; color: white; font-weight: bold; font-size: 14px; border-radius: 5px; }
            QPushButton:pressed { background-color: #07223A; }
        """)
        self.add_shadow(btn_back, blur=14, y_offset=3, alpha=110)
        btn_back.clicked.connect(lambda: self.page_data.setCurrentIndex(0))

        label_title = QLabel("TMU Setting")
        label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333333;")

        label_logo_tmu = QLabel()
        logo_tmu = QPixmap("assets/logoTMU.png")
        if not logo_tmu.isNull():
            logo_tmu_scaled = logo_tmu.scaledToHeight(40, Qt.TransformationMode.SmoothTransformation)
            label_logo_tmu.setPixmap(logo_tmu_scaled)

        header_layout.addWidget(btn_back)
        header_layout.addWidget(label_title, stretch=1)
        header_layout.addStretch()
        header_layout.addWidget(label_logo_tmu)

        box_frame = QFrame()
        box_frame.setStyleSheet("background-color: white; border-radius: 10px;")
        self.add_shadow(box_frame, blur=18, y_offset=4, alpha=70)

        main_layout.addLayout(header_layout)
        main_layout.addSpacing(18)
        main_layout.addWidget(box_frame)
        main_layout.addStretch()

        return main_widget

    def create_main_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 20, 30, 20)

        top_bar_layout = QHBoxLayout()

        label_logo_bd = QLabel()
        logo_bd = QPixmap("assets/logoBD.png")
        if not logo_bd.isNull():
            logo_bd_scaled = logo_bd.scaledToHeight(50, Qt.TransformationMode.SmoothTransformation)
            label_logo_bd.setPixmap(logo_bd_scaled)

        label_logo_tmu = QLabel()
        logo_tmu = QPixmap("assets/logoTMU.png")
        if not logo_tmu.isNull():
            logo_tmu_scaled = logo_tmu.scaledToHeight(40, Qt.TransformationMode.SmoothTransformation)
            label_logo_tmu.setPixmap(logo_tmu_scaled)

        btn_exit = QPushButton("X")
        btn_exit.setFixedSize(40, 40)
        btn_exit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_exit.setStyleSheet("""
            QPushButton { background-color: #AF3F3E; color: white; font-weight: bold; font-size: 16px; border-radius: 5px; }
            QPushButton:pressed { background-color: #8F3332; }
        """)
        self.add_shadow(btn_exit, blur=16, y_offset=3, alpha=110)
        btn_exit.clicked.connect(QApplication.quit)

        btn_setting = QPushButton("Setting")
        btn_setting.setFixedHeight(32)
        btn_setting.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_setting.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #7B7B7B;
                font-size: 14px;
                font-weight: 500;
                border: none;
                padding: 4px 8px;
            }
            QPushButton:hover {
                color: #5F5F5F;
            }
            QPushButton:pressed {
                color: #4F4F4F;
            }
        """)
        btn_setting.clicked.connect(self.show_settings_login_popup)

        top_bar_layout.addWidget(label_logo_bd)
        top_bar_layout.addSpacing(15)
        top_bar_layout.addWidget(label_logo_tmu, alignment=Qt.AlignmentFlag.AlignTop)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(btn_setting)
        top_bar_layout.addSpacing(6)
        top_bar_layout.addWidget(btn_exit)
        
        label_header = QLabel("Transformer Monitoring Unit\nPT Bambang Djaja")
        label_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_header.setStyleSheet("font-size: 32px; font-weight: bold; color: #333333;")
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(40)
        
        btn_physical = QToolButton()
        btn_physical.setText("Physical Data")
        btn_physical.setIcon(QIcon("assets/physical.png"))
        btn_physical.setIconSize(QSize(72, 72))
        btn_physical.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_physical.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn_physical.setStyleSheet("""
            QToolButton { background-color: #C1DEF8; color: #333333; font-size: 24px; font-weight: bold; border-radius: 15px; padding: 30px; }
            QToolButton:pressed { background-color: #3D99E8; } 
        """)
        self.add_shadow(btn_physical)
        btn_physical.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn_physical.clicked.connect(lambda: self.page_data.setCurrentIndex(1)) 
        
        btn_electrical = QToolButton()
        btn_electrical.setText("Electrical Data")
        btn_electrical.setIcon(QIcon("assets/electrical.png"))
        btn_electrical.setIconSize(QSize(72, 72))
        btn_electrical.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_electrical.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn_electrical.setStyleSheet("""
            QToolButton { background-color: #FBDA7B; color: #333333; font-size: 24px; font-weight: bold; border-radius: 15px; padding: 30px; }
            QToolButton:pressed { background-color: #DCAE47; }
        """)
        self.add_shadow(btn_electrical)
        btn_electrical.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn_electrical.clicked.connect(lambda: self.page_data.setCurrentIndex(2)) 
        
        button_layout.addWidget(btn_physical)
        button_layout.addWidget(btn_electrical)
        
        label_footer = QLabel("Transformer Monitoring Unit (TMU)\nPT Bambang Djaja © 2026")
        label_footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_footer.setStyleSheet("font-size: 14px; color: #666666;")
        
        layout.addLayout(top_bar_layout)
        layout.addSpacing(15)
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
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.setStyleSheet("""
            QPushButton { background-color: #1670BE; color: white; font-weight: bold; font-size: 14px; border-radius: 5px; }
            QPushButton:pressed { background-color: #07223A; }
        """)
        self.add_shadow(btn_back, blur=14, y_offset=3, alpha=110)
        btn_back.clicked.connect(lambda: self.page_data.setCurrentIndex(0))
        
        label_title = QLabel(title)
        label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333333;")

        label_logo_tmu = QLabel()
        logo_tmu = QPixmap("assets/logoTMU.png")
        if not logo_tmu.isNull():
            logo_tmu_scaled = logo_tmu.scaledToHeight(40, Qt.TransformationMode.SmoothTransformation)
            label_logo_tmu.setPixmap(logo_tmu_scaled)

        header_layout.addWidget(btn_back)
        header_layout.addWidget(label_title, stretch=1)
        header_layout.addStretch()
        header_layout.addWidget(label_logo_tmu)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; }
            QScrollBar:vertical { width: 0px; } 
        """)
        
        content_widget = QWidget()
        grid_layout = QGridLayout(content_widget) 
        grid_layout.setSpacing(10)
        
        for row, item in enumerate(list_param):
            name, _unit = item
            frame_row = QFrame()
            frame_row.setStyleSheet("background-color: white; border-radius: 8px;")
            self.add_shadow(frame_row, blur=18, y_offset=4, alpha=70)
            layout_row = QHBoxLayout(frame_row)
            layout_row.setContentsMargins(15, 10, 15, 10)
            
            label_name = QLabel(name)
            label_name.setStyleSheet("font-size: 20px; color: #555555; font-weight: bold;")
            
            label_number = QLabel("0.0") 
            label_number.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label_number.setTextFormat(Qt.TextFormat.RichText)
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