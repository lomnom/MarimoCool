from flask import Flask, make_response, redirect, request, jsonify, render_template
from yaml import safe_load as yaml_load
import shared.sock_api as sockapi
import shared.log as make_log
log = make_log.make_log("web-service")

## Get GPIO instance
with open("storage/web_service/settings.yaml") as file:
    settings = yaml_load(file)

client = sockapi.SockConn(
    settings["gpio_addr"]["addr"], settings["gpio_addr"]["port"]
)

## Get flask path in storage
import os

# Here/../storage/web_service/
marimo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
base_dir = os.path.join(marimo_dir, "storage", "web_service")

app = Flask(__name__)
app.config["APPLICATION_ROOT"] = base_dir

@app.route("/")
def index():
    temp = client.request({"name": "tank_temp", "operation": "read"})
    log(f"Temp is {temp}C")
    return render_template("temp.html", temp = temp)

# log("If server crashes with 'permission denied', try "
# "`sudo setcap CAP_NET_BIND_SERVICE=+eip $(which python)` to allow binding to low ports")

app.run("0.0.0.0", port=settings["port"])