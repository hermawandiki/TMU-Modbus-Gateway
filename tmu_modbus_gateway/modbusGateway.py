import socket
import serial
import threading
import time
import datetime
import os
import sys
import logging
import queue
import selectors
import struct
import random

from toolboxTMU import initTkinter
CONFIG = {
    "TCP_HOST": "0.0.0.0",
    "SERIAL_PORT": "/dev/ttyS0",
    "BAUDRATE": 9600,
    "TIMEOUT": 1.0,
    "PORT_MAPPING_RS485": {
        502: 1, 
        503: 2, 
        504: 3
    },
    "PORT_ADC": 505
}

ts = time.strftime("%Y%m%d")
logging.basicConfig(
    filename=f'D:/tmu_modbus_gateway/log/syslog-{ts}.log', 
    format='%(asctime)s | %(levelname)s: %(message)s', 
    level=logging.DEBUG
)

try:
    os.chdir('D:/tmu_modbus_gateway/')
except:
    pass

def crc16_pure(data: bytes) -> int:
    """Menghitung nilai CRC16 Modbus standar menggunakan bitwise Python."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc

def tcp_to_rtu(tcp_frame: bytes, slave_id: int) -> bytes:
    if len(tcp_frame) < 8: 
        raise ValueError("Frame TCP terlalu pendek")
    rtu_body = bytes([slave_id]) + tcp_frame[7:]
    
    # Hitung CRC dengan fungsi mandiri
    crc_value = crc16_pure(rtu_body)
    return rtu_body + struct.pack("<H", crc_value)

def rtu_to_tcp(rtu_frame: bytes, transaction_id: bytes) -> bytes:
    if len(rtu_frame) < 4: 
        raise ValueError("Frame RTU terlalu pendek")
    slave_id = rtu_frame[0]
    pdu = rtu_frame[1:-2]
    return transaction_id + b"\x00\x00" + struct.pack(">H", len(pdu)+1) + bytes([slave_id]) + pdu

def verify_crc(rtu_frame: bytes) -> bool:
    if len(rtu_frame) < 3: 
        return False
    body = rtu_frame[:-2]
    crc_terima = struct.unpack("<H", rtu_frame[-2:])[0]
    
    # Validasi menggunakan fungsi mandiri
    return crc16_pure(body) == crc_terima

def read_hardware_adc() -> list:
    """Ganti dengan fungsi pembacaan library sensor ADC Anda"""
    return [random.randint(0, 4095) for _ in range(4)]

def process_adc_request(tcp_req: bytes) -> bytes:
    if len(tcp_req) < 12: 
        raise ValueError("Request ADC tidak lengkap")
    tid, uid, fc = tcp_req[0:2], tcp_req[6], tcp_req[7]

    if fc not in (0x03, 0x04): 
        return tid + b"\x00\x00\x00\x03" + bytes([uid, fc | 0x80, 0x01])

    data_bytes = b"".join(struct.pack(">H", int(v)) for v in read_hardware_adc())
    return tid + b"\x00\x00" + struct.pack(">H", 3 + len(data_bytes)) + bytes([uid, fc, len(data_bytes)]) + data_bytes


# ============================================================================
# 3. THREAD KONTROLER RS485
# ============================================================================
class SerialWorker:
    def __init__(self, req_queue, log_cb):
        self.req_queue = req_queue
        self.log_cb = log_cb
        self.running = False
        self.ser = None

    def run(self):
        self.running = True
        try:
            self.ser = serial.Serial(
                port=CONFIG["SERIAL_PORT"], baudrate=CONFIG["BAUDRATE"], timeout=CONFIG["TIMEOUT"]
            )
            self.log_cb('D', f"RS485 Terhubung: {CONFIG['SERIAL_PORT']}")
        except Exception as e:
            self.log_cb('D', f"Gagal buka Serial: {e}")
            self.running = False
            return

        while self.running:
            try: task = self.req_queue.get(timeout=1.0)
            except queue.Empty: continue

            try:
                self.ser.reset_input_buffer()
                self.ser.write(task["rtu_request"])
                
                res = b""
                start_t = time.time()
                while time.time() - start_t < CONFIG["TIMEOUT"]:
                    chunk = self.ser.read(256)
                    if chunk:
                        res += chunk
                        if len(res) >= 5: break
                    else: break

                if res and verify_crc(res):
                    task["conn"].sendall(rtu_to_tcp(res, task["transaction_id"]))
                else:
                    if len(task["rtu_request"]) > 1:
                        err_pdu = bytes([task["rtu_request"][1] | 0x80, 0x0B])
                        task["conn"].sendall(task["transaction_id"] + b"\x00\x00\x00\x03" + bytes([task["slave_id"]]) + err_pdu)
            except Exception as e:
                self.log_cb('D', f"Error RS485: {e}")
            finally:
                self.req_queue.task_done()

    def stop(self):
        self.running = False
        if self.ser: self.ser.close()


# ============================================================================
# 4. THREAD MULTIPLEXER JARINGAN TCP (SCADA)
# ============================================================================
class TCPMultiplexer:
    def __init__(self, req_queue, log_cb):
        self.req_queue = req_queue
        self.log_cb = log_cb
        self.running = False
        self.sel = selectors.DefaultSelector()

    def _bind_port(self, port, identity):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((CONFIG["TCP_HOST"], port))
        sock.listen(5)
        sock.setblocking(False)
        self.sel.register(sock, selectors.EVENT_READ, data=("LISTENER", identity))
        self.log_cb('D', f"Listen Port {port} -> {identity}")

    def run(self):
        self.running = True
        for port, slave_id in CONFIG["PORT_MAPPING_RS485"].items():
            self._bind_port(port, f"Slave ID {slave_id}")
        self._bind_port(CONFIG["PORT_ADC"], 'ADC Lokal')

        while self.running:
            events = self.sel.select(timeout=1.0)
            for key, mask in events:
                sock = key.fileobj
                sock_type, identity = key.data

                if sock_type == "LISTENER":
                    conn, addr = sock.accept()
                    conn.setblocking(False)
                    self.sel.register(conn, selectors.EVENT_READ, data=("CLIENT", identity))
                
                elif sock_type == "CLIENT":
                    try:
                        data = sock.recv(1024)
                        if data:
                            if identity == 'ADC Lokal':
                                sock.sendall(process_adc_request(data))
                            else:
                                # Ekstrak angka ID (misal dari string "Slave ID 2" jadi integer 2)
                                slave_id = int(identity.split()[-1])
                                self.req_queue.put({
                                    "conn": sock, "transaction_id": data[0:2], 
                                    "slave_id": slave_id, "rtu_request": tcp_to_rtu(data, slave_id)
                                })
                        else:
                            self._close_client(sock)
                    except Exception:
                        self._close_client(sock)

    def _close_client(self, sock):
        try: self.sel.unregister(sock)
        except: pass
        sock.close()

    def stop(self):
        self.running = False
        for key in list(self.sel.get_map().values()):
            key.fileobj.close()
        self.sel.close()


# ============================================================================
# 5. APP MANAGER (Tkinter GUI & Watchdog)
# ============================================================================
class AppManager:
    def __init__(self):
        logging.info("Memulai Hibrida Modbus Gateway Manager")
        self.gui_log_queue = queue.Queue()
        self.request_queue = queue.Queue()
        
        self.progStat = False
        self.lastHB = "init"
        self.debugMsg = ""
        
        self.tcp_worker = None
        self.ser_worker = None

        self.main_screen = initTkinter()
        self.main_screen.restartBtn["command"] = self.restart_all
        self.main_screen.stopBtn1["command"] = self.toggle_gateway
        
        # Sembunyikan tombol yang tidak terpakai
        try:
            self.main_screen.stopBtn2["state"] = 'disabled'
            self.main_screen.stopBtn3["state"] = 'disabled'
        except: pass

        self.start_gateway()
        self.process_queue_logs()
        self.update_tk()
        
        # Thread Heartbeat Internal
        threading.Thread(target=self.internal_heartbeat, daemon=True).start()
        
        # Blocking Mainloop Tkinter
        self.main_screen.screen.mainloop()

    def log_callback(self, msg_type, msg):
        self.gui_log_queue.put((msg_type, msg))

    def internal_heartbeat(self):
        while True:
            if self.progStat:
                now = datetime.datetime.now().strftime("%H:%M:%S")
                self.log_callback('T', now)
            time.sleep(1)

    def start_gateway(self):
        if self.progStat: return
        self.progStat = True
        self.main_screen.stopBtn1["text"] = "Stop Gateway"
        
        self.ser_worker = SerialWorker(self.request_queue, self.log_callback)
        self.tcp_worker = TCPMultiplexer(self.request_queue, self.log_callback)

        threading.Thread(target=self.ser_worker.run, daemon=True, name="Th-Serial").start()
        threading.Thread(target=self.tcp_worker.run, daemon=True, name="Th-TCP").start()
        self.log_callback('D', "Sistem Berjalan Aktif.")

    def stop_gateway(self):
        if not self.progStat: return
        self.progStat = False
        self.main_screen.stopBtn1["text"] = "Start Gateway"
        self.log_callback('D', "Menghentikan jalur komunikasi...")
        if self.ser_worker: self.ser_worker.stop()
        if self.tcp_worker: self.tcp_worker.stop()

    def toggle_gateway(self):
        if self.progStat: self.stop_gateway()
        else: self.start_gateway()

    def restart_all(self):
        self.stop_gateway()
        time.sleep(1)
        # Eksekusi ulang file script ini dengan aman
        os.execv(sys.executable, [sys.executable, sys.argv[0]] + sys.argv[1:])

    def process_queue_logs(self):
        while not self.gui_log_queue.empty():
            try:
                msg_type, message = self.gui_log_queue.get_nowait()
                if msg_type == 'T':
                    self.lastHB = message
                elif msg_type == 'D':
                    self.debugMsg = message
                    logging.debug(message)
            except queue.Empty: break
                
        self.main_screen.screen.after(100, self.process_queue_logs)

    def update_tk(self):
        try:
            self.main_screen.lastHB1Lbl['text'] = self.lastHB
            self.main_screen.debug1Lbl['text'] = self.debugMsg
            self.main_screen.prog1Lbl['text'] = "Running" if self.progStat else "Stop"
        except: pass
        self.main_screen.screen.after(1000, self.update_tk)

if __name__ == "__main__":
    try:
        AppManager()
    except KeyboardInterrupt:
        logging.info("Dihentikan secara manual (Ctrl+C).")
        sys.exit(0)
    except Exception as e:
        logging.critical(f"Kesalahan Fatal Utama: {e}")
        sys.exit(1)