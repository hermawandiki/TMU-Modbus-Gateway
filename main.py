import socket
import struct
import threading
import subprocess
import serial
import time
import json
import sys
import os
import logging
import Adafruit_ADS1x15
import smbus2
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont

adc = Adafruit_ADS1x15.ADS1115(address=0x48, busnum=1)

GPIO.setmode(GPIO.BCM)
GPIO.setup(13, GPIO.IN)
GPIO.setup(22, GPIO.IN)
GPIO.setup(17, GPIO.IN)
GPIO.setup(27, GPIO.IN)

adc_channels = 4
adc_registers = [0] * adc_channels
adc_lock = threading.Lock()
lcd_fields = [
    "TSU Oil Level",
    "TSU Oil Temperature",
    "TSU Oil Pressure",
    "eDMCR Oil Level",
    "eDMCR Oil Temperature",
    "eDMCR Oil Pressure",
    "Bus U Temperature",
    "Bus V Temperature",
    "Bus W Temperature",
    "WIT U Temperature",
    "WIT V Temperature",
    "WIT W Temperature",
    "U-N Phase Voltage",
    "V-N Phase Voltage",
    "W-N Phase Voltage",
    "U-V Phase Voltage",
    "V-W Phase Voltage",
    "U-W Phase Voltage",
    "U Phase Current",
    "V Phase Current",
    "W Phase Current",
    "Average Current",
]
lcd_values = [0.0] * len(lcd_fields)
lcd_lock = threading.Lock()
global_port_map = {}
gui_process = None
GUI_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui_data.json")

I2C_BUS = 1
I2C_ADDR = 0x3C
bus = smbus2.SMBus(I2C_BUS)

ts = time.strftime("%Y%m%d")
# logName = r'D:/GitHub/TMU-Modbus-Gateway/tmu_modbus_gateway/logsys/logsys-' + ts + '.log'
logName = r'/home/pi/TMU-Modbus-Gateway/logsys/logsys-' + ts + '.log'
logging.basicConfig(
    filename=logName,
    format='%(asctime)s | %(levelname)s: %(message)s',
    level=logging.INFO,
)

def oled_cmd(cmd):
    bus.write_byte_data(I2C_ADDR, 0x00, cmd)

def oled_init():
	for c in [0xAE, 0x00, 0x10, 0x40, 0x81, 0xCF, 0xA1, 0xC8, 0xA6,
			  0xA8, 0x3F, 0xD3, 0x00, 0xD5, 0x80, 0xD9, 0xF1, 0xDA,
			  0x12, 0xDB, 0x40, 0x20, 0x00, 0x8D, 0x14, 0xAF]:
		oled_cmd(c)

def oled_show(image):
	image = image.rotate(180)
	oled_cmd(0x21); oled_cmd(0); oled_cmd(127)
	oled_cmd(0x22); oled_cmd(0); oled_cmd(7)
	pix = list(image.getdata())
	buf = []
	for page in range(8):
		for col in range(128):
			byte = 0
			for bit in range(8):
				if pix[(page * 8 + bit) * 128 + col]:
					byte |= (1 << bit)
			buf.append(byte)
	for i in range(0, len(buf), 16):
		bus.write_i2c_block_data(I2C_ADDR, 0x40, buf[i:i+16])

def oled_print(teks: str):
	try:
		font = Image.truetype("/usr/share/fonts/truetype/dejavu/DeJaVuSansMono.ttf", 10)
	except:
		font = ImageFont.load_default()
	
	img = Image.new("1", (128, 64))
	draw = ImageDraw.Draw(img)
	
	for i, row in enumerate(teks.splitlines()):
		draw.text((0, i * 12), row, font=font, fill=255)
	oled_show(img)
    
