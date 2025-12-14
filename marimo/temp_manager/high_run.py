"""
This file is a higher-level runner for core_run which implements:
1. Starting and stopping core_run
2. Saving previous params to reuse on startup
3. Exposing a flask api that is used to control it.
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
from datetime import datetime
from datetime import UTC as tz_UTC
from dataclasses import dataclass, asdict
from typing import Literal

def unix_time_now() -> int:
    """
    Returns the current unix timestamp.
    src: https://stackoverflow.com/questions/66393752/get-unix-time-in-python
    """
    return round(
        (datetime.now(tz_UTC) - datetime(1970, 1, 1, tzinfo = tz_UTC)).total_seconds()
    )

import shared.log as make_log
log = make_log.make_log("temp-high")

## Creation of the instance
# -u --> unbuffered
BASE_COMMAND = ["python3", "-u", "-m", "temp_manager.core_run"]

@dataclass
class RunInfo:
    """
    Dataclass which represents additional information about the current status.
    """
    # We have been running/stopped since this time, None if never started.
    since: int | None 

    # Reason for current running/stopped state.
    reason: Literal["never_started", "started", "stopped", "crashed"] 

    info: str | None # "<err>" if crash

class Instance:
    """Represents an instance of core_run. 
    TODO: Handle non-fatal errors.

    Attributes: 
    - self.running --> If it is running.
    - self.run_info --> RunInfo about current status.

    Probably the most complicated state & logic in the whole 
    temp_manager ngl. Complexity seems to be needed as we need live updates
    and robust instance management.
    """
    def __init__(self):
        # running contains if instance is running, run_info
        # contains info about why we are running or stopped.
        self.running = False
        self.run_info = RunInfo(
            since = None,
            reason = "never_started",
            info = None
        )

        self.instance_info = [None, None] # live [params, state] when running.
        self.info_lock = threading.Lock() # Lock for accessinf instance_info

        # Captures all malformatted output to stderr.
        # Resets to "" on every start.
        self.stderr_reject = ""

    def handle_packet(self, data: str):
        """
        Handle a packet sent thru stderr.
        TODO: Handle peltier_fail and fan_fail
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
                # Malformatted stderr, not a packet.
                self.stderr_reject += data
                continue

            length, content = data[:5], data[5:]
            length = int(length)
            while len(content) < length:
                content += pipe.readline()
            
            content = content[:-1] # Remove trailing '\n'
            self.handle_packet(content)
    
    def stdout_stream(self, pipe):
        """Reads data from stdout pipe.
        Terminates when pipe closes.
        Forwards messages in stdout."""
        for data in iter(pipe.readline, ""):
            data = data[:-1] # Remove trailing newline.
            log(f"Fw: {data}")
    
    def watchdog(self):
        """Watches the process and does cleanup on crash.
        Any non-zero exit code is considered a crash.
        NOTE: Assumes zero exit code can only be induced by .exit() or a 
        ctrl-c to the whole program."""
        return_code = self.proc.wait()
        if return_code != 0:
            log(f"Process crashed with return code {return_code}!!!!!")
            log(f"Doing cleanup...")

            self.running = False
            self.instance_info = [None, None]

            self.stdout_thread.join()
            self.stderr_thread.join()

            log(f"Cleaned up.")

            self.run_info = RunInfo(
                since = unix_time_now(),
                reason = "crashed",
                info = self.stderr_reject # Would contain exception.
            )
    
    param_keys = ["low", "high", "fan_retain", "tick_time"]
    def start(self, params: dict):
        """Start the instance with given params."""
        if self.running:
            raise RuntimeError("Instance running already!")
        
        self.running = True

        command = BASE_COMMAND

        args = [
            params[key] for key in self.param_keys
        ]
        args = [str(arg) for arg in args]

        self.proc = subprocess.Popen(
            command + args,
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE,
            text = True,
            encoding = "ascii", # Standardised.
            # We do not need to set bufsize as -u specified alreday.
            start_new_session=True # Prevents ctrl-c from propagating.
        )

        self.stdout_thread = threading.Thread(
            target=self.stdout_stream, 
            args=(self.proc.stdout,)
        )
        self.stderr_reject = "" # Reset reject cache.
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

        self.run_info = RunInfo(
            since = unix_time_now(),
            reason = "started",
            info = None
        )
    
    def exit(self):
        """Stops the instance. Blocks till a full exit."""
        if not self.running:
            raise RuntimeError("Instance not running!")

        log("Stopping core_run (wait a few seconds)...")
        self.running = False

        self.proc.send_signal(signal.SIGINT) # Ctrl-c to core_run
        self.proc.wait() # Wait for procs to end

        log("Cleaning threads...")
        self.stdout_thread.join()
        self.stderr_thread.join()
        self.watch_thread.join()

        self.instance_info = [None, None]

        self.run_info = RunInfo(
            since = unix_time_now(),
            reason = "stopped",
            info = None
        )

        log("Done.")
    
    def __del__(self):
        """
        Last resort cleanup. Pls do .exit() if possible.
        """
        if self.running:
            self.exit()

