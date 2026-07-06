import RPi.GPIO as GPIO
from time import sleep

GPIO.setmode(GPIO.BCM)
GPIO.setup(13, GPIO.IN) #Oil Level Alarm
GPIO.setup(17, GPIO.IN) #Oil Level Trip
GPIO.setup(22, GPIO.IN) #Spare
GPIO.setup(27, GPIO.IN) #Spare

while True:
    print(f"Oil Level Alarm DI0 -> {GPIO.input(13)}")
    print(f"Oil Level Trip DI1  -> {GPIO.input(17)}")
    print(f"Spare DI2           -> {GPIO.input(22)}")
    print(f"Spare DI3           -> {GPIO.input(27)}")
    print()
    sleep(1)