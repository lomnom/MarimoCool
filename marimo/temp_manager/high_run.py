"""
This file is a higher-level runner for core_run which implements:
1. Starting and stopping core_run
2. Saving previous params to reuse on startup
3. Exposing a sock_api that can:
    - Start service
    - Stop service
    - Check if running
    - Query State
    - Query current Params
    - Update params when service stopped

TODO: Error reporting, get last few errors & error when service crashes.
"""

from yaml import dump as yaml_dump
from yaml import safe_load as yaml_load
with open("storage/temp_manager/settings.yaml") as file:
    settings = yaml_load(file)
PORT = settings["port"]

import subprocess
import threading
import signal
import json
import copy

import shared.log as make_log
log = make_log.make_log("temp-high")

## Params file utils
PARAMS_FILE = "storage/temp_manager/params.yaml"

"""
The params file is to save the params of the manager so that it can
be restored on the next start.

The params in the manager are not to be touched. The service should
be stopped before the params are updated, both internal and file.
"""

def read_params_file() -> dict:
    """Read the params file."""
    # TODO: Start in halted state if params invalid.
    with open(PARAMS_FILE) as file:
        new_params = yaml_load(file)
    return new_params

PARAMS_HEADER = """# This is loaded on startup of temp_manager
# Change the params thru the API when temp_manager is running.
# API updates will also update this file
"""

def write_params_file(new_params: dict):
    """Write params to the params file."""
    written = PARAMS_HEADER + yaml_dump(new_params)
    with open(PARAMS_FILE, 'w') as file:
        file.write(written)

## Creation of the instance
# -u --> unbuffered
BASE_COMMAND = ["python3", "-u", "-m", "temp_manager.core_run"]

class Instance:
    """Represents an instance of core_run. 
    Attributes: 
    - self.running --> If it is running.
    TODO: Error reporting."""
    def __init__(self):
        self.running = False

        self.instance_info = [None, None] # live [params, state] when running.
        self.info_lock = threading.Lock()

    def handle_packet(self, data: str):
        """
        Handle a packet sent thru stderr.
        """
        with self.info_lock:
            kind, _, info = data.partition(";")
            if kind == "state":
                state = json.loads(info)
                self.instance_info[1] = state
            elif kind == "params":
                params = json.loads(info)
                self.instance_info[0] = params
    
    def live_info(self) -> tuple:
        """
        Get live info about the system.
        Returns None for a field if no info is available yet or
        the system is offline.
        Returns (params, state).
        """
        with self.info_lock:
            return tuple(
                copy.deepcopy(self.instance_info)
            )

    def stderr_stream(self, pipe):
        """Reads data from stderr pipe.
        Terminates when pipe closes."""
        for data in iter(pipe.readline, ""):
            if len(data) < 5 or not data[:5].isnumeric():
                continue # TODO: Handle, likely exception.

            length, content = data[:5], data[5:]
            length = int(length)
            while len(content) < length:
                content += pipe.readline()
            
            content = content[:-1] # Remove trailing '\n'
            self.handle_packet(content)
    
    def stdout_stream(self, pipe):
        """Reads data from stdout pipe.
        Terminates when pipe closes."""
        for data in iter(pipe.readline, ""):
            data = data[:-1] # Remove trailing newline.
            log(f"Stdout data received: {data}")
    
    def watchdog(self):
        """Watches the process and does cleanup on crash.
        Any non-zero exit code is considered a crash."""
        return_code = self.proc.wait()
        if return_code != 0:
            log(f"Process crashed with return code {return_code}!!!!!")
            log(f"Doing cleanup...")

            self.running = False
            self.instance_info = [None, None]
            
            self.stdout_thread.join()
            self.stderr_thread.join()
    
    def start(self, params: dict):
        """Start the instance with given params."""
        if self.running:
            raise RuntimeError("Instance running already!")
        
        self.running = True

        command = BASE_COMMAND

        args = [
            params["low"],
            params["high"],
            params["fan_retain"],
            params["tick_time"]
        ]
        args = [str(arg) for arg in args]

        self.proc = subprocess.Popen(
            command + args,
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE,
            text = True,
            encoding = "ascii", # Standardised.
            # We do not need to set bufsize as -u specified alreday.
        )

        self.stdout_thread = threading.Thread(
            target=self.stdout_stream, 
            args=(self.proc.stdout,)
        )
        self.stderr_thread = threading.Thread(
            target=self.stderr_stream, 
            args=(self.proc.stderr,)
        )
        self.watch_thread = threading.Thread(
            target=self.watchdog, 
        )
        self.watch_thread.start()
        self.stdout_thread.start()
        self.stderr_thread.start()
    
    def exit(self):
        """Stops the instance. Blocks till a full exit."""
        if not self.running:
            raise RuntimeError("Instance not running!")

        self.running = False
        self.instance_info = [None, None]

        self.proc.send_signal(signal.SIGINT) # Ctrl-c to core_run
        self.proc.wait() # Wait for procs to end

        self.stdout_thread.join()
        self.stderr_thread.join()
        self.watch_thread.join()
    
    def __del__(self):
        if self.running:
            self.exit()

# The one instance object we will use.
instance = Instance()

# We start the instance started with the last run's saved params.
params = read_params_file()

# We start the instance started with the last run's saved params.
instance = Instance()
input("Enter to continue")

instance.start(params)

input("Enter to continue")

instance.exit()

input("Enter to continue")

instance.start(params)

input("Enter to continue")

instance.exit()

print("Exiting...")
del instance

print(instance)