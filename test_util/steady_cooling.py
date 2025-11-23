import time
import interface as pi

print("Starting steady cooling test. CTRL-C to stop.")

# Leave fan on for 1min30s after deactivation to cool heatsink and prevent backflow.
last_cool = time.perf_counter()
def fan_update():
    if time.perf_counter() - last_cool < 90:
        pi.fan.turn_on()
    else:
        pi.fan.turn_off()

def cool():
    global last_cool
    pi.peltier.turn_on()
    last_cool = time.perf_counter()

def no_cool():
    pi.peltier.turn_off()

# Small to avoid turning on peltier for long period
# Heat buildup causes ineffeciency
# 18-22 is the range tested to be optimal. 
UPPER = 21.5
LOWER = 21

cooling = False
temp = pi.tank_temp.read()
if temp >= UPPER:
    cooling = True
elif temp <= LOWER:
    cooling = False

try:
    start_time = time.perf_counter()
    while True:
        output = ""

        elapsed = round(time.perf_counter() - start_time, 1)
        output += str(elapsed).rjust(6, " ") + ": "

        temp = pi.tank_temp.read()
        output += f"{temp}C".ljust(9)

        if temp >= UPPER:
            cooling = True
        elif temp <= LOWER:
            cooling = False
        
        if cooling:
            cool()
        else:
            no_cool()

        fan_update()
        
        if pi.peltier.is_on():
            output += " = "
        else:
            output += " . "

        if pi.fan.is_on():
            output += " F "
        else:
            output += " . "

        bars = round((temp - 17) * 10) * "-"
        output += bars

        print(output)
        time.sleep(1)
except KeyboardInterrupt:
    pass

print("Ending cooling test...")

no_cool()
pi.fan.turn_off()