def load_config(filename="config.json"):
    global global_port_map
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_dir, filename)
        logging.info(f"Loading config from: {config_path}")
        print(f"[INFO ] Loading config from: {config_path}")
        
        with open(config_path, "r") as f:
            config = json.load(f)
            
        host = config.get("host", "0.0.0.0")
        serial_cfg = config.get("serial_port", {})
        
        port_slave_map = {int(k): v for k, v in config.get("port_slave_map", {}).items()}
        global_port_map = port_slave_map
        
        logging.info(f"Config loaded with OK")
        print(f"[INFO ] Config loaded with OK")
        return host, serial_cfg, port_slave_map
    except FileNotFoundError:
        logging.error(f"File {filename} not found.")
        print(f"[ERROR] File {filename} not found.")    
        sys.exit(1)
    except json.JSONDecodeError:
        logging.error(f"Format {filename} invalid.")
        print(f"[ERROR] Format {filename} invalid.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"OLED crashed of HW not found: {e}")
        print(f"[ERROR] OLED crashed or HW not found: {e}")

def calculate_crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return struct.pack("<H", crc)

def validate_crc16(frame: bytes) -> bool:
    return len(frame) >= 3 and calculate_crc16(frame[:-2]) == frame[-2:]

def tcp2rtu(tcp_frame: bytes, slave_id: int) -> bytes:
    rtu_body = bytes([slave_id]) + tcp_frame[7:]
    return rtu_body + calculate_crc16(rtu_body)

def rtu2tcp(rtu_frame: bytes, tx_id: bytes, unit_id: int) -> bytes:
    pdu = rtu_frame[1:-2]
    return tx_id + b"\x00\x00" + struct.pack(">H", len(pdu) + 1) + bytes([unit_id]) + pdu

def adc_handler():
    while True:
        try:
            analogIn3 = adc.read_adc(3, gain=2)
            analogIn2 = adc.read_adc(2, gain=2)
            
            # pakai ini kalau transmitter mode minus
            # oil_temp = round(((analogIn3 * 0.009573) - 112.5), 3) if analogIn3 >= 0 else 0 
            # pakai ini kalau transmitter mode plus
            oil_temp = round(((analogIn3 * 0.007630) - 50), 3) if analogIn3 >= 0 else 0
            oil_press = (analogIn2 - 6553) / 26214 if analogIn2 >= 0 else 0

            oil_temp_m = int(oil_temp * 100)
            oil_press_m = int(oil_press * 10000)

            oil_level_alarm = 1 if adc.read_adc(1, gain=2) > 25000 else 0
            oil_level_trip  = 1 if adc.read_adc(0, gain=2) > 25000 else 0
            if (oil_level_alarm and oil_level_trip) or oil_level_trip:
                oil_level = 1
            elif oil_level_alarm:
                oil_level = 2
            elif not oil_level_alarm and not oil_level_trip:
                oil_level = 3

            with lcd_lock:
                lcd_values[0] = oil_level    # Oil Level Status
                lcd_values[1] = round(oil_temp_m / 100, 2) # Oil Temperature
                lcd_values[2] = round(oil_press_m / 10000, 3) # Oil Pressure

            with adc_lock:
                adc_registers[0] = oil_level
                adc_registers[1] = oil_temp_m
                adc_registers[2] = oil_press_m
            time.sleep(0.05)
        except Exception as e:
            logging.error(f"ADC Handler error: {e}")
            print(f"[ERROR] ADC Handler error: {e}")
            time.sleep(2)

def lcd_data_worker(bus: "SerialBus"):
    from pymodbus.framer.rtu_framer import ModbusRtuFramer
    from pymodbus.register_read_message import ReadHoldingRegistersRequest

    framer = ModbusRtuFramer(None)
    read_jobs = [(2, 0x0000, 9), (10, 0x1300, 5)]

    while True:
        try:
            for slave_id, start_addr, qty in read_jobs:
                request = ReadHoldingRegistersRequest(start_addr, qty)
                request.unit_id = slave_id
                request_frame = framer.buildPacket(request)
                response = bus.send_and_receive(request_frame)

                if not response or len(response) < 5:
                    continue
                if response[0] != slave_id or response[1] != 0x03:
                    continue
                if not validate_crc16(response):
                    continue

                byte_count = response[2]
                payload = response[3:-2]
                if byte_count != qty * 2 or len(payload) != qty * 2:
                    continue

                registers = struct.unpack(f">{qty}H", payload)

                with lcd_lock:
                    if slave_id == 2 and start_addr == 0x0000:
                        lcd_values[12] = round(registers[0] / 100.0, 2) # U-N Phase Voltage
                        lcd_values[13] = round(registers[1] / 100.0, 2) # V-N Phase Voltage
                        lcd_values[14] = round(registers[2] / 100.0, 2) # W-N Phase Voltage
                        lcd_values[15] = round(registers[3] / 100.0, 2) # U-V Phase Voltage
                        lcd_values[16] = round(registers[4] / 100.0, 2) # V-W Phase Voltage
                        lcd_values[17] = round(registers[5] / 100.0, 2) # U-W Phase Voltage
                        lcd_values[18] = round(registers[6] / 1000.0, 3) # U Phase Current
                        lcd_values[19] = round(registers[7] / 1000.0, 3) # V Phase Current 
                        lcd_values[20] = round(registers[8] / 1000.0, 3) # W Phase Current
                        lcd_values[21] = round((lcd_values[18] + lcd_values[19] + lcd_values[20]) / 3.0, 2) # Average Current
                    elif slave_id == 10 and start_addr == 0x1300:
                        lcd_values[3] = registers[4] * 25.0 # Oil Level Measurement
                        lcd_values[4] = registers[2] / 10.0 # Oil Temperature Measurement
                        lcd_values[5] = registers[1] / 1000.0 if registers[1] >= 0 and registers[1] < 65535 else 0.00 # Oil Pressure Measurement

                time.sleep(1)
        except Exception as e:
            logging.error(f"LCD worker error: {e}")
            print(f"[ERROR] LCD worker error: {e}")
        time.sleep(1)

def handle_adc_client(conn: socket.socket, addr, port: int):
    logging.info(f"Connected to ADC on port {port} from {addr[0]}:{addr[1]}")
    print(f"[INFO ] Connected to ADC on port {port} from {addr[0]}:{addr[1]}")
    try:
        while True:
            tcp_req = conn.recv(1024)
            if not tcp_req: break
            if len(tcp_req) < 12: continue

            tx_id, unit_id, fc = tcp_req[0:2], tcp_req[6], tcp_req[7]
            
            if fc in (0x03, 0x04):
                start_addr, qty = struct.unpack(">HH", tcp_req[8:12])
                
                with adc_lock:
                    if start_addr + qty <= adc_channels:
                        byte_count = qty * 2
                        data_bytes = b"".join(struct.pack(">h", int(adc_registers[i])) for i in range(start_addr, start_addr + qty))
                        
                        res_length = 3 + byte_count
                        response = tx_id + b"\x00\x00" + struct.pack("<H", res_length) + bytes([unit_id, fc, byte_count]) + data_bytes
                        conn.sendall(response)
                    else:
                        exc = bytes([fc | 0x80, 0x02])
                        conn.sendall(tx_id + b"\x00\x00" + struct.pack(">H", 3) + bytes([unit_id]) + exc)
            else:
                exc = bytes([fc | 0x80, 0x01])
                conn.sendall(tx_id + b"\x00\x00" + struct.pack("<H", 3) + bytes([unit_id]) + exc)
                
    except ConnectionResetError:
        logging.warning(f" Connection reset by {addr[0]}:{addr[1]}")
        print(f"[WARN ] Connection reset by {addr[0]}:{addr[1]}")
    except Exception as e:
        logging.error(f"Unexpected error on ADC: {e}")
        print(f"[ERROR] Unexpected error on ADC: {e}")
    finally:
        conn.close()
        logging.info(f"Disconnected ADC Port {port} from {addr[0]}:{addr[1]}")
        print(f"[INFO ] Disconnected ADC Port {port} from {addr[0]}:{addr[1]}")

def start_adc_listener(host: str, port: int):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_adc_client, args=(conn, addr, port), daemon=True).start()

