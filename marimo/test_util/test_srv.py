import shared.sock_api as sock_api
import shared.log as make_log

log = make_log.make_log("server")

# Create server
server = sock_api.SockServer(6767)
sock_api.do_log = True

@server.handler
def handle_req(req_body: "Any", addr: "str") -> "Any":
    log("Request!")
    return "Hello :)"

server.run()