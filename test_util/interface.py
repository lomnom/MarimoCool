"""
This file initialises sensors and devices connected to the pi,
and exposes methods to read from sensors and control devices.
"""

import RPi.GPIO as GPIO
import atexit
import os
import re

### Global initialisation for all devices & sensors
def global_setup():
    GPIO.setmode(GPIO.BCM)

global_setup()

### Superclasses

class Peripheral:
    """
    Superclass for all peripherals
    """
    def setup(self):
        """
        Sets up peripheral. Functions which act on the peripheral
        should work after setup() is called. 
        Should be called in the constructor.
        """
        raise NotImplementedError

class Sensor(Peripheral):
    """
    Superclass for all sensors.
    Sensors have a reading you can read.
    """
    def read(self):
        """
        Returns sensor reading.
        """
        raise NotImplementedError

class Device(Peripheral):
    """
    Superclass for all devices.
    Devices have an "on" state and an "off" state.
    """
    def is_on(self) -> bool:
        """
        Returns True if device is on, False otherwise.
        """
        raise NotImplementedError
    
    def turn_on(self):
        """
        Turns device on
        Must not have side effects if device is on already.
        """
        raise NotImplementedError
    
    def turn_off(self):
        """
        Turns device off
        Must not have side effects if device is off already.
        """
        raise NotImplementedError

### Actual sensor & device definitions
## Relays
class Relay(Device):
    """Class for a relay device
    The device must be active-low."""
    def __init__(self, pin: int):
        """Constructor for Relay.
        Takes in pin number for relay switching."""
        self.pin = pin
        self.setup()
    
    def setup(self):
        """Set up relay GPIO"""
        GPIO.setup([self.pin], GPIO.OUT, initial=GPIO.HIGH) # Initialise off
        self.state = False
    
    def turn_on(self):
        """Turn on relay"""
        GPIO.output(self.pin, GPIO.LOW)
        self.state = True
    
    def turn_off(self):
        """Turn off relay"""
        GPIO.output(self.pin, GPIO.HIGH)
        self.state = False
    
    def is_on(self) -> bool:
        """True if relay is on, False otherwise."""
        return self.state

class TankTemp(Sensor):
    """Sensor for temperature inside the tank."""
    def __init__(self):
        """Constructor for TankTemp"""
        self.setup()
    
    # Folder that contains sensor folder, like 28-3ce104574f79
    SYS_SENSOR_DIR = "/sys/bus/w1/devices" 
    def setup(self):
        sensors = [
            item for item in os.listdir(self.SYS_SENSOR_DIR) 
                if item.startswith("28")
        ]
        # If a sensor has family code 28 (ie. folder name like 28-3ce104574f79),
        # it is a DS18B20. This is what we use in the tank.

        assert(len(sensors) == 1) # 0 -> No sensor, >1 -> multiple sensors.

        # Data file ends with t=[temp in C * 1000]
        self.data_file = f"/sys/bus/w1/devices/{sensors[0]}/w1_slave"
    
    DATAFILE_RE = re.compile(r"t=([0-9]+)")
    def read(self) -> float:
        """Read tank temperature sensor. 
        Returns float, the temperature in C"""
        with open(self.data_file, "r") as data_file:
            data = data_file.read()
        
        result = self.DATAFILE_RE.search(data)
        return float(result.group(1)) / 1000

### Exported sensors & devices
## Relays
PELTIER_RELAY = 26 
FAN_RELAY = 21

peltier = Relay(PELTIER_RELAY)
fan = Relay(FAN_RELAY)

tank_temp = TankTemp()

PERIPHERALS = {
    "peltier": peltier,
    "fan": fan,
    "tank_temp": tank_temp
}

### Global exit hook
def global_exit():
    GPIO.cleanup()

atexit.register(global_exit)