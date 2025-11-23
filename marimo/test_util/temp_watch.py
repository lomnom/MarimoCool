import time
import shared.interface as pi

print("Watching temperature")

try:
    while True:
        print(pi.tank_temp.read(), "C")
except KeyboardInterrupt:
    pass

print("Ending...")