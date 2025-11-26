"""
Run this file to run gpio_service.

gpio_service is responsible for exposing and API that can be used to 
control and check the state of peripherals connected to the pi. This
is to allow multiple programs to read from temperature sensors/control
peltier & fan at the same time safely (not possible with base GPIO).

Thus the decision to make GPIO control a seperate service. A bonus is that
it allows basically every other service to be run remotely.

We will export every peripheral in pi.PERIPHERALS.

Request format: {"name": name of peripheral, "operation": operation}
Response format: return value or "Internal error [...]"

For Sensors:
- `read` operation, returns what sensor.read returns.
  - To prevent bursts from causing hugh latency:
    If there is a measurement less than settings.sensor_cache old, 
    use that.

For Device:
- `is_on` operation, returns bool
- `turn_on`, `turn_off` operation, returns "OK"

Settings are in storage/gpio_service/settings.yaml (TODO: should make 
a module to handle settings in the future??)
"""

import time
import threading

from yaml import safe_load as yaml_load
with open("storage/gpio_service/settings.yaml") as file:
    settings = yaml_load(file)
PORT = settings["port"]
CACHE_EXPIRE = settings["cache_expire"]

import shared.sock_api as sock_api
import shared.interface as pi
import shared.log as make_log
log = make_log.make_log("gpio_service")

# What to export
export = pi.PERIPHERALS

# Sensor data cache
cache = {}
time_ref = time.perf_counter

for name, item in export.items():
    if isinstance(item, pi.Sensor):
        # Cache items are stored as (time_ref when created, value)
        cache[name] = (float("-inf"), None)

# Request lock to prevent race conditions
req_lock = threading.Lock()

# Create server
server = sock_api.SockServer(PORT)

@server.handler
def handle_req(req_body: "Any", addr: "str") -> "Any":
    """Handle a request to GPIOService."""
    print(f"Request from {addr}: {req_body}")

    try:
        name = req_body["name"]
        operation = req_body["operation"]
    except KeyError:
        raise SyntaxError("Request dict must have `name` and `operation` keys!")

    try:
        peripheral = export[name]
    except KeyError:
        raise LookupError(f"Peripheral {name} is not found!")

    with req_lock: # GPIO maniuplation is not thread-safe.
        if isinstance(peripheral, pi.Sensor):
            if operation == "read":
                cache_time, cached = cache[name]
                if time_ref() - cache_time > CACHE_EXPIRE:
                    # If cache has expired, refresh
                    reading = peripheral.read()
                    cache[name] = (time_ref(), reading)
                else:
                    # Cache still valid
                    reading = cached
                return reading
            else:
                raise SyntaxError(f"Operation {operation} for sensor not allowed!")
        elif isinstance(peripheral, pi.Device):
            if operation == "is_on":
                return peripheral.is_on()
            elif operation == "turn_on":
                peripheral.turn_on()
                return "OK"
            elif operation == "turn_off":
                peripheral.turn_off()
                return "OK"
            else:
                raise SyntaxError(f"Operation {operation} for device not allowed!")

log(f"Initialised! Listening @ port {PORT}")
server.run()