class SerialBus:
    def __init__(self, serial_cfg: dict):
        self._lock = threading.Lock()
        self.serial_cfg = serial_cfg
        self.timeout = serial_cfg.get("timeout", 1.0)
        self._ser = None
        self.connect()
    
    def connect(self):
        try:
            if self._ser is not None:
                self._ser.close()
        except Exception:
            pass
        
        try:
            self._ser = serial.Serial(**self.serial_cfg)
            logging.info(f"Connected to {self.serial_cfg.get('port')} at {self.serial_cfg.get('baudrate')}")
            print(f"[INFO ] Connected to {self.serial_cfg.get('port')} at {self.serial_cfg.get('baudrate')}")
        except Exception as e:
            logging.error(f"Failed to open serial: {e}")
            print(f"[ERROR] Failed to open serial: {e}")    
            self._ser = None

    def send_and_receive(self, request: bytes) -> bytes:
        with self._lock:
            if self._ser is None:
                self.connect()
                if self._ser is None:
                    return b""
                    
            try:
                self._ser.reset_input_buffer()
                self._ser.write(request)
                
                response = b""
                start = time.time()
                
                while time.time() - start < self.timeout:
                    if self._ser.in_waiting:
                        response += self._ser.read(self._ser.in_waiting)
                        if len(response) >= 5 and validate_crc16(response):
                            break
                    time.sleep(0.005)
                
                return response
                
            except serial.SerialException as e:
                logging.error(f"RS485 connection lost: {e}")
                print(f"[ERROR] RS485 connection lost: {e}")
                self._ser = None
                return b""
            except OSError as e:
                logging.error(f"OS Error on serial: {e}")
                print(f"[ERROR] OS Error on serial: {e}")
                return b""
            except Exception as e:
                logging.error(f"Unexpected error on serial: {e}")
                print(f"[ERROR] Unexpected error on serial: {e}")
                return b""

