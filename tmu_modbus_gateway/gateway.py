import socket
import struct
import threading
import serial
import time

HOST = "0.0.0.0"
PORT_SLAVE_MAP = {502: 1, 503: 2, 504: 3}
SERIAL_CFG = {
    "port": "COM10", 
    "baudrate": 9600, 
    "timeout": 1.0,
}

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
    def __init__(self):
        self._lock = threading.Lock()
        try:
            self._ser = serial.Serial(**SERIAL_CFG)
            print(f"Connected to {SERIAL_CFG['port']} @ {SERIAL_CFG['baudrate']}")
        except Exception as e:
            print(f"Failed to open serial: {e}")
            self._ser = None

    def send_and_receive(self, request: bytes) -> bytes:
        if not self._ser: return b""
        
        with self._lock:
            try:
                self._ser.reset_input_buffer()
                self._ser.write(request)
                
                response = b""
                start = time.time()
                
                while time.time() - start < SERIAL_CFG["timeout"]:
                    if self._ser.in_waiting:
                        response += self._ser.read(self._ser.in_waiting)
                        if len(response) >= 5 and validate_crc16(response):
                            break
                    time.sleep(0.005)
                
                return response
            except Exception:
                return b""

def handle_client(conn: socket.socket, addr, port: int, slave_id: int, bus: SerialBus):
    print(f"\nConnected to {port} -> Slave {slave_id} from {addr[0]}:{addr[1]}")
    try:
        while True:
            tcp_req = conn.recv(1024)
            if not tcp_req: break
            if len(tcp_req) < 8: continue

            tx_id, unit_id, fc = tcp_req[0:2], tcp_req[6], tcp_req[7]

            rtu_req = tcp2rtu(tcp_req, slave_id)
            print(f"[REQ]  {rtu_req.hex(' ')}")
            rtu_res = bus.send_and_receive(rtu_req)

            if rtu_res and validate_crc16(rtu_res):
                conn.sendall(rtu2tcp(rtu_res, tx_id, unit_id))
                print(f"[OK]  {rtu_res.hex(' ')}")
            else:
                exc = bytes([fc | 0x80, 0x0B])
                conn.sendall(tx_id + b"\x00\x00" + struct.pack(">H", len(exc) + 1) + bytes([unit_id]) + exc)
                print("Respond Timeout / CRC Invalid")
            print("")
                
    except Exception: pass
    finally:
        conn.close()
        print(f"Disconnected Port {port} from {addr[0]}:{addr[1]}")

def start_listener(port: int, slave_id: int, bus: SerialBus):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, port))
    server.listen(5)

    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr, port, slave_id, bus), daemon=True).start()

def main():
    print("=== TMU Modbus Gateway ===")
    bus = SerialBus()

    for port, slave_id in PORT_SLAVE_MAP.items():
        threading.Thread(target=start_listener, args=(port, slave_id, bus), daemon=True).start()
        print(f"Listen: {HOST}:{port}  ->  Slave ID {slave_id}")

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nGateway Stopped.")

if __name__ == "__main__":
    main()