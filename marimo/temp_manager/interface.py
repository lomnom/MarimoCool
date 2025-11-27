"""
This file defines a safe interface for TempManager that also
implements persistent param storage.

The TempManager will run in a seperate thread.
"""

from yaml import safe_load as yaml_load
from yaml import dump as yaml_dump
with open("storage/temp_manager/settings.yaml") as file:
    settings = yaml_load(file)
GPIO_PORT = settings["gpio_addr"]["port"]
GPIO_ADDR = settings["gpio_addr"]["addr"]

import temp_manager.manager as temp
import shared.sock_api as sock_api

from dataclasses import asdict
import threading
import atexit

PARAMS_FILE = "storage/temp_manager/params.yaml"

## Params file management.
"""
The params file is to save the params of the manager so that it can
be restored on the next start.

The service must be stopped before the params are updated, both 
internal and file.
"""

# Assume files & folders exist.

def read_params_file() -> temp.Params:
    """Read the params file to a params object."""
    # TODO: If the yaml is invalid we're cooked
    with open(PARAMS_FILE) as file:
        new_params = yaml_load(file)
    return temp.Params(
        **new_params
    )

PARAMS_HEADER = """# This is loaded on startup of temp_manager
# Change the params thru the API when temp_manager is running.
# API updates will also update this file
"""

def write_params_file(new_params: temp.Params):
    """Write params to the params file."""
    data = asdict(new_params)
    written = PARAMS_HEADER + yaml_dump(data)
    with open(PARAMS_FILE, 'w') as file:
        file.write(written)

## To run the manager in a seperate thread.
class Interface:
    """Safe interface for TempManager. It is run in a seperate thread.
    Handles param saving and loading."""

    # Enforce singleton.
    single = None
    def __new__(cls, *args, **kwargs):
        if cls.single is None:
            cls.single = super().__new__(cls)
        return cls.single

    def __init__(self):
        self.thread = None
        self.instance = temp.TempManager(
            read_params_file(),
            sock_api.SockConn(GPIO_ADDR, GPIO_PORT)
        )
        atexit.register(self.atexit_safe)

        self.param_lock = threading.Lock() # Lock around param setting.
    
    def is_running(self):
        """Returns True if TempManager is running."""
        # NOTE: .run() will never crash.
        return self.thread is not None

    def start_manager(self):
        """
        Run this to start the manager thread.
        Raises ValueError if manager already running.
        """
        if self.is_running():
            raise ValueError("TempManager already running!")
        
        self.thread = threading.Thread(
            target = self.instance.run
        )
        self.thread.start()

    def stop_manager(self):
        """
        Run this to stop the manager.
        Raises ValueError if not running.
        """
        if not self.instance.is_running():
            raise ValueError("TempManager not running yet!")
        
        self.instance.stop()
        self.thread.join()
        self.thread = None
    
    def atexit_safe(self):
        """Stop the manager on exit"""
        if self.is_running():
            self.stop_manager() # Gracefully stop manager

    ## Public access utilities
    def get_state(self) -> dict | None:
        """
        Get the current state of the instance.
        None if instance not running.
        """
        state = self.instance.copy_state()
        if state is None:
            return state
        else:
            return asdict(state)

    def get_params(self) -> dict:
        """
        Utility to get current params of instance.
        """
        params = self.instance.copy_params()
        return asdict(params)

    ## Param updating.
    def validate_params(self, params: temp.Params) -> bool:
        """
        Validate given params. Raises AssertionError if any test fails.
        Validation is minimum to allow for experimentation.
        """
        def ensure(result: bool):
            """Like assert but not disabled in debug mode."""
            if not result:
                raise AssertionError("Assertion failed.")

        # Type tests. The values, even in yaml, must be float not int.
        ensure(type(params.low) is float)
        ensure(type(params.high) is float)
        ensure(type(params.fan_retain) is float)
        ensure(type(params.tick_time) is float)

        # Validity
        ensure(0 <= params.tick_time <= 60) # Tick time >60 makes system unresponsive, dangerous.

    def set_params(self, params: dict):
        """
        Utility to update params of instance. Also keeps the yaml save in sync.
        Must only be used when instance is down.
        Raises RuntimeError if interface running, AssertionError if params invalid.
        Raises TypeError if there are extra or missing keys in dict.
        Is thread safe.
        """
        with self.param_lock:
            params = temp.Params(**params) # TypeError if extra or missing keys

            # Validate
            self.validate_params(params) # Throws on fail.
            
            # Update params.
            self.instance.update_params(params)
            write_params_file(params)

interface = Interface()