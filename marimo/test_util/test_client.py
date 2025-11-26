import shared.sock_api as sock_api
import time

# Create client
client = sock_api.SockConn("0.0.0.0", 6767)

while True:
    time.sleep(1)
    try:
        response = client.request({"say hi?": True})
    except sock_api.ClosedException:
        response = None
    print(response)