import logging
import struct
import tkinter as tk

def calculate_crc16(data: bytes) -> int:
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

def tcp2rtu(tcp_frame: bytes, slave_id: int) -> bytes:
    if len(tcp_frame) < 8: 
        logging.error("TCP frame is too short to be a valid Modbus TCP frame.")
        return b""
    rtu_body = bytes([slave_id]) + tcp_frame[7:]
    
    crc_value = calculate_crc16(rtu_body)
    return rtu_body + struct.pack("<H", crc_value)

def rtu2tcp(rtu_frame: bytes, transaction_id: bytes) -> bytes:
    if len(rtu_frame) < 4: 
        logging.error("Frame is too short to be a valid Modbus RTU frame.")
        return b""
    slave_id = rtu_frame[0]
    pdu = rtu_frame[1:-2]
    return transaction_id + b"\x00\x00" + struct.pack(">H", len(pdu)+1) + bytes([slave_id]) + pdu

def verify_crc(rtu_frame: bytes) -> bool:
    if len(rtu_frame) < 3: 
        logging.error("Frame is too short to be a valid Modbus RTU frame.")
        return False
    body = rtu_frame[:-2]
    crc_received = struct.unpack("<H", rtu_frame[-2:])[0]
    
    return calculate_crc16(body) == crc_received