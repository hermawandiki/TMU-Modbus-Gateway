from pymodbus.client import ModbusSerialClient
from time import sleep

client = ModbusSerialClient(method='rtu', port='/dev/ttyACM0', baudrate=9600)

while True:
    try:
        mb_data1 = client.read_holding_registers(0x0000, 3, slave=2)
        print(f"Read Slave ID 2 Register  -> {mb_data1.registers}")
    except Exception as e:
        print(f"Slave ID 2 Failed Exception! Error: {e}")

    try:
        mb_data2 = client.read_holding_registers(0x1301, 4, slave=10)
        print(f"Read Slave ID 10 Register -> {mb_data2.registers}")
    except Exception as e:
        print(f"Slave ID 10 Failed Exception! Error: {e}")
        
    print()
    sleep(1)