def handle_client(conn: socket.socket, addr, port: int, slave_id: int, bus: SerialBus):
    logging.info(f"Connected to {port} -> Slave {slave_id} from {addr[0]}:{addr[1]}")
    print(f"[INFO ] Connected to {port} -> Slave {slave_id} from {addr[0]}:{addr[1]}")
    try:
        while True:
            tcp_req = conn.recv(1024)
            if not tcp_req: break
            if len(tcp_req) < 8: continue

            tx_id, unit_id, fc = tcp_req[0:2], tcp_req[6], tcp_req[7]

            rtu_req = tcp2rtu(tcp_req, slave_id)
            # logging.info(f"{rtu_req.hex(' ')}")
            # print(f"[REQ  ]  {rtu_req.hex(' ')}")
            rtu_res = bus.send_and_receive(rtu_req)

            if rtu_res and validate_crc16(rtu_res):
                if slave_id == 2 and fc in (0x03, 0x04):
                    start_addr, qty = struct.unpack(">HH", tcp_req[8:12])
                    payload = rtu_res[3:-2]
                    if len(payload) == qty * 2:
                        registers = struct.unpack(f">{qty}H", payload)
                        with lcd_lock:
                            if start_addr == 0x0000 and qty >= 9:
                                lcd_values[12] = round(registers[0] / 100.0, 2) # U-N Phase Voltage
                                lcd_values[13] = round(registers[1] / 100.0, 2) # V-N Phase Voltage
                                lcd_values[14] = round(registers[2] / 100.0, 2) # W-N Phase Voltage
                                lcd_values[15] = round(registers[3] / 100.0, 2) # U-V Phase Voltage
                                lcd_values[16] = round(registers[4] / 100.0, 2) # V-W Phase Voltage
                                lcd_values[17] = round(registers[5] / 100.0, 2) # U-W Phase Voltage
                                lcd_values[18] = round(registers[6] / 1000.0, 3) # U Phase Current
                                lcd_values[19] = round(registers[7] / 1000.0, 3) # V Phase Current 
                                lcd_values[20] = round(registers[8] / 1000.0, 3) # W Phase Current
                                lcd_values[21] = round((lcd_values[18] + lcd_values[19] + lcd_values[20]) / 3.0, 2) # Average Current
                if slave_id == 10 and fc in (0x03, 0x04):
                    start_addr, qty = struct.unpack(">HH", tcp_req[8:12])
                    payload = rtu_res[3:-2]
                    if len(payload) == qty * 2:
                        registers = struct.unpack(f">{qty}H", payload)
                        with lcd_lock:
                            if start_addr == 0x1300 and qty >= 5:
                                lcd_values[3] = registers[4] * 25.0 # Oil Level Measurement
                                lcd_values[4] = registers[2] / 10.0 # Oil Temperature Measurement
                                lcd_values[5] = registers[1] / 1000.0 if registers[1] >= 0 and registers[1] < 65535 else 0.00 # Oil Pressure Measurement
                conn.sendall(rtu2tcp(rtu_res, tx_id, unit_id))
                # logging.info(f"{rtu_res.hex(' ')}")
                # print(f"[RES  ]  {rtu_res.hex(' ')}")
            else:
                exc = bytes([fc | 0x80, 0x0B])
                conn.sendall(tx_id + b"\x00\x00" + struct.pack(">H", len(exc) + 1) + bytes([unit_id]) + exc)
                # logging.error(f"Respond Timeout / CRC Invalid")
                # print(f"[ERROR] Respond Timeout / CRC Invalid")
                logging.error(f"{rtu_res.hex(' ')}" if rtu_res else f"Slave ID {slave_id} No Response")
                print(f"[ERROR] {rtu_res.hex(' ')}" if rtu_res else f"[ERROR] Slave ID {slave_id} No Response")
    except ConnectionResetError:
        logging.warning(f" Connection reset by {addr[0]}:{addr[1]}")
        print(f"[WARN ] Connection reset by {addr[0]}:{addr[1]}")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        print(f"[ERROR] Unexpected error: {e}")
    finally:
        conn.close()
        logging.info(f"Disconnected Port {port} from {addr[0]}:{addr[1]}")
        print(f"[INFO ] Disconnected Port {port} from {addr[0]}:{addr[1]}")

def start_listener(host: str, port: int, slave_id: int, bus: SerialBus):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)

    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr, port, slave_id, bus), daemon=True).start()

