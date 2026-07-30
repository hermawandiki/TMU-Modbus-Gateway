import socket
import struct
import threading
import time
import logging
from data_handler import lcd_lock, lcd_values, adc_lock, adc_registers, adc_channels

def calculate_crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8): crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return struct.pack("<H", crc)

def validate_crc16(frame: bytes) -> bool:
    return len(frame) >= 3 and calculate_crc16(frame[:-2]) == frame[-2:]

def tcp2rtu(tcp_frame: bytes, slave_id: int) -> bytes:
    rtu_body = bytes([slave_id]) + tcp_frame[7:]
    return rtu_body + calculate_crc16(rtu_body)

def rtu2tcp(rtu_frame: bytes, tx_id: bytes, unit_id: int) -> bytes:
    pdu = rtu_frame[1:-2]
    return tx_id + b"\x00\x00" + struct.pack(">H", len(pdu) + 1) + bytes([unit_id]) + pdu

def handle_adc_client(conn: socket.socket, addr, port: int):
    try:
        while True:
            tcp_req = conn.recv(1024)
            if not tcp_req or len(tcp_req) < 12: break
            tx_id, unit_id, fc = tcp_req[0:2], tcp_req[6], tcp_req[7]
            if fc in (0x03, 0x04):
                start_addr, qty = struct.unpack(">HH", tcp_req[8:12])
                with adc_lock:
                    if start_addr + qty <= adc_channels:
                        data_bytes = b"".join(struct.pack(">h", int(adc_registers[i])) for i in range(start_addr, start_addr + qty))
                        res = tx_id + b"\x00\x00" + struct.pack("<H", 3 + qty*2) + bytes([unit_id, fc, qty*2]) + data_bytes
                        conn.sendall(res)
                    else:
                        conn.sendall(tx_id + b"\x00\x00" + struct.pack(">H", 3) + bytes([unit_id, fc | 0x80, 0x02]))
    except Exception: pass
    finally: conn.close()

def handle_rtu_client(conn: socket.socket, addr, port: int, slave_id: int, bus, dummy_mode: bool):
    try:
        while True:
            tcp_req = conn.recv(1024)
            if not tcp_req or len(tcp_req) < 8: break
            tx_id, unit_id, fc = tcp_req[0:2], tcp_req[6], tcp_req[7]
            
            if dummy_mode:
                if fc in (0x03, 0x04):
                    start_addr, qty = struct.unpack(">HH", tcp_req[8:12])
                    regs = [0] * qty
                    with lcd_lock:
                        if slave_id == 1 and start_addr == 0x0000 and qty <= 9:
                            regs = [int(lcd_values[12+i]*100) for i in range(6)] + [int(lcd_values[18+i]*1000) for i in range(min(qty-6, 3))]
                        elif slave_id == 10 and start_addr == 0x1300 and qty <= 5:
                            regs = [0, int(lcd_values[5]*1000), int(lcd_values[4]*10), 0, int(lcd_values[3]/25.0)]
                    data_bytes = struct.pack(f">{len(regs)}H", *regs)
                    res = tx_id + b"\x00\x00" + struct.pack(">H", 3 + len(data_bytes)) + bytes([unit_id, fc, len(data_bytes)]) + data_bytes
                    conn.sendall(res)
                continue

            rtu_res = bus.send_and_receive(tcp2rtu(tcp_req, slave_id))
            if rtu_res and validate_crc16(rtu_res):
                if slave_id == 1 and fc in (0x03, 0x04):
                    start_addr, qty = struct.unpack(">HH", tcp_req[8:12])
                    payload = rtu_res[3:-2]
                    if len(payload) == qty * 2:
                        regs = struct.unpack(f">{qty}H", payload)
                        with lcd_lock:
                            if start_addr == 0x0000 and qty >= 9:
                                lcd_values[12:18] = [round(x/100.0, 2) for x in regs[0:6]]
                                lcd_values[18:21] = [round(x/1000.0, 3) for x in regs[6:9]]
                                lcd_values[21] = round(sum(lcd_values[18:21])/3.0, 2)
                conn.sendall(rtu2tcp(rtu_res, tx_id, unit_id))
            else:
                conn.sendall(tx_id + b"\x00\x00" + struct.pack(">H", 3) + bytes([unit_id, fc | 0x80, 0x0B]))
    except Exception: pass
    finally: conn.close()

def _server_listener(host, port, target, bus, dummy_mode, stop_event):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try: server.bind((host, port))
    except Exception as e:
        logging.error(f"Bind Error Port {port}: {e}"); return
    server.listen(5)
    server.settimeout(1.0)
    
    while not stop_event.is_set():
        try:
            conn, addr = server.accept()
            if str(target).upper() == "ADC":
                threading.Thread(target=handle_adc_client, args=(conn, addr, port), daemon=True).start()
            else:
                threading.Thread(target=handle_rtu_client, args=(conn, addr, port, int(target), bus, dummy_mode), daemon=True).start()
        except socket.timeout: continue
        except Exception: break
    server.close()

def start_gateway_engine(host: str, port_slave_map: dict, bus, dummy_mode: bool, stop_event, hb_callback=None):
    for port, target in port_slave_map.items():
        threading.Thread(target=_server_listener, args=(host, port, target, bus, dummy_mode, stop_event), daemon=True).start()
        logging.info(f"Gateway Listening on Port {port} -> {target}")
    
    def _hb_loop():
        while not stop_event.is_set():
            if hb_callback: hb_callback(time.time())
            time.sleep(1.0)
    threading.Thread(target=_hb_loop, daemon=True).start()