import time
import shared.interface as pi

print("Starting cooling test. CTRL-C to stop.")

pi.peltier.turn_on()
pi.fan.turn_on()

try:
    start_time = time.perf_counter()
    while True:
        output = ""

        elapsed = round(time.perf_counter() - start_time, 1)
        output += str(elapsed).rjust(6, " ") + ": "

        temp = pi.tank_temp.read()
        output += f"{temp}C".ljust(9)

        bars = round((temp - 20) * 10) * "-"
        output += " " + bars

        print(output)
        time.sleep(1)
except KeyboardInterrupt:
    pass

print("Ending cooling test...")
pi.peltier.turn_off()
pi.fan.turn_off()