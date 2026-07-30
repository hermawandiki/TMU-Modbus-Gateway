import threading
import time
import json
import os
import struct
import serial
import logging
import random
import smbus2
import Adafruit_ADS1x15
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GUI_DATA_FILE = os.path.join(BASE_DIR, "gui_data.json")

try:
    adc = Adafruit_ADS1x15.ADS1115(address=0x48, busnum=1)
except Exception:
    adc = None

try:
    GPIO.setmode(GPIO.BCM)
    for pin in [13, 22, 17, 27]: GPIO.setup(pin, GPIO.IN)
except Exception:
    pass

adc_channels = 4
adc_registers = [0] * adc_channels
adc_lock = threading.Lock()

lcd_fields = [
    "TSU Oil Level", "TSU Oil Temperature", "TSU Oil Pressure",
    "eDMCR Oil Level", "eDMCR Oil Temperature", "eDMCR Oil Pressure",
    "Bus U Temperature", "Bus V Temperature", "Bus W Temperature",
    "WIT U Temperature", "WIT V Temperature", "WIT W Temperature",
    "U-N Phase Voltage", "V-N Phase Voltage", "W-N Phase Voltage",
    "U-V Phase Voltage", "V-W Phase Voltage", "U-W Phase Voltage",
    "U Phase Current", "V Phase Current", "W Phase Current",
    "Average Current"
]
lcd_values = [0.0] * len(lcd_fields)
lcd_lock = threading.Lock()

I2C_BUS = 1
I2C_ADDR = 0x3C
try:
    bus_i2c = smbus2.SMBus(I2C_BUS)
except Exception:
    bus_i2c = None

def oled_cmd(cmd):
    if bus_i2c: bus_i2c.write_byte_data(I2C_ADDR, 0x00, cmd)

def oled_init():
    if not bus_i2c: return
    for c in [0xAE, 0x00, 0x10, 0x40, 0x81, 0xCF, 0xA1, 0xC8, 0xA6,
              0xA8, 0x3F, 0xD3, 0x00, 0xD5, 0x80, 0xD9, 0xF1, 0xDA,
              0x12, 0xDB, 0x40, 0x20, 0x00, 0x8D, 0x14, 0xAF]:
        oled_cmd(c)

def oled_show(image):
    if not bus_i2c: return
    image = image.rotate(180)
    oled_cmd(0x21); oled_cmd(0); oled_cmd(127)
    oled_cmd(0x22); oled_cmd(0); oled_cmd(7)
    pix = list(image.getdata())
    buf = []
    for page in range(8):
        for col in range(128):
            byte = 0
            for bit in range(8):
                if pix[(page * 8 + bit) * 128 + col]: byte |= (1 << bit)
            buf.append(byte)
    for i in range(0, len(buf), 16):
        bus_i2c.write_i2c_block_data(I2C_ADDR, 0x40, buf[i:i+16])

def oled_print(teks: str):
    if not bus_i2c: return
    try: font = Image.truetype("/usr/share/fonts/truetype/dejavu/DeJaVuSansMono.ttf", 10)
    except: font = ImageFont.load_default()
    img = Image.new("1", (128, 64))
    draw = ImageDraw.Draw(img)
    for i, row in enumerate(teks.splitlines()): draw.text((0, i * 12), row, font=font, fill=255)
    oled_show(img)

class SerialBus:
    def __init__(self, serial_cfg: dict):
        self._lock = threading.Lock()
        self.serial_cfg = serial_cfg
        self.timeout = serial_cfg.get("timeout", 1.0)
        self._ser = None
        self.connect()
    
    def connect(self):
        try:
            if self._ser: self._ser.close()
        except: pass
        try:
            self._ser = serial.Serial(**self.serial_cfg)
            logging.info(f"RS485 Connected: {self.serial_cfg.get('port')}")
        except Exception as e:
            logging.error(f"Failed open RS485: {e}")
            self._ser = None

    def send_and_receive(self, request: bytes) -> bytes:
        with self._lock:
            if not self._ser:
                self.connect()
                if not self._ser: return b""
            try:
                time.sleep(0.01)
                self._ser.reset_input_buffer()
                self._ser.write(request)
                self._ser.flush()
                res = b""
                start = time.time()
                while time.time() - start < self.timeout:
                    if self._ser.in_waiting:
                        res += self._ser.read(self._ser.in_waiting)
                        if len(res) >= 5: break
                    time.sleep(0.005)
                return res
            except Exception as e:
                logging.error(f"RS485 IO Error: {e}")
                self._ser = None
                return b""

