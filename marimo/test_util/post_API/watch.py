"""
Tool to watch temp, peltier and fan state.
Pings every 3 seconds.
"""
from .std_adaptor import gpio_req
import shared.log as make_log
import shared.sock_api as sock_api
import time
log = make_log.make_log("watch")

while True:
    try:
        temp = gpio_req({"name": "tank_temp", "operation": "read"})
        peltier_on = gpio_req({"name": "peltier", "operation": "is_on"})
        fan_on = gpio_req({"name": "fan", "operation": "is_on"})
    except RuntimeError as e:
        log(f"Internal error in GPIOService: {repr(e)}")
    except sock_api.BrokenException:
        log(f"GPIOService is unreachable!")

    output = ""

    temp_str = f"{temp}C".ljust(8)

    peltier_char = "=" if peltier_on else "."

    fan_char = "F" if fan_on else "."

    bars = round((temp - 17) * 10) * "-"

    output = temp_str + " | " + peltier_char + " " + fan_char + " | " + bars

    log(output)
    time.sleep(3)