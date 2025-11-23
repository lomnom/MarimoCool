import time
import interface as pi

print("Cooling with fan")

pi.fan.turn_on()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass

print("Ending cooling...")
pi.fan.turn_off()