import time
import shared.interface as pi

print("Starting peltier relay test. Do not ctrl-c.")

pi.peltier.turn_on()
time.sleep(5)
print("Ending...")
pi.peltier.turn_off()