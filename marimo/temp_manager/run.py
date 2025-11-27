"""
Run this file to run temp_manager. The temp_manager service is 
responsible for controlling fan & peltier to regulate tank temperature
within a specific temperature range.

Access to peripherals is done thru gpio_service. Any change to configuration
is propagated through a sock_api to keep the service lightweight.
"""
import time
import threading

from dataclasses import dataclass, asdict
from enum import Enum

import shared.log as make_log
log = make_log.make_log("temp-manager")
import shared.sock_api as sock_api

from yaml import safe_load as yaml_load
from yaml import dump as yaml_dump
with open("storage/temp_manager/settings.yaml") as file:
    settings = yaml_load(file)
GPIO_PORT = settings["gpio_addr"]["port"]
GPIO_ADDR = settings["gpio_addr"]["addr"]

PARAMS_FILE = "storage/temp_manager/params.yaml"

## Utils to manage params
"""
The params file is to save the params of the manager so that it can
be restored on the next start.

The params in the manager are not to be touched. The service should
be stopped before the params are updated, both internal and file.
"""

@dataclass
class Params:
    """Dataclass, represents the current parameters of the cooler."""
    low: float 
    high: float
    fan_retain: float
    tick_time: float

def read_params_file() -> Params:
    """Read the params file to a params object."""
    with open(PARAMS_FILE) as file:
        new_params = yaml_load(file)
    return Params(
        **new_params
    )

PARAMS_HEADER = """# This is loaded on startup of temp_manager
# Change the params thru the API when temp_manager is running.
# API updates will also update this file
"""

def write_params_file(new_params: Params):
    """Write params to the params file."""
    data = asdict(new_params)
    written = PARAMS_HEADER + yaml_dump(data)
    with open(PARAMS_FILE, 'w') as file:
        file.write(written)

## Actual manager
Phase = Enum('Phase', [('cool', 1), ('idle', 2)])
@dataclass
class State:
    """Contains the whole state of TempManager"""
    phase: Phase
    # Ticks after the last time the peltier was turned on.
    last_peltier_on: int 

class TempManager:
    """Class which contains critical functionality that manages 
    temperature.

    The system has two phases, cool and idle.
    -> The system starts at cool
    -> When cool:
    - Peltier is on
    - If the temperature < low, change to "idle".
    -> When idle:
    - Peltier is off.
    - If the temperature >= high, change to "cooling"

    The fan stays on for fan_retain seconds after the peltier is switched off.

    tick_time is the time between the start of each tick to aim for."""
    def __init__(
        self, 
        params: Params, 
        server_conn: sock_api.SockConn,
        state: State = State(phase = Phase.cool, last_peltier_on = 0)
    ):
        """server_conn is a SockConn to the GPIOService."""
        self.params = params
        self.state = state
        self.server_conn = server_conn
        self.stop_lock = threading.Lock()
    
    def gpio_req(self, body: "Any") -> "Any":
        """Makes a request to GPIOService. Raises RuntimeError
        if internal error faced in GPIOService. Raises sock_api.ClosedException
        if unreachable."""
        response = self.server_conn.request(body)
        if type(response) is str and response.startswith("Internal error"):
            raise RuntimeError(f"GPIOService server error: {response}")
        return response
    
    def peltier_tick(self):
        """Runs the peltier control section of a tick.
        If the server is unreachable, raises sock_api.ClosedException.
        Assume server never misbehaves."""
        temperature = self.gpio_req({"name": "tank_temp", "operation": "read"})

        # Update current phase if needed.
        if self.state.phase == Phase.cool and temperature < self.params.low:
            self.state.phase = Phase.idle
            log("Changed to idle state.")
        elif self.state.phase == Phase.idle and temperature >= self.params.high:
            self.state.phase = Phase.cool
            log("Changed to cooling state.")

        # Set peltier to what is appropriate for phase.
        peltier_on = self.gpio_req({"name": "peltier", "operation": "is_on"})
        if peltier_on and self.state.phase == Phase.idle:
            self.gpio_req({"name": "peltier", "operation": "turn_off"})
            log("Turning peltier off")
        elif not peltier_on and self.state.phase == Phase.cool:
            self.gpio_req({"name": "peltier", "operation": "turn_on"})
            log("Turning peltier on")
        
    def fan_tick(self):
        """Runs the fan control section of a tick. 
        If the server is unreachable, raises sock_api.ClosedException.
        Assume server never misbehaves."""
        peltier_on = self.gpio_req({"name": "peltier", "operation": "is_on"})
        if peltier_on:
            self.state.last_peltier_on = 0
        else:
            self.state.last_peltier_on += 1
        
        last_time = self.state.last_peltier_on * self.params.tick_time

        fan_on = self.gpio_req({"name": "fan", "operation": "is_on"})
        if last_time < self.params.fan_retain and not fan_on:
            self.gpio_req({"name": "fan", "operation": "turn_on"})
            log("Turning fan on")
        elif last_time >= self.params.fan_retain and fan_on:
            self.gpio_req({"name": "fan", "operation": "turn_off"})
            log("Turning fan off")
    
    def tick(self) -> tuple:
        """Runs a full cooling tick. Returns a tuple 
        (peltier_tick exception | None, fan_tick exception | None)
        """
        try:
            self.peltier_tick()
            peltier_fail = None
        except Exception as e:
            log(f"Peltier tick failed with {repr(e)}")
            peltier_fail = e
        
        try:
            self.fan_tick()
            fan_fail = None
            log(f"Fan tick failed with {repr(e)}")
        except Exception as e:
            fan_fail = e
        
        return (peltier_fail, fan_fail)
    
    def run(self):
        """Run the service. Stop with .stop().
        Never ever change params when running."""
        log(f"Cooling service started. Params={self.params}")
        while True:
            start = time.perf_counter()
            result = self.tick()
            # TODO: Log tick result.
            elapsed = time.perf_counter() - start
            to_wait = self.params.tick_time - elapsed
            if to_wait > 0:
                time.sleep(to_wait)

            # TODO: extremely long tick time will freeze system.
            if self.stop_lock.locked():
                self.stop_lock.release() # Return the signal
                break
        log("Cooling service ended.")
    
    def stop(self):
        """Stop the service gracefully.
        TODO: Make sure run is actually running when this is called else deadlock occurs"""
        self.stop_lock.acquire() # Signal
        self.stop_lock.acquire() # Wait for returned signal
        log("Cooling service ended")

def get_manager():
    """Get a manager object initialised with saved params and GPIOService"""
    return TempManager(
        read_params_file(),
        sock_api.SockConn(GPIO_ADDR, GPIO_PORT)
    )