# The one instance object we will use.
instance = Instance()

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

# We try to start the instance started with the last run's saved params.
instance.start(
    read_params_file()
)

doc = """
[Flask API schema]
409 code: Conflict with current resource state.

Start service: POST /start
- Success
  - 204 (no content)
- Failure
  - 409 {"err": "already running"}

Stop service: POST /stop
- Success
  - 204 (no content)
- Failure
  - 409 {"err": "already stopped"}

Check instance status: GET /status
- Success:
  - 200 {
    "running": true | false,
    "since": <unix_time> | null if never_started,
    "reason": "never_started" | "started" | "stopped" | "crashed",
    "info": null | {"error": "<err>"} if crashed
  }

Query State: GET /state
- Success:
  - 200 {json with state} 
- Failure:
  - 404 {"err": "undefined instance state when instance not running!"}

Query current Params: GET /params
- Success:
  - 200 {json with params}
  - Returns internal saved yaml params, which are guaranteed to be synced with
    the running instance (if there is one).

Set params when service stopped: PUT /params
- Request schema: {json with params}
- Success:
  - 204 (no content)
- Failure:
  - 409 {"err": "not stopped!"}
  - 400 {"err": "<reason why provided params are invalid.>"}

Web endpoint at /docs with this documentation. Root redirects to /docs
"""
from flask import Flask, make_response, redirect, request, jsonify

app = Flask("temp_manager", root_path="./")

@app.route("/")
def root_route():
    """
    It is an API, so we redirect to docs.
    """
    return redirect("/docs")

@app.route("/docs")
def docs_route():
    """
    Route which sends documentation over.
    """
    resp = make_response(doc, 200)
    resp.mimetype = "text/plain"
    return resp

@app.route("/start", methods = ["POST"])
def start_route():
    """
    Route to start the instance.
    """
    if instance.running:
        return jsonify(err = "already running"), 409
    
    params = read_params_file()
    instance.start(params)
    return '', 204

@app.route("/stop", methods = ["POST"])
def stop_route():
    """
    Route to stop the instance.
    """
    if not instance.running:
        return jsonify(err = "already stopped"), 409
    
    instance.exit()
    return '', 204

@app.route("/status", methods = ["GET"])
def is_running_route():
    """
    Route to get system status.
    """
    status = asdict(instance.run_info)
    status = {"running": instance.running, **status}
    return jsonify(status), 200

@app.route("/state", methods = ["GET"])
def get_state_route():
    """
    Route to get instance State (when running).
    """
    if not instance.running:
        return jsonify(
            err = "undefined instance state when instance not running!"
        ), 404
    
    params, state = instance.live_info()
    return jsonify(state), 200

@app.route("/params", methods = ["GET"])
def get_params_route():
    """
    Route to get instance Params.
    """
    params = read_params_file()
    return jsonify(params), 200

@app.route("/params", methods = ["PUT"])
def set_params_route():
    """
    Route to set instance Params.
    Only works if instance is stopped.
    """
    if instance.running:
        return jsonify(err = "not stopped!"), 409
    
    new_params = request.json

    # NOTE: Minimal functional validation!
    if not isinstance(new_params, dict):
        return jsonify(err="invalid json!"), 400

    for key in instance.param_keys:
        if key not in new_params.keys():
            return jsonify(err = f"params needs key {key}!"), 400
    
    for key in new_params.keys():
        if key not in instance.param_keys:
            return jsonify(err = f"params has extra key {key}!"), 400

    write_params_file(new_params)
    return '', 204

app.run(host='0.0.0.0', port = PORT)

log("Shutting down...")

if instance.running:
    instance.exit()