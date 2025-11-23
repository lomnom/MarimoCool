"""
This module defines client and server classes for a lightweight network TCP
stream-based API thru sockets. The API behaves like a REST API. Here,
Start: A client establishes a connection to a server.
Loop: 
1. The client can send requests containing a request body to the server
2. The server responds with a response to the request, containing a response 
   body.
End: The client closes the connection.

Each client is handled in a seperate connection, and in a seperate thread.

Data is serialised to JSON in transit.
"""

import socket
import threading
import json
import atexit

def read_bytes(sock: socket.socket, length: int):
    """Read bytes from a socket. Normal .recv is not guaranteed to return all
    bytes. Returns None if connection closed."""
    data = bytes()
    while len(data) < length:
        new = sock.recv(length - len(data))
        if not new:
            return None
        data += new
    return data

def read_packet(sock: socket.socket) -> "bytes|None":
    """Read a packet from the tcp stream. Returns None if the stream has closed.

    Packet structure:
    -> [3 bytes, big endian: packet size in bytes][Json data]
    
    3 bytes are used to enforce a packet size limit of ~16mb"""
    length_bytes = read_bytes(sock, 3)
    if not length_bytes:
        return None

    length = int.from_bytes(length_bytes, "big")

    return read_bytes(sock, length)

def send_packet(sock: socket.socket, data: bytes):
    """Send a packet to TCP stream."""

    length_bytes = len(data).to_bytes(3, "big")
    body = length_bytes + data
    sock.sendall(body)

def send_json(sock: socket.socket, body: "Any"):
    """Send a python object serialised to json then bytes thru
    a packet."""
    body = json.dumps(body)
    body = body.encode("utf-8")
    send_packet(sock, body)

def get_json(sock: socket.socket):
    """Receive and decode json sent as bytes in TCP stream.
    Returns None if connection is closed already."""
    body = read_packet(sock)
    if body is None:
        return None
    
    body = body.decode("utf-8")
    body = json.loads(body)
    return body

class SockServer:
    """This class runs a REST-like server thru sockets."""
    def __init__(self, port: int):
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.threads = []
        atexit.register(self.close) # Close self on exit to not hang clients.
    
    class Conn:
        """Represents a conection to a client."""
        def __init__(self, conn, addr):
            """Receives the return values of sock.accept."""
            self.conn = conn
            self.addr = addr
        
        def get_request(self) -> "Any":
            """Gets a request from the client. Returns None if connection
            closed."""
            return get_json(self.conn)

        def send_response(self, data: "Any"):
            """Send a response back to the clien"""
            send_json(self.conn, data)

    def conn_manager(self, conn: "Conn"):
        """Receive requests for a connection and call handler function to handle."""
        while True:
            request = conn.get_request()
            if request is None:
                break # Connection closed
            
            try:
                response = self.handler_fn(request)
                conn.send_response(response)
            except Exception as e:
                conn.send_response(f"Internal error {e}.")

    def handler(self, handler_fn):
        """Decorator to set the handler function. The handler function takes a request
        body and returns response body."""
        self.handler_fn = handler_fn

    def run(self):
        """Blocking function. Runs the server. Spawns a new thread running conn_manager
        for each connection."""
        assert(self.handler_fn is not None)

        self.sock.bind(("127.0.0.1", self.port))
        self.sock.listen()

        while True:
            conn, addr = self.sock.accept()
            conn_obj = self.Conn(conn, addr)
            handler_thread = threading.Thread(
                target=self.conn_manager, 
                args=(conn_obj, ), 
                daemon = True # daemon means it is killed automatically when main exits.
            )
            handler_thread.start()
    
    def close(self):
        """Close socket."""
        self.sock.close() 

class SockConn:
    """This class allows connection to a server with SockServer."""
    def __init__(self, addr: str, port: int):
        """Takes in ipv4 address & port, connects to server"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((addr, port))
        atexit.register(self.close) # Close self on exit to not hang server.

    def close(self):
        """Close connection to server"""
        self.sock.close()

    def request(self, body: "Any") -> "Any":
        """Send a request to the server. Returns the response.
        Blocks till response arrives. It is UNSAFE to make multiple
        requests concurrently!"""
        send_json(self.sock, body)

        return get_json(self.sock)