# Raspberry Pi Pico W IOT Antenna Rotator Control

This project uses a Raspberry Pi Pico W to internet-enable a antenna 
rotator controller that has a RS-232 interface.

I used it for my Hy-Gain Ham IV rotator.  My Hy-Gain rotator control
box has been modified to allow computer control with the addition of a
Ham Supply/Idiom Press *Rotor-EZ* module.  I further hacked the rotator
to provide +5 Volts on Pin 1 (carrier detect) of the RS-232 interface.
This allows the Raspberry Pi Pico W to leech power from the rotator
control box.

There is very little external hardware required.  The most important
other piece is a MAX3232 3.3 volt RS-232 interface.  (I am actually 
using the 5-volt version, MAX232 in my prototype.)  The MAX3232 is
used to interface the 3.3 volt logic of the Raspberry Pi Pico W to the
RS-232 levels presented by the antenna rotator.

I used the "Thonny" IDE to load the python source code and template
files onto the Pico W.

Notes:  this repo does not include the file *settings.py* as it contains
the SSID and password for my wireless network.  It looks like this:

```python
#
# settings -- DO NOT COMMIT YOUR SECRETS TO GIT!
#

SSID = 'put your network SSID here'
SECRET = 'put your network password here.'

```