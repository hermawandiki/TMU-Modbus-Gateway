import Adafruit_ADS1x15
from time import sleep

adc = Adafruit_ADS1x15.ADS1115(address=0x48, busnum=1)

while True:
    ch0 = adc.read_adc(0, gain=2)
    ch1 = adc.read_adc(1, gain=2)
    ch2 = adc.read_adc(2, gain=2)
    ch3	= adc.read_adc(3, gain=2)
    
    print(f"Channel 0 Raw  -> {ch0}")
    print(f"Channel 1 Raw  -> {ch1}")
    print(f"Channel 2 Raw  -> {ch2}")
    print(f"Channel 3 Raw  -> {ch3}")
    
    #voltage = temperature_raw / 32767 * 2.07 * 2.5
    #current = voltage * 1000 / 250
    # print(f"Volt: {voltage} | Current: {current}")
    
    temperature = round(((ch0 * 0.007630) - 50), 3) if ch0 >= 0 else 0
    #temperature = round(((ch0 * 0.009573) - 112.5), 3) if ch0 >= 0 else 0
    pressure = (ch1 - 6553) / 26214 if ch1 >= 0 else 0
    print(f"Oil Temp: {temperature} | Oil Press: {pressure}")
    
    print()
    sleep(1)