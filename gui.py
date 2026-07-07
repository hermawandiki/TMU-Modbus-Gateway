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
                             QLineEdit, QCheckBox)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QPixmap, QIcon, QAction

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

    def get_visible_lcd_items(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    cfg = json.load(f)
                visible_items = cfg.get("lcd_visible_items", None)
                if isinstance(visible_items, list):
                    return [item for item in lcd_items if item[0] in visible_items]
            except Exception:
                pass

        return lcd_items
    
    def save_visible_lcd_items(self, checked_names):
        cfg = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    cfg = json.load(f)
            except Exception:
                pass
        cfg["lcd_visible_items"] = checked_names
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(cfg, f, indent=4)
        except Exception:
            pass
        
        self.rebuild_lcd_pages()
    
    def rebuild_lcd_pages(self):
        visible_items = self.get_visible_lcd_items()

        phys_master_names = [x[0] for x in lcd_items[:12]]
        phys_items = [x for x in visible_items if x[0] in phys_master_names]
        elec_items = [x for x in visible_items if x[0] not in phys_master_names]

        old_phys = self.page_data.widget(1)
        old_elec = self.page_data.widget(2)

        hal_phys, scroll_phys = self.create_page_data("Physical Data Monitoring", phys_items)
        hal_elec, scroll_elec = self.create_page_data("Electrical Data Monitoring", elec_items)

        self.page_data.removeWidget(old_phys)
        self.page_data.insertWidget(1, hal_phys)
        self.scroll_areas[1] = scroll_phys
        
        self.page_data.removeWidget(old_elec)
        self.page_data.insertWidget(2, hal_elec)
        self.scroll_areas[2] = scroll_elec

        self.refresh_data_from_file()

    def init_gui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(800, 480)
        self.setStyleSheet("background-color: #F9F6EE;")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.page_data = QStackedWidget()
        main_layout.addWidget(self.page_data)
        
        # Page 0 - Main Page
        self.page_data.addWidget(self.create_main_page())
        
        visible_items = self.get_visible_lcd_items()
        phys_master_names = [x[0] for x in lcd_items[:12]]
        phys_items = [x for x in visible_items if x[0] in phys_master_names]
        elec_items = [x for x in visible_items if x[0] not in phys_master_names]
        hal_phys, scroll_phys = self.create_page_data("Physical Data Monitoring", phys_items)
        hal_elec, scroll_elec = self.create_page_data("Electrical Data Monitoring", elec_items)
        # Page 1 - Physical Data
        self.page_data.addWidget(hal_phys)
        self.scroll_areas[1] = scroll_phys
        # Page 2 - Electrical Data
        self.page_data.addWidget(hal_elec)
        self.scroll_areas[2] = scroll_elec
        # Page 3 - Setting Page
        self.page_data.addWidget(self.create_settings_page())
        # Page 4 - Change password page
        self.page_data.addWidget(self.create_password_page())
        # Page 5 - Data filter page
        self.page_data.addWidget(self.create_filter_page())
        
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
        if max_pos <= 7:
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

    def save_new_password(self, old_pass, new_pass, confirm_pass, status_label):
        if not old_pass or not new_pass or not confirm_pass:
            status_label.setText("New password cannot be empty!")
            status_label.setStyleSheet("color: #D32F2F; font-size: 14px; font-weight: bold;")
            return

        if new_pass != confirm_pass:
            status_label.setText("New password confirmation does not match!")
            status_label.setStyleSheet("color: #D32F2F; font-size: 14px; font-weight: bold;")
            return

        if not self.verify_settings_password(old_pass):
            status_label.setText("The old password is wrong!")
            status_label.setStyleSheet("color: #D32F2F; font-size: 14px; font-weight: bold;")
            return

        try:
            config_data = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    config_data = json.load(f)
            iterations = 200000
            new_salt = os.urandom(16)
            new_hash = hashlib.pbkdf2_hmac(
                "sha256", new_pass.encode("utf-8"), new_salt, iterations
            )

            config_data["settings_auth"] = {
                "salt": new_salt.hex(),
                "password_hash": new_hash.hex(),
                "iterations": iterations
            }

            with open(CONFIG_FILE, "w") as f:
                json.dump(config_data, f, indent=4)

            status_label.setText("Password changed successfully!")
            status_label.setStyleSheet("color: #2E7D32; font-size: 14px; font-weight: bold;")

        except Exception as e:
            status_label.setText("Failed to save password to file!")
            status_label.setStyleSheet("color: #D32F2F; font-size: 14px; font-weight: bold;")

    def show_settings_login_popup(self):
        popup = QDialog(self)
        popup.setWindowTitle("Settings Login")
        popup.setFixedSize(250, 150)
        popup.setModal(True)
        popup.setStyleSheet("background-color: #F9F6EE;")

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        label_title = QLabel("Enter Password")
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

        grid_menu = QHBoxLayout()
        grid_menu.setSpacing(30)

        btn_pass = QPushButton("Change Password")
        btn_pass.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn_pass.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_pass.setStyleSheet("""
            QPushButton { background-color: white; color: #1670BE; font-size: 22px; font-weight: bold; border-radius: 12px; border: 2px solid #E0E0E0; }
            QPushButton:hover { background-color: #F0F8FF; border-color: #1670BE; }
            QPushButton:pressed { background-color: #D1E8FF; }
        """)

        self.add_shadow(btn_pass, blur=18, y_offset=4, alpha=70)
        btn_pass.clicked.connect(lambda: self.page_data.setCurrentIndex(4))

        btn_filter = QPushButton("Data Display")
        btn_filter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_filter.setStyleSheet("""
            QPushButton { background-color: white; color: #1670BE; font-size: 22px; font-weight: bold; border-radius: 12px; border: 2px solid #E0E0E0; }
            QPushButton:hover { background-color: #F0F8FF; border-color: #1670BE; }
            QPushButton:pressed { background-color: #D1E8FF; }
        """)
        self.add_shadow(btn_filter, blur=18, y_offset=4, alpha=70)
        btn_filter.clicked.connect(lambda: self.page_data.setCurrentIndex(5))

        grid_menu.addWidget(btn_pass)
        grid_menu.addWidget(btn_filter)

        main_layout.addLayout(header_layout)
        main_layout.addSpacing(18)
        main_layout.addLayout(grid_menu)
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

    def create_password_page(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)

        header_layout = QHBoxLayout()
        btn_back = QPushButton("◀ BACK")
        btn_back.setFixedSize(120, 40)
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.setStyleSheet("""
            QPushButton { background-color: #1670BE; color: white; font-weight: bold; font-size: 14px; border-radius: 5px; }
            QPushButton:pressed { background-color: #07223A; }
        """)
        self.add_shadow(btn_back, blur=14, y_offset=3, alpha=110)
        btn_back.clicked.connect(lambda: self.page_data.setCurrentIndex(3)) # Kembali ke menu setting (Index 3)

        label_title = QLabel("Change Admin Password")
        label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333333;")

        header_layout.addWidget(btn_back)
        header_layout.addWidget(label_title, stretch=1)
        header_layout.addSpacing(120)

        box_frame = QFrame()
        box_frame.setStyleSheet("QFrame { background-color: white; border-radius: 10px; }")
        self.add_shadow(box_frame, blur=18, y_offset=4, alpha=70)

        form_layout = QVBoxLayout(box_frame)
        form_layout.setContentsMargins(30, 20, 30, 20)
        form_layout.setSpacing(10)

        input_style = """
            QLineEdit { background-color: #F8F9FA; border: 1px solid #CCCCCC; border-radius: 6px; padding: 8px 12px; font-size: 14px; color: #333333; }
            QLineEdit:focus { border: 1px solid #1670BE; background-color: #FFFFFF; }
        """
        input_old = QLineEdit()
        input_old.setPlaceholderText("Enter old password")
        input_old.setEchoMode(QLineEdit.EchoMode.Password)
        input_old.setStyleSheet(input_style)

        input_new = QLineEdit()
        input_new.setPlaceholderText("Enter new password")
        input_new.setEchoMode(QLineEdit.EchoMode.Password)
        input_new.setStyleSheet(input_style)

        input_confirm = QLineEdit()
        input_confirm.setPlaceholderText("Enter new password confirmation")
        input_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        input_confirm.setStyleSheet(input_style)

        lbl_status = QLabel("")
        lbl_status.setFixedHeight(20)

        btn_save = QPushButton("Save Password")
        btn_save.setFixedHeight(38)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton { background-color: #2E7D32; color: white; font-weight: bold; font-size: 15px; border-radius: 6px; }
            QPushButton:hover { background-color: #1B5E20; }
            QPushButton:pressed { background-color: #104014; }
        """)

        def handle_change():
            self.save_new_password(input_old.text(), input_new.text(), input_confirm.text(), lbl_status)
            if "berhasil" in lbl_status.text().lower():
                input_old.clear(); input_new.clear(); input_confirm.clear()

        btn_save.clicked.connect(handle_change)

        form_layout.addWidget(input_old)
        form_layout.addWidget(input_new)
        form_layout.addWidget(input_confirm)
        form_layout.addWidget(lbl_status)
        form_layout.addWidget(btn_save)

        main_layout.addLayout(header_layout)
        main_layout.addSpacing(15)
        main_layout.addWidget(box_frame)
        main_layout.addStretch()

        return main_widget

    def create_filter_page(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)

        header_layout = QHBoxLayout()
        btn_back = QPushButton("◀ BACK")
        btn_back.setFixedSize(120, 40)
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.setStyleSheet("""
            QPushButton { background-color: #1670BE; color: white; font-weight: bold; font-size: 14px; border-radius: 5px; }
            QPushButton:pressed { background-color: #07223A; }
        """)
        self.add_shadow(btn_back, blur=14, y_offset=3, alpha=110)
        btn_back.clicked.connect(lambda: self.page_data.setCurrentIndex(3))

        label_title = QLabel("Data Display Filters")
        label_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333333;")

        btn_save = QPushButton("Save")
        btn_save.setFixedSize(100, 40)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton { background-color: #2E7D32; color: white; font-weight: bold; font-size: 14px; border-radius: 5px; }
            QPushButton:pressed { background-color: #1B5E20; }
        """)
        self.add_shadow(btn_save, blur=14, y_offset=3, alpha=110)

        header_layout.addWidget(btn_back)
        header_layout.addWidget(label_title, stretch=1)
        header_layout.addWidget(btn_save)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; } QScrollBar:vertical { width: 0px; }")

        content_widget = QWidget()
        grid_layout = QVBoxLayout(content_widget)
        grid_layout.setSpacing(8)

        checkboxes = {}
        visible_items = [x[0] for x in self.get_visible_lcd_items()]

        for item in lcd_items:
            name, unit = item
            frame_row = QFrame()
            frame_row.setStyleSheet("background-color: white; border-radius: 8px;")
            self.add_shadow(frame_row, blur=12, y_offset=2, alpha=50)
            layout_row = QHBoxLayout(frame_row)
            layout_row.setContentsMargins(15, 8, 15, 8)

            lbl_name = QLabel(f"{name} ({unit})")
            lbl_name.setStyleSheet("font-size: 18px; color: #333333; font-weight: 600;")

            chk = QCheckBox()
            chk.setChecked(name in visible_items)
            chk.setStyleSheet("""
                QCheckBox::indicator { width: 28px; height: 28px; }
            """)
            
            layout_row.addWidget(lbl_name)
            layout_row.addStretch()
            layout_row.addWidget(chk)

            grid_layout.addWidget(frame_row)
            checkboxes[name] = chk

        grid_layout.addStretch()
        scroll_area.setWidget(content_widget)

        def handle_save_filter():
            selected = [name for name, chk in checkboxes.items() if chk.isChecked()]
            self.save_visible_lcd_items(selected)
            btn_save.setText("Saved!")
            QTimer.singleShot(2000, lambda: btn_save.setText("Save"))

        btn_save.clicked.connect(handle_save_filter)

        main_layout.addLayout(header_layout)
        main_layout.addSpacing(15)
        main_layout.addWidget(scroll_area)

        return main_widget


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec())
