import sys
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton
from PyQt6.QtCore import Qt

class mainWindow(QWidget):
	def __init__(self):
		super().__init__()
		self.init_gui()
	
	def init_gui(self):
		self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
		self.label_status = QLabel("TMU PT Bambang Djaja")
		
		self.exit_btn = QPushButton("EXIT", self)
		self.exit_btn.clicked.connect(self.exit_gui)
		
		self.showFullScreen()
	
	def exit_gui(self):
		QApplication.quit()

if __name__ == "__main__":
	app = QApplication(sys.argv)
	window = mainWindow()
	
	sys.exit(app.exec())
