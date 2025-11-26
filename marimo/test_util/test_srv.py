import shared.sock_api as sock_api

# Create server
server = sock_api.SockServer(6767)
sock_api.do_log = True

@server.handler
def handle_req(req_body: "Any", addr: "str") -> "Any":
    print("Request!")
    return "Hello :)"

server.run()