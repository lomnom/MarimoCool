"""
Run this file to run temp_manager. The temp_manager service is 
responsible for controlling fan & peltier to regulate tank temperature
within a specific temperature range.

Access to peripherals is done thru gpio_service. This file is kept simple for
reliability.

The following log messages are guaranteed:
- "Cooling service started. Params=[...]" on startup to show what parameters are used.
- Within a single tick, in this order:
    - "Running tick..." when a tick is started
    - "Peltier tick failed with [...]" If an exception occurs during peltier tick
    - "Fan tick failed with [...]" if an exception occurs during fan tick.
    - "State after tick: [...]" printed after every tick to show state.
    - "Tick done." after the tick is done
"""
import time
import threading

from dataclasses import dataclass, asdict
from enum import Enum

import shared.log as make_log
log = make_log.make_log("temp-manager")
import shared.sock_api as sock_api

from yaml import safe_load as yaml_load
with open("storage/temp_manager/settings.yaml") as file:
    settings = yaml_load(file)
GPIO_PORT = settings["gpio_addr"]["port"]
GPIO_ADDR = settings["gpio_addr"]["addr"]

from sys import argv
# Run this program as python3 -m temp_manager.core_run [low] [high] [fan_retain] [tick_time]
# Where all square brackets are floats.

## Utils to manage params
@dataclass
class Params:
    """Dataclass, represents the current parameters of the cooler."""
    low: float 
    high: float
    fan_retain: float
    tick_time: float

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

    tick_time is the time between the start of each tick to aim for.
    """
    def __init__(
        self, 
        params: Params, 
        server_conn: sock_api.SockConn
    ):
        """server_conn is a SockConn to the GPIOService."""
        self.params = params
        self.state = None
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
        except Exception as e:
            log(f"Fan tick failed with {repr(e)}")
            fan_fail = e
        
        return (peltier_fail, fan_fail)
    
    initial_state = State(phase = Phase.cool, last_peltier_on = 0)
    def run(self):
        """Run the service. Stop with .stop().
        Never ever change params when running."""
        if self.is_running():
            # Only ONE run instance can exist at any time.
            raise RuntimeError("An instance of manager is running already!")

        log(f"Cooling service started. Params={asdict(self.params)}")
        self.state = State(**asdict(self.initial_state))

        while True:
            start = time.perf_counter()
            log(f"Running tick...") 
            result = self.tick()
            log(f"State after tick: {asdict(self.state)}") 
            log(f"Tick done.") 
            elapsed = time.perf_counter() - start
            to_wait = self.params.tick_time - elapsed
            if to_wait > 0:
                time.sleep(to_wait)

            # TODO: extremely long tick time will freeze system.
            if self.stop_lock.locked():
                self.stop_lock.release() # Return the signal
                break
        
        self.state = None
        log("Tick loop ended.")
    
    def is_running(self) -> bool:
        """Returns True if the service is running now else False."""
        return self.state is not None

    def stop(self):
        """Stop the service gracefully.
        If it is not running, has no effect.
        Pls understand that the double-acquire mechanism works, and
        allows for back-signalling.
        """
        if not self.is_running():
            self.stop_lock.acquire() # Signal
            self.stop_lock.acquire() # Wait for returned signal
            log("Cooling service ended")

def get_params() -> Params:
    """Get params from keyword arguments.
    Does validation."""
    if len(argv) != 5:
        raise ValueError(
            "4 arguments expected! Run as "
            "python3 -m temp_manager.core_run [low] [high] [fan_retain] [tick_time]"
        )
    _, low, high, fan_retain, tick_time = argv

    try:
        low = float(low)
        high = float(high)
        fan_retain = float(fan_retain)
        tick_time = float(tick_time)
    except ValueError:
        raise ValueError("Provided arguments must be numerical values!")
    
    def ensure(val: bool):
        """Like assert but cannot be disabled."""
        if not val: 
            raise AssertionError("Assertion failed.")
    
    ensure(high > low)
    ensure(fan_retain >= 0)
    ensure(1 <= tick_time <= 60) # High tick time makes system unresponsive.

    return Params(
        low = low, high = high, 
        fan_retain = fan_retain, tick_time = tick_time
    )

def get_manager():
    """Get a manager object initialised with saved params and GPIOService"""
    return TempManager(
        get_params(),
        sock_api.SockConn(GPIO_ADDR, GPIO_PORT)
    )

manager = get_manager()
log(f"Using params {manager.params}") 

thread = threading.Thread(
    target = manager.run
)
thread.start()

try:
    thread.join()
except KeyboardInterrupt:
    log("Ending...")
    manager.stop()
    thread.join()
    log("Ended.")