## Pi details
Hostname: marimo
Password: blubblubball

Ip found with `sudo nmap -sn --disable-arp-ping -R 192.168.50.0/24`.

Ip: 192.168.50.17

## Temperature sensor
Tutorial: [link](https://pimylifeup.com/raspberry-pi-temperature-sensor/)

### First setup
1. Assemble circuit, attach temp sensor data line to pin 4
2. Enable one-pin comms by appending `dtoverlay=w1-gpio,gpiopin=4` to `/boot/firmware/config.txt`
3. Reboot to keep changes

### Reading temperature readings
1. In `/sys/bus/w1/devices` there will be a folder like `28-3ce104574f79`.
2. In that folder, there is a file `w1_slave`. Read it, below there is a t=[number].
3. Temperature is equal to t/1000 in celcius.

## Relay
Tutorial: [link](http://wiki.sunfounder.cc/index.php?title=2_Channel_5V_Relay_Module#For_raspberry_pi)

Channel 2 is on 17 and channel 1 is on 18. Beware that 18 starts on a floating, slightly high state!

Important note: Do not use the default gnd and vcc. The relay comes with JD-VCC (relay coils) and VCC (logic). There should be a 3-pin array beside the normal gnd and vcc inputs. Remove the jumper on this array, and connect gnd, JC-VCC to 5v and VCC to 3v. This is to allow the gpio pins to safely toggle the relay without backflow.

It is counterintuitive, but the relay is activated when the GPIO pin is set to LOW. lol.

An example:
```py
import time
import RPi.GPIO as GPIO

relay_channels = {1: 18, 2: 17}
relay_pins = list(relay_channels.values())

def setup():
	GPIO.setmode(GPIO.BCM)
	GPIO.setup(relay_pins, GPIO.OUT, initial=GPIO.HIGH)

def main():
	for channel in relay_channels:
		print(f"Turning on channel {channel}")
		GPIO.output(relay_channels[channel], GPIO.LOW)
		time.sleep(1)
		print(f"Turning off channel {channel}")
		GPIO.output(relay_channels[channel], GPIO.HIGH)
		time.sleep(1)

def end():
	GPIO.output(relay_pins, GPIO.LOW)
	GPIO.cleanup()

setup()
main()
end()
```

## Peltier
Marimo thrive between 20-28c ([source](https://www.mossball.com/basic-marimo-temperature-and-water-requirements/)). Thus, we want to keep the marimo at 23-25C, the mid range. Keeping a steady state will be done with the peltier TEC1-12706 at 12V. 

The side with the printed text is the cold side. 

Thermal paste application tutorial: [link](https://www.youtube.com/watch?v=Sog0M9OrlME)

## Sublime sftp
Getting package manager working: [link](https://github.com/wbond/package_control/issues/1612#issuecomment-1708802315)

## Todo
1. Avoid dew point
2. Turn on fan only when needed