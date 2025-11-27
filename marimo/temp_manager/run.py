"""
Run this file to run temp_manager.

Temp_manager regulates the temperature of the temp, and has
an accompanying API that is used to query its state, and start and
stop the service. Parameters can also be changed when it is stopped.

This file contains the API used to interact with the manager. The manager 
is defined in ./manager.py
"""
import temp_manager.manager as temp
import shared.sock_api as sock_api
import threading
import shared.log as make_log
log = make_log.make_log("temp-overseer")

## The server

server = sock_api.SockServer(PORT)

@server.handler
def handle_req(req_body: "Any", addr: "str") -> "Any":
    """
    Request format: {"request": ..., "data": ...}, where data key is optional.
    Response format: return value or "Internal error [...]"

    Requests that are always valid:
    - request = get_params -> returns current manager parameters (dict)
    - request = get_state -> returns a dictionary representing manager State
      - Returns null/none if manager is not running.

    Valid requests when service is running:
    - request = stop -> stops the manager ; returns OK

    Valid requests when service is stopped:
    - request = start -> starts the manager ; returns OK
    - request = set_params, data = {dictionary with Params} -> Updates params. ; returns OK

    Note: Exceptions are forwarded back to client thru sock_server
    """
    request = req_body["request"]

    if request == "get_params": 
        return get_params()
    elif request == "get_state":
        state = get_state()
        if state is None:
            return None
        else:
            return state
    elif request == "stop":
        stop_manager()
        return "OK"
    elif request == "start":
        start_manager()
        return "OK"
    elif request == "set_params":
        data = req_body["data"]
        set_params(data)
        return "OK"


server.run() # In main thread.