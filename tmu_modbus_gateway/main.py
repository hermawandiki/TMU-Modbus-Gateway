import socket
import struct
import threading
import serial
import time
import json
import sys
import os
import logging

# ts = time.strftime("%Y%m%d")
# # logName = r'D:/GitHub/TMU-Modbus-Gateway/tmu_modbus_gateway/logsys/logsys-' + ts + '.log'
# logName = r'/home/pi/TMU-Modbus-Gateway/tmu_modbus_gateway/logsys/logsys-' + ts + '.log'
# logging.basicConfig(
#     filename=logName,
#     format='%(asctime)s | %(levelname)s: %(message)s',
#     level=logging.DEBUG
# )

def load_config(filename="config.json"):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_dir, filename)
        # logging.info(f"Loading config from: {config_path}")
        print(f"[INFO ] Loading config from: {config_path}")
        
        with open(config_path, "r") as f:
            config = json.load(f)
            
        host = config.get("host", "0.0.0.0")
        serial_cfg = config.get("serial_port", {})
        
        port_slave_map = {int(k): v for k, v in config.get("port_slave_map", {}).items()}
        
        # logging.info(f"Config loaded with OK")
        print(f"[INFO ] Config loaded with OK")
        return host, serial_cfg, port_slave_map
    except FileNotFoundError:
        # logging.error(f"File {filename} not found.")
        print(f"[ERROR] File {filename} not found.")    
        sys.exit(1)
    except json.JSONDecodeError:
        # logging.error(f"Format {filename} invalid.")
        print(f"[ERROR] Format {filename} invalid.")
        sys.exit(1)

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

class SerialBus:
    def __init__(self, serial_cfg: dict):
        self._lock = threading.Lock()
        self.timeout = serial_cfg.get("timeout", 1.0)
        try:
            self._ser = serial.Serial(**serial_cfg)
            # logging.info(f"Connected to {serial_cfg.get('port')} at {serial_cfg.get('baudrate')}")
            print(f"[INFO ] Connected to {serial_cfg.get('port')} at {serial_cfg.get('baudrate')}")
        except Exception as e:
            # logging.error(f"Failed to open serial: {e}")
            print(f"[ERROR] Failed to open serial: {e}")    
            self._ser = None

    def send_and_receive(self, request: bytes) -> bytes:
        if not self._ser: return b""
        
        with self._lock:
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
            except Exception:
                return b""

def handle_client(conn: socket.socket, addr, port: int, slave_id: int, bus: SerialBus):
    # logging.info(f"Connected to {port} -> Slave {slave_id} from {addr[0]}:{addr[1]}")
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
                # logging.error(f"{rtu_res.hex(' ')}" if rtu_res else "No Response")
                print(f"[ERROR] {rtu_res.hex(' ')}" if rtu_res else "[ERROR] No Response")
    except ConnectionResetError:
        # logging.warning(f" Connection reset by {addr[0]}:{addr[1]}")
        print(f"[WARN ] Connection reset by {addr[0]}:{addr[1]}")
    except Exception: pass
    finally:
        conn.close()
        # logging.info(f"Disconnected Port {port} from {addr[0]}:{addr[1]}")
        print(f"[INFO ] Disconnected Port {port} from {addr[0]}:{addr[1]}")

def start_listener(host: str, port: int, slave_id: int, bus: SerialBus):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)

    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr, port, slave_id, bus), daemon=True).start()

def main():
    # logging.info("=== TMU Modbus Gateway ===")
    print("=== TMU Modbus Gateway ===")
    host, serial_cfg, port_slave_map = load_config("config.json")
    bus = SerialBus(serial_cfg)

    for port, slave_id in port_slave_map.items():
        threading.Thread(target=start_listener, args=(host, port, slave_id, bus), daemon=True).start()
        # logging.info(f"Ready listening on Port {port} for Slave ID {slave_id}")
        print(f"[INFO ] Ready listening on Port {port} for Slave ID {slave_id}")

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        # logging.info("Gateway Stopped.")
        print(f"[INFO ] Gateway Stopped.")

if __name__ == "__main__":
    main()