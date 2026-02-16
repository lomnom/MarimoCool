from flask import Flask, make_response, redirect, request, jsonify, render_template
from yaml import safe_load as yaml_load
import shared.sock_api as sockapi
import shared.log as make_log
import requests
from datetime import datetime

log = make_log.make_log("web-service")

## Get interfaces
with open("storage/web_service/settings.yaml") as file:
    settings = yaml_load(file)

client = sockapi.SockConn(
    settings["gpio_addr"]["addr"], settings["gpio_addr"]["port"]
)

manager_url = f"http://{settings['temp_manager']['addr']}:{settings['temp_manager']['port']}"

## Get flask object
# Get flask path in storage (Here/../storage/web_service/)
import os

marimo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
base_dir = os.path.join(marimo_dir, "storage", "web_service")

app = Flask(__name__)
app.config["APPLICATION_ROOT"] = base_dir

## Routes
@app.route("/")
def index():
    # Get tank temperature
    try:
        temp = client.request({"name": "tank_temp", "operation": "read"})
    except sockapi.ClosedException:
        return render_template("down.html", message = "gpio_service unreachable!")
    
    # Query temp_manager status & state (if running)
    try:
        status = requests.get(manager_url + "/status").json()
    except requests.exceptions.ConnectionError:
        return render_template("down.html", message = "temp_manager unreachable!")

    timestamp = datetime.fromtimestamp(status["since"])
    since = timestamp.strftime("%Y-%m-%d %H:%M:%S")

    if status["running"]:
        state = requests.get(manager_url + "/state").json()
        return render_template(
            "index.html", 
            temp = temp, 
            running = status["running"],
            status_change = since,
            phase = state["phase"]
        )
    else:
        return render_template(
            "index.html", 
            temp = temp, 
            running = status["running"],
            status_change = since,
            reason = status["info"]
        )

app.run("0.0.0.0", port=settings["port"])