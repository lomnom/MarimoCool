"""
Defines the standard logging function.
"""
from time import perf_counter
import threading

log_lock = threading.Lock()

START = perf_counter()
def make_log(purpose: str) -> "function":
    """Returns a logging function that logs for a purpose.
    Logs are printed in form [    time] purpose > """
    def log(*args, **kwargs):
        """Logs messages with a timestamp since startup. Same syntax as print."""
        timestamp = perf_counter() - START
        timestamp = round(timestamp, 2)
        timestamp = str(timestamp).ljust(8, " ") + "s"
        timestamp = f"[{timestamp}]" 
        timestamp = "\033[2m" + timestamp + "\033[22m" # make dim.

        purpose_str = purpose
        purpose_str = "\033[2;1m" + purpose + "\033[22;21m" # dim + bold
        with log_lock:
            print(timestamp, purpose_str, '>', *args, **kwargs)
    return log