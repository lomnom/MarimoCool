"""
Turn on the fan
"""
from .std_adaptor import gpio_req
import shared.log as make_log
log = make_log.make_log("fan")

log("Turning fan on")
gpio_req({"name": "fan", "operation": "turn_on"})
log("Fan is on.")