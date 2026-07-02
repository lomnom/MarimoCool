from flask import Flask, make_response, redirect, request, jsonify, render_template
from yaml import safe_load as yaml_load
import shared.sock_api as sockapi
import shared.log as make_log
import requests
from datetime import datetime
import time
import threading
import copy

log = make_log.make_log("web-service")

## Get interfaces
with open("storage/web_service/settings.yaml") as file:
    settings = yaml_load(file)

client = sockapi.SockConn(
    settings["gpio_addr"]["addr"], settings["gpio_addr"]["port"]
)

manager_url = f"http://{settings['temp_manager']['addr']}:{settings['temp_manager']['port']}"

## History manager
class History:
    """
    Fetches a temperature reading every per_sample minutes.
    Keeps the last n_samples readings.
    """
    def __init__(self, per_sample: float, n_samples: int):
        """Construct. Does not start manager."""
        self.per_sample = per_sample
        self.n_samples = n_samples
        self.log = []

        self.halt_lock = threading.Lock()
        self.log_lock = threading.Lock()
    
    def get_sample(self):
        """
        Get a sample now.
        """
        with self.log_lock:
            try:
                temp = client.request({"name": "tank_temp", "operation": "read"})
            except Exception as e:
                temp = f"gpio_service unreachable: {repr(e)}"
            # if temp is str, it is an error message
            # float means it is an actual temperature.

            # Add sample, rotate log.
            self.log.insert(
                0,
                (datetime.now(), temp)
            )
            self.log = self.log[:self.n_samples]
            log(f"Collected a sample {temp}")
    
    def get_log(self) -> list:
        """
        Get full log.
        Will wait for current sample to finish collecting, if any.
        """
        with self.log_lock:
            return copy.deepcopy(self.log)
    
    def sampler(self):
        """Thread that collects samples."""
        point = time.perf_counter()
        target = point
        while not self.halt_lock.locked():
            self.get_sample()

            target += self.per_sample * 60
            wait = target - time.perf_counter()
            if wait <= 0:
                log(f"Lagging behind on samples by {wait}s!")
            
            while wait > 0:
                time.sleep(min(wait, 1))
                # Dont wait the whole waiting time before quitting.
                if self.halt_lock.locked():
                    break
                
                wait = target - time.perf_counter()
        
        self.halt_lock.release() # Signal success to stop()
    
    def start(self):
        """Start sample collection thread"""
        thread = threading.Thread(target = self.sampler)
        thread.start()
    
    def stop(self):
        """Stop sample collection thread."""
        self.halt_lock.acquire()
        self.halt_lock.acquire()

per_sample = settings["history"]["per_sample"]
n_samples = settings["history"]["n_samples"]

history = History(per_sample, n_samples)
history.start()
log("History collector started.")

graph_low = settings["graph"]["low"]
graph_division = settings["graph"]["division"]
graph_char = settings["graph"]["char"]

## Routes
app = Flask(__name__)

@app.route("/")
def index():
    # Get tank temperature
    try:
        temp = client.request({"name": "tank_temp", "operation": "read"})
    except Exception as e:
        return render_template("down.html", message = f"gpio_service unreachable! Err: {repr(e)}")
    
    # Query temp_manager status & state (if running)
    try:
        status = requests.get(manager_url + "/status").json()
    except Exception as e:
        return render_template("down.html", message = f"temp_manager unreachable! Err: {repr(e)}")

    if status["since"]:
        timestamp = datetime.fromtimestamp(status["since"])
        since = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    else:
        since = "never" # never_started

    extra_params = {}

    if status["running"]:
        state = requests.get(manager_url + "/state").json()
        extra_params["phase"] = state["phase"]
    elif status["reason"] == "crashed":
        extra_params["error"] = status["info"]

    # Put history there.
    entries = []
    for item in history.get_log():
        timestamp, reading = item
        time_str = timestamp.strftime("%I:%M%p")
        if type(reading) is str:
            # Error reading
            info = "Err 💀"
            bar = reading
        else:
            info = f"{reading}°C"
            bar = round((reading - graph_low)/graph_division) * graph_char
            
        entries.append(
            ['[', time_str, '⏐', info, ']', bar]
        )
    
    # Render
    return render_template(
        "index.html", 
        temp = temp, 
        running = status["running"],
        status_change = since,
        reason = status["reason"],
        history = entries,
        **extra_params
    )

app.run("0.0.0.0", port=settings["port"])

# Stop history collector
log("Stopping history collector...")
history.stop()
log("History collector stopped.")