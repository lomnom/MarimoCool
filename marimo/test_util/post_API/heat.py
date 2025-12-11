"""
Turn on the peltier to heat hot side.
"""
from .std_adaptor import gpio_req
import shared.log as make_log
from time import sleep
log = make_log.make_log("heat")

log("Turning heat on. ctrl-c to stop.")
try:
    gpio_req({"name": "peltier", "operation": "turn_on"})
    log("Heat is on.")
    while True:
        sleep(1)
except KeyboardInterrupt:
    gpio_req({"name": "peltier", "operation": "turn_off"})
    log("Heat is off.")