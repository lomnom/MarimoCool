"""
An adaptor to connect to GPIOService remotely.
Takes in addr from commandline arguments.
python [blabla] addr port
"""

from sys import argv
import shared.sock_api as sock_api

# Arguments
_, addr, port = argv
port = int(port)

# Connection
gpio = sock_api.SockConn(addr, port)

def gpio_req(body: "Any") -> "Any":
    """
    Send a request to GPIOService.
    sock_api.BrokenException if server is unreachable.
    RuntimeError if internal service error.
    """
    response = gpio.request(body)
    if type(response) is str and response.startswith("Internal error"):
        raise RuntimeError(f"GPIOService server error {response}")
    else:
        return response