def start_gui_process():
    global gui_process
    if gui_process is not None and gui_process.poll() is None:
        return

    gui_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui.py")
    if not os.path.exists(gui_path):
        logging.warning(f"gui.py not found at {gui_path}")
        print(f"[WARN ] gui.py not found at {gui_path}")
        return

    gui_env = os.environ.copy()
    has_display = bool(gui_env.get("DISPLAY") or gui_env.get("WAYLAND_DISPLAY"))

    if not has_display and os.path.exists("/tmp/.X11-unix/X0"):
        gui_env["DISPLAY"] = ":0"
        xauth_path = os.path.expanduser("~/.Xauthority")
        if os.path.exists(xauth_path):
            gui_env.setdefault("XAUTHORITY", xauth_path)
        has_display = True

    if not has_display:
        msg = "No active display detected. GUI not started (set DISPLAY/WAYLAND_DISPLAY first)."
        logging.warning(msg)
        print(f"[WARN ] {msg}")
        return

    try:
        gui_process = subprocess.Popen([sys.executable, gui_path], env=gui_env)
        logging.info(f"GUI started (PID: {gui_process.pid})")
        print(f"[INFO ] GUI started (PID: {gui_process.pid})")
    except Exception as e:
        logging.error(f"Failed to start GUI: {e}")
        print(f"[ERROR] Failed to start GUI: {e}")

def stop_gui_process():
    global gui_process
    if gui_process is None:
        return
    if gui_process.poll() is not None:
        gui_process = None
        return

    try:
        gui_process.terminate()
        gui_process.wait(timeout=3)
        logging.info("GUI process terminated")
        print("[INFO ] GUI process terminated")
    except Exception:
        try:
            gui_process.kill()
            logging.warning("GUI process killed")
            print("[WARN ] GUI process killed")
        except Exception as e:
            logging.error(f"Failed to stop GUI process: {e}")
            print(f"[ERROR] Failed to stop GUI process: {e}")
    finally:
        gui_process = None

def _write_gui_data(payload: dict):
    tmp_path = f"{GUI_DATA_FILE}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(payload, f)
    os.replace(tmp_path, GUI_DATA_FILE)

def build_gui_payload() -> dict:
    with lcd_lock:
        values = lcd_values.copy()

    return {
        "updated_at": time.time(),
        "values": values,
    }

def gui_data_publisher():
    while True:
        try:
            payload = build_gui_payload()
            _write_gui_data(payload)
        except Exception as e:
            logging.error(f"GUI data publisher error: {e}")
            print(f"[ERROR] GUI data publisher error: {e}")
        time.sleep(0.5)

def main():
    logging.info("\n\n\n")
    logging.info("=== TMU Modbus Gateway ===")
    print("=== TMU Modbus Gateway ===")
    host, serial_cfg, port_slave_map = load_config("config.json")

    bus = SerialBus(serial_cfg)
    threading.Thread(target=gui_data_publisher, daemon=True).start()
    threading.Thread(target=lcd_data_worker, args=(bus,), daemon=True).start()
    
    adc_handler_started = False
    oled_init()
    
    textFormat = "\n       ".join([f"{k} -> {v}" for k, v in global_port_map.items()])
    oled_print(f"""\
	 TMU MODBUS GATEWAY 
	ETH  : 192.168.4.200
	PORT : {textFormat}
	""")

    for port, target in port_slave_map.items():
        if str(target).upper() == "ADC":
            if not adc_handler_started:
                threading.Thread(target=adc_handler, daemon=True).start()
            threading.Thread(target=start_adc_listener, args=(host, port), daemon=True).start()
            logging.info(f"Ready listening on Port {port} for ADC")
            print(f"[INFO ] Ready listening on Port {port} for ADC")
        else:
            try:
                slave_id = int(target)
                threading.Thread(target=start_listener, args=(host, port, slave_id, bus), daemon=True).start()
                logging.info(f"Ready listening on Port {port} for Slave ID {slave_id}")
                print(f"[INFO ] Ready listening on Port {port} for Slave ID {slave_id}")
            except ValueError:
                logging.error(f"Invalid target '{target}' for port {port}. Must be 'ADC' or integer Slave ID")
                print(f"[ERROR] Invalid target '{target}' for port {port}. Must be 'ADC' or integer SLave ID")

    start_gui_process()

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        logging.info("Gateway Stopped.")
        print(f"[INFO ] Gateway Stopped.\n\n")
    finally:
        stop_gui_process()

if __name__ == "__main__":
    main()
