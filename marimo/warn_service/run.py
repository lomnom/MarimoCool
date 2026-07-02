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
for name in ["cold", "hot", "on", "err"]:
    with open(f"storage/warn_service/msg_{name}.json") as file:
        messages[name] = file.read()

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
    error = 3

def send(name: str, *args: tuple):
    """
    Send a message through the webhook.
    Name is one of messages.keys()
    %s substitutions only allowed within quotes.
    """
    # Stop JSON injection.
    raw_args = args
    args = []
    for item in raw_args:
        item = str(item)
        item = item.replace("\\", "\\\\")
        item = item.replace("\"", "\\\"")
        args.append(item)
    args = tuple(args)
    
    try:
        result = requests.post(
            WEBHOOK, 
            json = json.loads(messages[name] % args)
        )
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
limit = 24 # Boundary between hot and cold
def tick():
    """
    A tick where the temperature is fetched and messages may be sent. 
    """
    global temps, state

    # Update internal temp
    try:
        response = gpio.request({"name": "tank_temp", "operation": "read"})
    except Exception as e:
        response = f"Internal error: GPIOService unreachable; {repr(e)}"

    if type(response) is str and response.startswith("Internal error"):
        log(f"GPIOService server error: {response}")
        if not state == State.error:
            state = State.error
            send("err", "Temperature sensor cannot be read!", response)
        return
    
    temps.insert(0, response)
    temps = temps[:6]
    temp = max(temps)

    # Send messages based on state change based on internal temp
    if temp <= limit:
        new_state = State.cold 
    else:
        new_state = State.hot

    if new_state != state:
        # State change!
        state = new_state
        if new_state == State.cold:
            send("cold", limit, temp)
        elif new_state == State.hot:
            send("hot", limit, temp)

def main():
    """
    Program entrypoint.
    """
    send("on")
    while True:
        sleep(10)
        try:
            tick()
        except Exception as e:
            send("err", "Warn service tick failed!", f"{repr(e)}")

main()