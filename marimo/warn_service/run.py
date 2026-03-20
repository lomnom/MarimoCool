import requests
from yaml import safe_load as yaml_load
import shared.log as make_log
import shared.sock_api as sock_api
import json
from time import sleep
from enum import Enum

log = make_log.make_log("warn-service")

# Get messages
messages = {}
for name in ["cold", "hot", "on"]:
    with open(f"storage/warn_service/msg_{name}.json") as file:
        messages[name] = json.loads(file.read())

# Load settings
with open("storage/warn_service/settings.yaml") as file:
    settings = yaml_load(file)
GPIO_PORT = settings["gpio_addr"]["port"]
GPIO_ADDR = settings["gpio_addr"]["addr"]
WEBHOOK = settings["webhook_url"]

# Connect to gpio
gpio = sock_api.SockConn(GPIO_ADDR, GPIO_PORT)

# Take true temperature to be the max over last 6 readings (1 minute)
# Take one reading every tick, ie. every 10 seconds

temps = []
class State(Enum):
    nothing = 0
    cold = 1
    hot = 2

def send(name: str):
    """
    Send a message through the webhook.
    Name is one of messages.keys()
    """
    try:
        result = requests.post(WEBHOOK, json = messages[name])
    except requests.exceptions.ConnectionError:
        log("Internet not connected! Message could not send. Retrying in 30 seconds...")
        sleep(30)
        send(name)

    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        log("HTTP error!", err)
    except:
        log("Other error faced!")
    else:
        log(f"Message `{name}` sent successfully!")

state = State.nothing
def tick():
    """
    A tick where the temperature is fetched and messages may be sent. 
    """
    global temps, state

    # Update internal temp
    response = gpio.request({"name": "tank_temp", "operation": "read"})
    if type(response) is str and response.startswith("Internal error"):
        log(f"GPIOService server error: {response}")
        return
        # TODO: A warning for this.
    
    temps.insert(0, response)
    temps = temps[:6]
    temp = max(temps)

    # Send messages based on state change based on internal temp
    if temp <= 24:
        new_state = State.cold 
    else:
        new_state = State.hot

    if new_state != state:
        # State change!
        state = new_state
        if new_state == State.cold:
            send("cold")
        elif new_state == State.hot:
            send("hot")

def main():
    """
    Program entrypoint.
    """
    send("on")
    while True:
        sleep(10)
        tick()

main()