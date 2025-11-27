"""
This file is a higher-level runner for core_run which implements:
1. Starting and stopping core_run
2. Saving previous params to reuse on startup
3. Exposing a sock_api that can:
    - Query State
    - Query current Params
    - Stop service
    - Start service
    - Update params when service stopped
    - Retreive how many ticks ago the last error was and 
      the last 25 error messages, with how many ticks ago they are individually.
"""

from yaml import dump as yaml_dump
from yaml import safe_load as yaml_load
with open("storage/temp_manager/settings.yaml") as file:
    settings = yaml_load(file)
PORT = settings["port"]

## Params file utils
PARAMS_FILE = "storage/temp_manager/params.yaml"

"""
The params file is to save the params of the manager so that it can
be restored on the next start.

The params in the manager are not to be touched. The service should
be stopped before the params are updated, both internal and file.
"""

def read_params_file():
    """Read the params file."""
    with open(PARAMS_FILE) as file:
        new_params = yaml_load(file)
    return Params(
        **new_params
    )

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
params = read_params_file()
