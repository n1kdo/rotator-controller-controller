# Raspberry Pi Pico W IOT Antenna Rotator Controller Controller

This project uses a Raspberry Pi Pico W to internet-enable a antenna 
rotator controller that has a RS-232 interface.

![](rotator_controller_controller.png)

I used it for my Hy-Gain Ham IV rotator.  My Hy-Gain rotator control box has been modified to allow computer
control with the addition of a Ham Supply/Idiom Press *Rotor-EZ* module.  I further modified the rotator
control box to provide +5 Volts on Pin 1 (carrier detect) of the DE-9S RS-232 interface.  This allows the 
Raspberry Pi Pico W to rob power from the rotator control box.

There is very little external hardware required.  The most important other piece is a MAX3232 3.3 volt 
RS-232 level converter.  The MAX3232 is used to interface the 3.3 volt logic of the Raspberry Pi Pico W to
the RS-232 levels required by the antenna rotator control box.

## Installing MicroPython on your Pico-W

1. Download the latest "nightly" build of MicroPython from https://micropython.org/download/rp2-pico-w/ -- it
   will have a name similar to `v1.19.1-409-g0e8c2204d (2022-09-14) .uf2`
2. Connect a micro-USB cable to your PC.  Hold down the white "BOOTSEL" button on the Pico-W, and insert the
   micro-USB cable into your Pico-W.
3. The Pico-W should appear as a USB storage device on your computer.  On mine, it shows up as "RPI-RP2 (F:)".
4. Copy/Paste the MicroPython .uf2 file to this drive.
5. Disconnect the Pico-W and prepare for the next step.

## Installing this software onto the Pico-W

The easiest way to get this software installed onto your Pico-W is to use the `loader.py` tool, also
provided in this repository.

1. Download Python 3 from https://www.python.org/downloads/ and install it.  Make sure to select "Add 
   Python 3 to Path."
2. Download the contents of this GitHub repository as a zip.  Use this URL: 
   `https://github.com/n1kdo/rotator-controller-controller/archive/refs/heads/master.zip`
3. Unpack that zip file somewhere. 
4. Open a command prompt.  (your choice.  Could be PowerShell, could be good ole CMD.)
5. From the command line, execute the following command: `pip install pyserial` -- this will install the Python 
   serial port support/
6. Change directory to where you unpacked the GitHub zip file, and then
   change directory to the `src/loader` directory.
7. From the command line, execute the following command: `python loader.py` -- this will install all the rotator
   controller-controller software onto the Pico-W.

If you want to experiment, you can use the open-source "Thonny" IDE to load the python source code and HTML files
onto the Pico W.  Unfortunately, Thonny cannot load the binary file `compass-background.png` image file into the
proper location, but this can be worked around by using the "upload" feature in the controller-controller software.

## What is all this stuff?

Important files:

* src/pico-w/main.py -- the main Python application
* src/pico-w/pico_rotator.py -- a Python module that queries and commands the rotator controller on the Pico-W
* src/pico-w/windows_rotator.py -- a Python module that queries and commands the rotator controller on Linux and
  Windows.  Used for development and testing
* src/pico-w/content/rotator.html -- the rotator control web page
* src/pico-w/content/setup.html -- the setup web page
* src/pico-w/content/files.html -- the file upload/download web page
* src/pico-w/data/config.json -- the configuration file.  automatically generated on first use if not present.

Other Stuff:

* src/loader/loader.py -- small Python application installs the six files above onto the Pico-W
* src/loader/pyboard.py -- patched pyboard library from Micropython. Patched to work on Pico-W.

Electronic Design Files:

* kicad/* -- Kicad 6 design files for schematic and PCB.

