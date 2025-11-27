from yaml import safe_load as yaml_load
from yaml import dump as yaml_dump

PARAMS_FILE = "storage/temp_manager/params.yaml"

"""
The params file is to save the params of the manager so that it can
be restored on the next start.

The params in the manager are not to be touched. The service should
be stopped before the params are updated, both internal and file.
"""

def read_params_file() -> Params:
    """Read the params file to a params object."""
    with open(PARAMS_FILE) as file:
        new_params = yaml_load(file)
    return Params(
        **new_params
    )

PARAMS_HEADER = """# This is loaded on startup of temp_manager
# Change the params thru the API when temp_manager is running.
# API updates will also update this file
"""

def write_params_file(new_params: Params):
    """Write params to the params file."""
    data = asdict(new_params)
    written = PARAMS_HEADER + yaml_dump(data)
    with open(PARAMS_FILE, 'w') as file:
        file.write(written)