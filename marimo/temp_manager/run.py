"""
Run this file to run temp_manager. The temp_manager service is 
responsible for controlling fan & peltier to regulate tank temperature
within a specific temperature range.

Access to peripherals is done thru gpio_service. Any change to configuration
is propagated through a sock_api to keep the service lightweight.
"""

from yaml import safe_load as yaml_load
with open("storage/temp_manager/settings.yaml") as file:
    settings = yaml_load(file)
PORT = settings["port"]
GPIO_PORT = settings["gpio_addr"]["port"]
GPIO_addr = settings["gpio_addr"]["addr"]

# The system has two states, cooling and idle.
# -> The system starts at cooling
# -> When cooling:
# - Peltier is on
# - If the temperature < low, change to "heating".
# -> When idle:
# - Peltier is off.
# - If the temperature >= high, change to "cooling"

# The fan stays on for fan_retain seconds 

# If disabled is true, the system will turn off fan and peltier,
# and give control back to other programs.

class Params:
    """Dataclass, represents the current parameters of the cooler."""
    disabled: bool
    low: float 
    high: float
    fan_retain: float

PARAMS_HEADER = """# This is loaded on startup of temp_manager
# Change the params thru the API when temp_manager is running.
# API updates will also update this file
"""

def read_params_file() -> Params:
    """Read the params file to a params object"""
    with open("storage/temp_manager/params.yaml") as file:
        params = yaml_load(file)
    return Params(
        disabled = params["disabled"],
        low = params["low"],
        high = params["high"],
        fan_retail = params["fan_retain"]
    )

def write_params_file(params: Params):
    """Write params to the params file."""
    data = params.as_dict()

def regulate_loop():
