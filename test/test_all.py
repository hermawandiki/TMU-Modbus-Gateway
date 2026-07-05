import Adafruit_ADS1x15
from time import sleep
from enum import Enum
from pymodbus.client import ModbusSerialClient
import RPi.GPIO as GPIO
import smbus2
from PIL import Image, ImageDraw, ImageFont

class option(Enum):
	TEST_GPIO = '1'
	TEST_ADC = '2'
	TEST_SERIAL = '3'
	TEST_OLED = '4'
	
loop = False
pilihan = option.TEST_OLED

I2C_BUS = 1
I2C_ADDR = 0x3C
bus = smbus2.SMBus(I2C_BUS)

adc = Adafruit_ADS1x15.ADS1115(address=0x48, busnum=1)
client = ModbusSerialClient(method='rtu', port='/dev/ttyACM0', baudrate=9600)

GPIO.setmode(GPIO.BCM)
GPIO.setup(13, GPIO.IN) #Oil Level Alarm
GPIO.setup(17, GPIO.IN) #Oil Level Trip
GPIO.setup(22, GPIO.IN) #Spare
GPIO.setup(27, GPIO.IN) #Spare

def adc_test():
	reserved0 		= adc.read_adc(0, gain=2)
	reserved1 		= adc.read_adc(1, gain=2)
	pressure_raw 	= adc.read_adc(2, gain=2)
	temperature_raw = adc.read_adc(3, gain=2)
	
	print(f"Reserved 0 Raw  -> {reserved0}")
	print(f"Reserved 1 Raw  -> {reserved1}")
	print(f"Pressure Raw    -> {pressure_raw}")
	print(f"Temperature Raw -> {temperature_raw}")
	
	# voltage = temperature_raw / 32767 * 2.07 * 2.5
	# current = voltage * 1000 / 250
	# print(f"Volt: {voltage} | Current: {current}")
	
	# temperature = round(((temperature_raw * 0.007630) - 50), 3) if temperature_raw >= 0 else 0
	# temperature = round(((temperature_raw * 0.009573) - 112.5), 3) if temperature_raw >= 0 else 0
	# pressure = (pressure_raw - 6553) / 26214 if pressure_raw >= 0 else 0
	# print(f"Oil Temp: {temperature} | Oil Press: {pressure}")
	
	print()

def serial_test():
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
    
def gpio_test():
	print(f"Oil Level Alarm DI0 -> {GPIO.input(13)}")
	print(f"Oil Level Trip DI1  -> {GPIO.input(17)}")
	print(f"Spare DI2           -> {GPIO.input(22)}")
	print(f"Spare DI3           -> {GPIO.input(27)}")
	print()

def oled_cmd(c):
	bus.write_byte_data(I2C_ADDR, 0x00, c)
	
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

def oled_test():
	oled_print("""TEST ROW 1
	TESTING ROW 2
	TESTING ROW 3
	TESTING ROW 4
	TESTING ROW 5""")
	
oled_init()

def main():
	if loop:
		while True:
			if pilihan == option.TEST_ADC:
				adc_test()
			if pilihan == option.TEST_ADC:
				adc_test()
			elif pilihan == option.TEST_GPIO:
				gpio_test()
			elif pilihan == option.TEST_SERIAL:
				serial_test()
			elif pilihan == option.TEST_OLED:
				oled_test()
			else:
				print("Tidak ada tes yang dipilih")
			sleep(1)
	else:
		if pilihan == option.TEST_ADC:
			adc_test()
		elif pilihan == option.TEST_GPIO:
			gpio_test()
		elif pilihan == option.TEST_SERIAL:
			serial_test()
		elif pilihan == option.TEST_OLED:
			oled_test()
		else:
			print("Tidak ada tes yang dipilih")
	
	GPIO.cleanup()

if __name__ == "__main__":
	main()
