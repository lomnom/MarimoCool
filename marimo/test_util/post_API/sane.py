"""
Make everything sane again (yurn off fan and peltier)
"""
from .std_adaptor import gpio_req
import shared.log as make_log
log = make_log.make_log("sane")

log("Making everything sane again")
gpio_req({"name": "peltier", "operation": "turn_off"})
gpio_req({"name": "fan", "operation": "turn_off"})
log("Sanity restored")