import time
import shared.interface as pi

print("Starting two relay test. Do not ctrl-c.")

pi.peltier.turn_on()
print("Peltier on")
time.sleep(1)

pi.fan.turn_on()
print("Fan on")
time.sleep(1)

print("Ending...")
pi.fan.turn_off()
pi.peltier.turn_off()