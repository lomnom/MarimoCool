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
import shared.log as log

# NOTE: All this code currently assumes all packets are well-structured and graceful close will be called.
# NOTE: All code assumes that the connection will not be closed anywhere between request --> process --> response.
# NOTE: Assumes json packets have valid json.
# NOTE: Malicious actors that are not well-behaved can easily exploit this to DOS.
# wow thats why ppl just use flask for everything oh my days
# we still need this for lightewightness.

class ClosedException(Exception):
    """Raised to signal a closed connection."""
    def __init__(self, message = ""):
        self.message = message
        super().__init__(self.message)

def read_bytes(sock: socket.socket, length: int) -> bytes:
    """Read bytes from a socket. Normal .recv is not guaranteed to return all
    bytes. Raises ClosedException if connection closed."""
    data = bytes()
    while len(data) < length:
        try:
            new = sock.recv(length - len(data))
        except (BrokenPipeError, ConnectionResetError, OSError):
            raise ClosedException() # Other close methods

        if not new:
            raise ClosedException() # Client closed gracefully

        data += new
    return data

def read_packet(sock: socket.socket) -> bytes:
    """Read a packet from the tcp stream. Raises ClosedException
    if the stream has closed.

    Packet structure:
    -> [3 bytes, big endian: packet size in bytes][Json data]
    
    3 bytes are used to enforce a packet size limit of ~16mb"""
    length_bytes = read_bytes(sock, 3) # throws ClosedException if closed

    length = int.from_bytes(length_bytes, "big")

    return read_bytes(sock, length)

def send_packet(sock: socket.socket, data: bytes):
    """Send a packet to TCP stream. Raises ClosedException
    if connection closed."""

    length_bytes = len(data).to_bytes(3, "big")
    body = length_bytes + data
    try:
        sock.sendall(body)
    except (BrokenPipeError, ConnectionResetError, OSError):
        raise ClosedException()

def send_json(sock: socket.socket, body: "Any"):
    """Send a python object serialised to json then bytes thru
    a packet."""
    body = json.dumps(body)
    body = body.encode("utf-8")
    send_packet(sock, body)

def get_json(sock: socket.socket) -> "Any":
    """Receive and decode json sent as bytes in TCP stream.
    Raises ClosedException if connection is closed already."""
    body = read_packet(sock) # raises ClosedException if closed
    
    body = body.decode("utf-8")
    body = json.loads(body)
    return body

SRV_LOG = log.make_log("sock-server") # Logging function for server

class SockServer:
    """This class runs a REST-like server thru sockets."""
    def __init__(self, port: int, external = True):
        """Set external to False to only be accessible on same machine,
        True to expose to network."""
        self.port = port
        self.external = external
        self.sock = None
        self.threads = []
        atexit.register(self.close) # Close self on exit to not hang clients.
    
    class Conn:
        """Represents a conection to a client."""
        def __init__(self, conn, addr):
            """Receives the return values of sock.accept."""
            self.conn = conn
            self.addr = addr
        
        def close(self):
            """Close the connection to client."""
            self.conn.close()
        
        def get_request(self) -> "Any":
            """Gets a request from the client. Raises ClosedException if connection
            closed."""
            return get_json(self.conn)

        def send_response(self, data: "Any"):
            """Send a response back to the client. Raises ClosedException if conn
            closed."""
            send_json(self.conn, data)

    def conn_manager(self, conn: "Conn"):
        """Receive requests for a connection and call handler function to handle.
        Exceptions are sent back as "Internal error {repr(e)}" """
        SRV_LOG(f"Connection made with {conn.addr}")

        while True:
            try:
                request = conn.get_request()
            except ClosedException:
                break
            
            SRV_LOG(f"Request from {conn.addr}: {request}")
            try:
                response = self.handler_fn(request, conn.addr)
                conn.send_response(response)
            except Exception as e:
                SRV_LOG(f"Internal error on request {conn.addr}: {request}, {repr(e)}")
                conn.send_response(f"Internal error {repr(e)}.")
            
        SRV_LOG(f"Connection with {conn.addr} ended")

    def handler(self, handler_fn):
        """Decorator to set the handler function. The handler function takes a request
        body and addr as handler_fn(body, addr) and returns response body."""
        self.handler_fn = handler_fn

    def run(self):
        """Blocking function. Runs the server. Spawns a new thread running conn_manager
        for each connection."""
        assert(self.handler_fn is not None)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        addr = "0.0.0.0" if self.external else "127.0.0.1"
        self.sock.bind((addr, self.port))
        self.sock.listen()

        SRV_LOG(f"Server now running at {addr}:{self.port}")

        while True:
            conn, addr = self.sock.accept()
            conn_obj = self.Conn(conn, addr)
            handler_thread = threading.Thread(
                target=self.conn_manager, 
                args=(conn_obj, ), 
                daemon = True # daemon means it is killed automatically when main exits.
            )
            handler_thread.start()
            self.threads.append((
                handler_thread,
                conn
            ))
    
    def close(self):
        """Close socket. Used for cleanup on termination."""
        self.sock.close() # Stop listening
        for thread, conn in self.threads:
            conn.close() # Close client connection, which also closes thread.
            thread.join()
        SRV_LOG("Server closed")

CLI_LOG = log.make_log("sock-client") # Logging function for client

class SockConn:
    """This class allows interfacing with a SockServer."""
    def __init__(self, addr: str, port: int):
        self.addr = addr
        self.port = port
        self.conn = None
        self.req_lock = threading.Lock() # Enforce synchronous requesting.
        atexit.register(self.close) # Close current conn on exit to not hang server.
    
    def request(self, body: "Any") -> "Any":
        """Make a request to the server. Raises ClosedException if server unavailable.
        unreachable."""
        with self.req_lock:
            try:
                # We basically reuse a cached connection, and try to reconnect if it is invalid.
                if self.conn is None:
                    # No cached connection
                    raise ClosedException()
                else:
                    # Raises ClosedException if conn closed.
                    response = self.conn.request(body)
                    return response
            except ClosedException:
                # Signals that we need to reconnect.
                # Either conn closed or we have no cached connection.
                CLI_LOG(f"Reconnecting to {self.addr}:{self.port}")
                self.conn = None

                try:
                    self.conn = self.Conn(self.addr, self.port)
                except:
                    CLI_LOG(f"Connection to {self.addr}:{self.port} failed.")
                    raise ClosedException() # Reconnection failed.

                # Basically guaranteed to not throw ClosedException if conn forms.
                retry = self.conn.request(body)
                return retry
        
    def close(self):
        """Closes current connection to server"""
        if self.conn is not None:
            self.conn.close()
            CLI_LOG(f"Connection to {self.addr}:{self.port} closed.")

    class Conn:
        """This class represents a connection to a SockServer"""
        def __init__(self, addr: str, port: int):
            """Takes in ipv4 address & port, connects to server.
            Propagates exceptions if connection fails."""
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((addr, port))

        def close(self):
            """Close connection to server"""
            self.sock.close()

        def request(self, body: "Any") -> "Any":
            """Send a request to the server. Returns the response.
            Blocks till response arrives. It is UNSAFE to make multiple
            requests concurrently!
            Raises ClosedException if the connection is closed."""
            
            send_json(self.sock, body)
            return get_json(self.sock)