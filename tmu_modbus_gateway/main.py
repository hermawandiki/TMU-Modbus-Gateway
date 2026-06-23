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
from toolboxTMU import initTkinter

CONFIG = {
    "TCP_HOST": "0.0.0.0",
    "SERIAL_PORT": "/dev/ttyS0",
    "BAUDRATE": 9600,
    "TIMEOUT": 1.0,
    "PORT_MAPPING": {
        502: 1,
        503: 2,
        504: 3,
    }
}

ts = time.strftime("%Y%m%d")
# logName = r'/home/pi/tmu-v2-smart/assets/sysdata-test/syslog-' + ts + '.log'
logName = r'D:/GitHub/TMU-Modbus-Gateway/tmu_modbus_gateway/log/syslog-' + ts + '.log'
logging.basicConfig(
    filename=logName,
    format='%(asctime)s | %(levelname)s: %(message)s',
    level=logging.DEBUG
)

os.chdir('D:/GitHub/TMU-Modbus-Gateway/tmu_modbus_gateway/')

def crc16_pure(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if (crc & 0x0001):
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc

def tcp_to_rtu(tcp_frame: bytes, slave_id: int) -> bytes:
    if len(tcp_frame) < 8: 
        logging.error("TCP frame is too short to be a valid Modbus TCP frame.")
        raise ValueError("TCP frame is too short to be a valid Modbus TCP frame.")
    rtu_body = bytes([slave_id]) + tcp_frame[7:]
    
    crc_value = crc16_pure(rtu_body)
    return rtu_body + struct.pack("<H", crc_value)

def rtu_to_tcp(rtu_frame: bytes, transaction_id: bytes) -> bytes:
    if len(rtu_frame) < 4: 
        logging.error("Frame is too short to be a valid Modbus RTU frame.")
        raise ValueError("Frame is too short to be a valid Modbus RTU frame.")
    slave_id = rtu_frame[0]
    pdu = rtu_frame[1:-2]
    return transaction_id + b"\x00\x00" + struct.pack(">H", len(pdu)+1) + bytes([slave_id]) + pdu

def verify_crc(rtu_frame: bytes) -> bool:
    if len(rtu_frame) < 3: 
        logging.error("Frame is too short to be a valid Modbus RTU frame.")
        return False
    body = rtu_frame[:-2]
    crc_received = struct.unpack("<H", rtu_frame[-2:])[0]
    
    return crc16_pure(body) == crc_received

class SerialWorker:
    def __init__(self, req_queue, log_cb):
        self.req_queue = req_queue
        self.log_cb = log_cb
        self.running = True
        self.ser = None

    def run(self):
        self.running = True
        try:
            self.ser = serial.Serial(
                port=CONFIG["SERIAL_PORT"],
                baudrate=CONFIG["BAUDRATE"],
                timeout=CONFIG["TIMEOUT"]
            )
            logging.info(f"Serial port {CONFIG['SERIAL_PORT']} opened successfully.")
            self.log_cb(f"Serial port {CONFIG['SERIAL_PORT']} opened successfully.")
        except Exception as e:
            logging.error(f"Failed to open serial port {CONFIG['SERIAL_PORT']}: {e}")
            self.log_cb(f"Failed to open serial port {CONFIG['SERIAL_PORT']}: {e}")
            self.running = False
            return
    
        while self.running:
            try:
                task = self.req_queue.get(timeout=1)
            except queue.Empty:
                continue
            
            try:
                self.ser.reset_input_buffer()
                self.ser.write(task['rtu_request'])

                frame_data = b""
                start_time = time.time()
                while time.time() - start_time < CONFIG["TIMEOUT"]:
                    chunk = self.ser.read(256)
                    if chunk:
                        frame_data += chunk
                        if len(frame_data) >= 5:
                            break
                        else:
                            break

                if frame_data and verify_crc(frame_data):
                    task["conn"].sendall(rtu_to_tcp(frame_data, task["transaction_id"]))
                else:
                    if len(task["rtu_request"]) > 1:
                        error_pdu = bytes([task["rtu_request"][1] | 0x80, 0x0B])
                        task["conn"].sendall(task["transaction_id"] + b"\x00\x00\x00\x03" + bytes([task["rtu_request"][0]]) + error_pdu)
            except Exception as e:
                logging.error(f"Error processing request: {e}")
            finally:
                    self.req_queue.task_done()

    def stop(self):
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()

class TCPServer:
    def __init__(self, req_queue, log_cb):
        self.req_queue = req_queue
        self.log_cb = log_cb
        self.running = True
        self.sel = selectors.DefaultSelector()

    def _bind_port(self, port, identity):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((CONFIG["TCP_HOST"], port))
        sock.listen(5)
        sock.setblocking(False)
        self.sel.register(sock, selectors.EVENT_READ, data=("LISTENER", identity))
        logging.info(f"Listening on TCP port {port} for slave ID {identity}.")
        # self.log_cb(f"Listening on TCP port {port} for slave ID {identity}.")
    
    def run(self):
        self.running = True
        for port, slave_id in CONFIG["PORT_MAPPING"].items():
            self._bind_port(port, f"Slave ID {slave_id}")
        
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
                            slave_id = int(identity.split()[-1])
                            self.req_queue.put({
                                "conn": sock, "transaction_id": data[:2],
                                "slave_id": slave_id, "rtu_request": tcp_to_rtu(data, slave_id)
                            })
                        else:
                            self._close_client(sock)
                    except Exception as e:
                        self._close_client(sock)
                
    def _close_client(self, sock):
        try: self.sel.unregister(sock)
        except: pass
        sock.close()

    def stop(self):
        self.running = False
        for key in self.sel.get_map().values():
            key.fileobj.close()
        self.sel.close()

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
        
        try:
            self.main_screen.stopBtn2["state"] = 'disabled'
            self.main_screen.stopBtn3["state"] = 'disabled'
        except: pass

        self.start_gateway()
        self.process_queue_logs()
        self.update_tk()
        
        threading.Thread(target=self.internal_heartbeat, daemon=True).start()
        
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
        self.main_screen.stopBtn1["text"] = "Stop"
        
        self.ser_worker = SerialWorker(self.request_queue, self.log_callback)
        self.tcp_worker = TCPServer(self.request_queue, self.log_callback)

        threading.Thread(target=self.ser_worker.run, daemon=True, name="Th-Serial").start()
        threading.Thread(target=self.tcp_worker.run, daemon=True, name="Th-TCP").start()
        self.log_callback('D', "Sistem Berjalan Aktif.")

    def stop_gateway(self):
        if not self.progStat: return
        self.progStat = False
        self.main_screen.stopBtn1["text"] = "Start"
        self.log_callback('D', "Menghentikan jalur komunikasi...")
        if self.ser_worker: self.ser_worker.stop()
        if self.tcp_worker: self.tcp_worker.stop()

    def toggle_gateway(self):
        if self.progStat: self.stop_gateway()
        else: self.start_gateway()

    def restart_all(self):
        self.stop_gateway()
        time.sleep(1)
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