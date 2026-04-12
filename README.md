# Raspberry Pi Python Scalextric Lap Timer
A Python3 based Scalextric lap timer dashboard built on the Raspberry Pi using the Tkinter and GPIO libraries

This is a personal Raspberry Pi 3b project I have been working on for a couple of weeks. My son recently got a Scalextric Sport set with the Arc One base plate. It's not bad, the Android App is 'OK' but fun is limited when you are looking at a small 5" screen to see your lap time or who is leading the race.

I thought I could do better and make a full screen race control dashboard using the Pi, some Reed sensors and a little Python 3 magic.

The basis of the timer is derived from: http://code.activestate.com/recipes/578666-stopwatch-with-laps-in-tkinter/ but modified to make it better, with an independant timer for each lane. GPIO integration to trigger a lap and more.

It's early days, and I will be extending this dashboard further in the coming weeks with a better UI that defaults to full screen so you can run this on a big TV or monitor at 1080p

### Pre-requisities:
* Reaspberry Pi (40 pin version to follow my setup but will work on and Pi)
* Breadboard + wires etc...
* 1KΩ and 10KΩ resistors
* 2 Reed sensors - Sealed / pre-wired ones are best like these: http://ebay.eu/2kwWhZ7
* Python3
* Tkinter Library installed
* GPIO Library installed
* Run the .py file under `sudo`
* Scalextric Track
* 2 Slot cars with Magnatraction (magnets on the chasis)

## Text-to-Speech (TTS) Setup

The dashboard can announce lap times and race positions out loud using text-to-speech. This is useful so you can keep your eyes on the track instead of the screen.

**What it does:**
* **Time Trial mode** — speaks the lap time after each lap (e.g. *"3 point 4 5 2"*)
* **Race mode** — announces *"Lane 1 in the lead"* or *"Lane 2 in the lead"* every time the leader completes a lap

**Setup on the Raspberry Pi:**

1. Install the system TTS engine (may already be installed on Raspberry Pi OS):
   ```bash
   sudo apt install -y espeak
   ```

2. Install the Python dependency:
   ```bash
   cd ~/Code/Raspberry-Pi-Python-Scalextric-Lap-Timer
   .venv/bin/pip install pyttsx3
   ```

3. Test that audio works:
   ```bash
   .venv/bin/python -c "import pyttsx3; e = pyttsx3.init(); e.say('test'); e.runAndWait()"
   ```
   You should hear "test" through the Pi's audio output. If not, check your audio config with `raspi-config` → System Options → Audio, or adjust volume with `amixer`.

**Usage:** Press the **TTS** button in the dashboard to toggle speech on or off. It is off by default. The button highlights purple when active.

## Raspberry Pi Fritzing diagram
![Fritzing](https://raw.githubusercontent.com/philm400/Raspberry-Pi-Python-Scalextric-Lap-Timer/master/docs/img/Scalextric-Reed-Swtichs_diagram.png?raw=true)
