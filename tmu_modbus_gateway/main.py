import time
import datetime
import os
import sys
import logging
import queue
import selectors
import struct
import socket
import serial
import threading
import subprocess
from toolboxTMU import initTkinter
import functions

CONFIG = {
    "TCP_HOST": "0.0.0.0",
    "SERIAL_PORT": "COM3",
    "BAUDRATE": 9600,
    "TIMEOUT": 1.0,
    "PORT_MAPPING": {
        502: 1,
        503: 2,
        504: 3,
    }
}

# ts = time.strftime("%Y%m%d")
# # logName = r'/home/pi/tmu-v2-smart/assets/sysdata-test/syslog-' + ts + '.log'
# logName = r'D:/GitHub/TMU-Modbus-Gateway/tmu_modbus_gateway/log/syslog-' + ts + '.log'
# logging.basicConfig(
#     filename=logName,
#     format='%(asctime)s | %(levelname)s: %(message)s',
#     level=logging.DEBUG
# )

os.chdir('D:/GitHub/TMU-Modbus-Gateway/tmu_modbus_gateway/')

class App:
    def __init__(self):
        print("Starting TMU Modbus Gateway Application...")
        # logging.info("Starting TMU Modbus Gateway Application...")

if __name__ == "__main__":
    try:
        app = App()
    except KeyboardInterrupt:
        # logging.info("Program terminated by user.")
        print("Program terminated by user.")
        sys.exit(0)
    except Exception as e:
        # logging.error(f"Unhandled exception in main: {e}")
        print(f"Unhandled exception in main: {e}")
        sys.exit(1)