def inject_dummy_data():
    with lcd_lock:
        lcd_values[1] = round(random.uniform(50.0, 52.0), 2)  # TSU Oil Temp
        lcd_values[4] = round(random.uniform(50.0, 52.0), 2)  # eDMCR Oil Temp
        lcd_values[2] = round(random.uniform(0.10, 0.70), 3)  # TSU Pressure
        lcd_values[5] = round(random.uniform(0.10, 0.70), 3)  # eDMCR Pressure
        lcd_values[0] = round(random.uniform(0, 3), 1)  # TSU Level Normal
        lcd_values[3] = round(random.uniform(0, 3), 1)  # eDMCR Level %
        
        for i in range(6, 12):
            lcd_values[i] = round(random.uniform(50.0, 52.0), 2) # Busbar & WIT Temp
            
        for i in range(12, 15):
            lcd_values[i] = round(random.uniform(225.0, 230.0), 2) # V Phase-Neutral
        for i in range(15, 18):
            lcd_values[i] = round(lcd_values[i-3] * 1.732, 2)      # V Phase-Phase
            
        for i in range(18, 21):
            lcd_values[i] = round(random.uniform(180.0, 200.0), 3) # Current
        lcd_values[21] = round(sum(lcd_values[18:21]) / 3.0, 2)    # Avg Current

    with adc_lock:
        adc_registers[0] = 3
        adc_registers[1] = int(lcd_values[1] * 100)
        adc_registers[2] = int(lcd_values[2] * 10000)

def _adc_loop(stop_event, dummy_mode):
    while not stop_event.is_set():
        if dummy_mode:
            time.sleep(0.5)
            continue
        if adc:
            try:
                analogIn3 = adc.read_adc(3, gain=2)
                analogIn2 = adc.read_adc(2, gain=2)
                oil_temp = round(((analogIn3 * 0.007630) - 50), 3) if analogIn3 >= 0 else 0
                oil_press = (analogIn2 - 6553) / 26214 if analogIn2 >= 0 else 0
                oil_temp_m = int(oil_temp * 100)
                oil_press_m = int(oil_press * 10000)

                oil_level_alarm = 1 if adc.read_adc(1, gain=2) > 25000 else 0
                oil_level_trip  = 1 if adc.read_adc(0, gain=2) > 25000 else 0
                oil_level = 1 if (oil_level_alarm or oil_level_trip) else (2 if oil_level_alarm else 3)

                with lcd_lock:
                    lcd_values[0] = oil_level
                    lcd_values[1] = round(oil_temp_m / 100, 2)
                    lcd_values[2] = round(oil_press_m / 10000, 3)
                with adc_lock:
                    adc_registers[0] = oil_level; adc_registers[1] = oil_temp_m; adc_registers[2] = oil_press_m
            except Exception: pass
        time.sleep(0.1)

def _rtu_loop(bus, stop_event, dummy_mode):
    from pymodbus.framer.rtu_framer import ModbusRtuFramer
    from pymodbus.register_read_message import ReadHoldingRegistersRequest
    framer = ModbusRtuFramer(None)
    read_jobs = [(1, 0x0000, 9), (10, 0x1300, 5)]

    while not stop_event.is_set():
        if dummy_mode:
            inject_dummy_data()
            time.sleep(1.0)
            continue
        try:
            for slave_id, start_addr, qty in read_jobs:
                req = ReadHoldingRegistersRequest(start_addr, qty)
                req.unit_id = slave_id
                res = bus.send_and_receive(framer.buildPacket(req))
                if res and len(res) >= 5 and res[1] == 0x03:
                    payload = res[3:-2]
                    if len(payload) == qty * 2:
                        regs = struct.unpack(f">{qty}H", payload)
                        with lcd_lock:
                            if slave_id == 1 and start_addr == 0x0000:
                                lcd_values[12:18] = [round(x/100.0, 2) for x in regs[0:6]]
                                lcd_values[18:21] = [round(x/1000.0, 3) for x in regs[6:9]]
                                lcd_values[21] = round(sum(lcd_values[18:21])/3.0, 2)
                            elif slave_id == 10 and start_addr == 0x1300:
                                lcd_values[3] = regs[4] * 25.0
                                lcd_values[4] = regs[2] / 10.0
                                lcd_values[5] = regs[1] / 1000.0 if 0 <= regs[1] < 65535 else 0.0
        except Exception: pass
        time.sleep(1.0)

def _json_publisher_loop(stop_event, hb_callback):
    while not stop_event.is_set():
        try:
            with lcd_lock: values = lcd_values.copy()
            payload = {
                "updated_at": time.strftime('%Y:%m:%d - %H:%M:%S', time.localtime()),
                "values": values
            }
            tmp_path = f"{GUI_DATA_FILE}.tmp"
            with open(tmp_path, "w") as f: json.dump(payload, f)
            os.replace(tmp_path, GUI_DATA_FILE)
            if hb_callback: hb_callback(time.time())
        except Exception: pass
        time.sleep(0.5)

def start_data_handler_engine(serial_cfg, dummy_mode, stop_event, hb_callback=None):
    oled_init()
    bus = None if dummy_mode else SerialBus(serial_cfg)
    
    if dummy_mode:
        logging.warning("=== SYSTEM RUNNING IN DUMMY MODE ===")
        print("[WARN ] === SYSTEM RUNNING IN DUMMY / SIMULATION MODE ===")
        oled_print(" TMU MODBUS GATEWAY \n  ** DUMMY MODE ** \n SIMULATING SENSORS ")
    
    threading.Thread(target=_adc_loop, args=(stop_event, dummy_mode), daemon=True).start()
    threading.Thread(target=_rtu_loop, args=(bus, stop_event, dummy_mode), daemon=True).start()
    threading.Thread(target=_json_publisher_loop, args=(stop_event, hb_callback), daemon=True).start()
    return bus