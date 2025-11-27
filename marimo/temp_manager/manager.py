"""
This file defines the core temperature regulation loop of temp_manager.

The temp_manager service is responsible for controlling fan & peltier
to regulate tank temperature within a specific temperature range.

Access to peripherals is done thru gpio_service. 

Any change to configuration is propagated through a sock_api (defined in run.py).
TempManager can be run through the interface defined in interface.py
"""
import time
import threading

from dataclasses import dataclass, asdict
from enum import Enum

import shared.log as make_log
log = make_log.make_log("temp-manager")
import shared.sock_api as sock_api

@dataclass
class Params:
    """Dataclass, represents the current parameters of the cooler."""
    low: float 
    high: float
    fan_retain: float
    tick_time: float

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
    - If the temperature >= high, change to "cool"

    The fan stays on for fan_retain seconds after the peltier is switched off.

    tick_time is the time between the start of each tick to aim for.
    
    State starts at TempManager.initial_state when .run() is called. It is
    None when not running.

    Public functions:
    - constructor
    - run
    - is_running
    - stop
    - copy_state
    - copy_params
    - update_params

    Public attributes:
    - [none.]

    Use only allowed public functions & attributes for safety.
    """

    def __init__(
        self, 
        params: Params, 
        server_conn: sock_api.SockConn,
    ):
        """server_conn is a SockConn to the GPIOService."""
        self.params = params
        self.server_conn = server_conn

        self.state = None
        self.tick_lock = threading.Lock() # Locked when a tick is happening.
        self.stop_lock = threading.Lock() # Used for stop signalling.
    
    ## Tick behavior
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
        with self.tick_lock:
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
    
    ## Start/stop behavior
    initial_state = State(phase = Phase.cool, last_peltier_on = 0)
    def run(self):
        """Run the service. Stop with .stop().
        Never ever change params when running."""
        log(f"Cooling service started. Params={self.params}")

        self.state = State(**asdict(self.initial_state)) # Make a copy.
        log(f"Initial state is {self.state}")

        while True:
            start = time.perf_counter()
            self.tick()
            elapsed = time.perf_counter() - start
            to_wait = self.params.tick_time - elapsed
            if to_wait > 0:
                time.sleep(to_wait)

            # NOTE: extremely long tick time will freeze system.
            if self.stop_lock.locked():
                self.stop_lock.release() # Return the signal
                break
        
        self.state = None
        log("Runner exiting")
    
    def is_running(self) -> bool:
        """Returns true if currently running, false otherwise.
        """
        return self.state is not None # state is None when not running.
    
    def stop(self):
        """Stop the service gracefully.
        Does nothing if not running."""
        if self.is_running():
            self.stop_lock.acquire() # Signal
            self.stop_lock.acquire() # Wait for returned signal
            log("Cooling service ended.")

    ## Safe public interfaces.
    def copy_state(self) -> State|None:
        """
        Returns a copy of the current state of the system.
        Returns None if not running.
        """
        with self.tick_lock:
            if self.state is None:
                return None
            else:
                return State(**asdict(self.state))
    
    def copy_params(self) -> Params:
        """Returns the a copy of the current params of the system."""
        return Params(**asdict(self.params))
    
    def update_params(self, params: Params):
        """Update the params of the system. 
        Can only be done when system is stopped. Raises RuntimeError
        if system is running when this is called.
        """
        if self.is_running():
            raise RuntimeError("Cannot update state when TempManager is running!")
        
        self.params = Params(**asdict(params)) # Create a copy.