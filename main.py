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
import random
import Adafruit_ADS1x15
import smbus2
from PIL import Image, ImageDraw, ImageFont

adc = Adafruit_ADS1x15.ADS1115(address=0x48, busnum=1)

adc_channels = 4
adc_registers = [0] * adc_channels
adc_lock = threading.Lock()
global_port_map = {}
gui_process = None
GUI_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui_data.json")

GUI_PHYSICAL_KEYS = [
    "Oil Level",
    "Oil Temperature",
    "Oil Pressure",
    "Bus U Temperature",
    "Bus V Temperature",
    "Bus W Temperature",
    "WIT U Temperature",
    "WIT V Temperature",
    "WIT W Temperature",
]

GUI_ELECTRICAL_KEYS = [
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

def cmd(c):
	bus.write_byte_data(I2C_ADDR, 0x00, c)
	
def initOled():
	for c in [0xAE, 0x00, 0x10, 0x40, 0x81, 0xCF, 0xA1, 0xC8, 0xA6,
			  0xA8, 0x3F, 0xD3, 0x00, 0xD5, 0x80, 0xD9, 0xF1, 0xDA,
			  0x12, 0xDB, 0x40, 0x20, 0x00, 0x8D, 0x14, 0xAF]:
		cmd(c)

def show(image):
	image = image.rotate(180)
	cmd(0x21); cmd(0); cmd(127)
	cmd(0x22); cmd(0); cmd(7)
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

def showOled(teks: str):
	try:
		font = Image.truetype("/usr/share/fonts/truetype/dejavu/DeJaVuSansMono.ttf", 10)
	except:
		font = ImageFont.load_default()
	
	img = Image.new("1", (128, 64))
	draw = ImageDraw.Draw(img)
	
	for i, row in enumerate(teks.splitlines()):
		draw.text((0, i * 12), row, font=font, fill=255)
	show(img)
    
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
            
            with adc_lock:
                oil_temp  = round(((analogIn3 * 0.007630) - 50), 3)
                oil_press = (analogIn2 - 6553) / 26214 
                
                oil_temp_m = int(oil_temp * 100) if oil_temp >= 0 else 0
                oil_press_m = int(oil_press * 10000) if oil_press >= 0 else 0
                
                adc_registers[0] = oil_temp_m
                adc_registers[1] = oil_press_m
            time.sleep(0.05)
        except Exception as e:
            logging.error(f"ADC Handler error: {e}")
            print(f"[ERROR] ADC Handler error: {e}")
            time.sleep(2)

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
    with adc_lock:
        oil_temp = adc_registers[0] / 100.0
        oil_press = adc_registers[1] / 10000.0

    bus_u_temp = round(random.uniform(40.0, 65.0), 1)
    bus_v_temp = round(random.uniform(40.0, 65.0), 1)
    bus_w_temp = round(random.uniform(40.0, 65.0), 1)
    wit_u_temp = round(random.uniform(45.0, 80.0), 1)
    wit_v_temp = round(random.uniform(45.0, 80.0), 1)
    wit_w_temp = round(random.uniform(45.0, 80.0), 1)

    u_n = round(random.uniform(215.0, 235.0), 1)
    v_n = round(random.uniform(215.0, 235.0), 1)
    w_n = round(random.uniform(215.0, 235.0), 1)

    u_v = round(u_n + v_n, 1)
    v_w = round(v_n + w_n, 1)
    u_w = round(u_n + w_n, 1)

    i_u = round(random.uniform(10.0, 50.0), 2)
    i_v = round(random.uniform(10.0, 50.0), 2)
    i_w = round(random.uniform(10.0, 50.0), 2)
    i_avg = round((i_u + i_v + i_w) / 3.0, 2)

    values = {
        "Oil Level": round(random.uniform(20.0, 100.0), 1),
        "Oil Temperature": round(oil_temp, 2),
        "Oil Pressure": round(oil_press, 3),
        "Bus U Temperature": bus_u_temp,
        "Bus V Temperature": bus_v_temp,
        "Bus W Temperature": bus_w_temp,
        "WIT U Temperature": wit_u_temp,
        "WIT V Temperature": wit_v_temp,
        "WIT W Temperature": wit_w_temp,
        "U-N Phase Voltage": u_n,
        "V-N Phase Voltage": v_n,
        "W-N Phase Voltage": w_n,
        "U-V Phase Voltage": u_v,
        "V-W Phase Voltage": v_w,
        "U-W Phase Voltage": u_w,
        "U Phase Current": i_u,
        "V Phase Current": i_v,
        "W Phase Current": i_w,
        "Average Current": i_avg,
    }

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

    threading.Thread(target=gui_data_publisher, daemon=True).start()
    start_gui_process()
    bus = SerialBus(serial_cfg)
    
    adc_handler_started = False
    initOled()
    
    textFormat = "\n       ".join([f"{k} -> {v}" for k, v in global_port_map.items()])
    showOled(f"""\
	 TMU MODBUS GATEWAY 
	IP   : 192.168.4.200
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

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        logging.info("Gateway Stopped.")
        print(f"[INFO ] Gateway Stopped.\n\n")
    finally:
        stop_gui_process()

if __name__ == "__main__":
    main()
