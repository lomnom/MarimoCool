import shared.sock_api as sock_api
import shared.log as make_log
import time

log = make_log.make_log("client")

# Create client
client = sock_api.SockConn("0.0.0.0", 6767)

while True:
    time.sleep(1)
    try:
        response = client.request({"say hi?": True})
    except sock_api.ClosedException:
        response = None
    log(response)