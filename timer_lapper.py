from tkinter import *
from tkinter import messagebox
from threading import Thread, Lock
from queue import Queue, Empty
from pathlib import Path
# from PIL import Image
import RPi.GPIO as GPIO
import time
import struct
import math
import pygame
try:
	import pyttsx3
except ImportError:
	pyttsx3 = None

pygame.init()
pygame.mixer.init()

BASE_DIR = Path(__file__).resolve().parent
SOUNDS_DIR = BASE_DIR / 'sounds'

def load_sound(*candidates):
	for candidate in candidates:
		sound_path = SOUNDS_DIR / candidate
		if sound_path.exists():
			return pygame.mixer.Sound(str(sound_path))
	raise FileNotFoundError('Could not find any sound file in {}: {}'.format(SOUNDS_DIR, ', '.join(candidates)))

def generate_tone(frequency, duration_ms, volume=0.5):
	sample_rate = 44100
	n_samples = int(sample_rate * duration_ms / 1000)
	buf = bytes()
	for i in range(n_samples):
		t = float(i) / sample_rate
		value = int(volume * 32767 * math.sin(2 * math.pi * frequency * t))
		buf += struct.pack('<h', value)
	sound = pygame.mixer.Sound(buffer=buf)
	return sound

SOUND_START = load_sound('startende_race_autos.ogg')
SOUND_LAP = load_sound('Doppler-4.ogg')
SOUND_FINISH = load_sound('finish.mp3', 'finished.ogg')
SOUND_REVVING = load_sound('revving.mp3', 'start-revving.ogg')
SOUND_BEEP_RED = generate_tone(600, 200, volume=0.4)
SOUND_BEEP_GREEN = generate_tone(1000, 800, volume=0.5)
DEFAULT_RACE_LAPS = 3
LIGHTS_INTERVAL_SEC = 0.5
GPIO_BOUNCETIME_MS = 120
MIN_LAP_TRIGGER_INTERVAL_SEC = 0.15
MIN_LAP_TIME_SEC = 1.0
DEBUG_COUNTER_ENABLED = True
DEBUG_COUNTER_UPDATE_MS = 200
race_winner = None
race_laps = DEFAULT_RACE_LAPS
countdown_job = None
countdown_widgets = []

tts_queue = Queue()
tts_enabled = False
tts_lock = Lock()
tts_generation = 0

def _tts_worker():
	engine = pyttsx3.init()
	engine.setProperty('rate', 150)
	while True:
		item = tts_queue.get()
		if item is None:
			break
		generation, text = item
		with tts_lock:
			if not tts_enabled or generation != tts_generation:
				continue
		try:
			engine.say(text)
			engine.runAndWait()
		except Exception:
			pass

_tts_thread = None

def speak(text):
	global _tts_thread
	with tts_lock:
		if not tts_enabled or pyttsx3 is None:
			return
		if _tts_thread is None or not _tts_thread.is_alive():
			_tts_thread = Thread(target=_tts_worker, daemon=False)
			_tts_thread.start()
		tts_queue.put((tts_generation, text))

def format_lap_time_speech(seconds_float):
	"""Format a lap time for speech, e.g. 3.452 -> '3 point 4 5 2'"""
	whole = int(seconds_float)
	frac = '{:.3f}'.format(seconds_float).split('.')[1]
	digits = ' '.join(frac)
	if whole == 0:
		return 'point {}'.format(digits)
	return '{} point {}'.format(whole, digits)

class StopWatch(Frame):
	""" Implements a stop watch frame widget. """                                                                
	def __init__(self, parent=None, **kw):        
		Frame.__init__(self, parent, kw)
		global LapRace
		self.config(bg=colBg2)
		self._start = 0.0
		self._elapsedtime = 0.0
		self._running = 0
		self.timestr = StringVar()
		self.lapstr = StringVar()
		self.lapSplit = StringVar()
		self.bestLap = StringVar()
		self.bestTime = 0
		self.e = 0
		self.m = 0
		self.makeWidgets()
		self.laps = []
		self.lapmod2 = 0
		self._last_trigger_time = 0.0
		self._event_cutoff = time.monotonic()
		self.today = time.strftime("%d %b %Y %H-%M-%S", time.localtime())
	
	def gpioTrigger(self, event_time=None):
		# Use a monotonic clock for debounce timing to avoid issues if the
		# system wall clock is adjusted (e.g., via NTP or manual changes).
		if event_time is None:
			event_time = time.monotonic()
		if event_time < self._event_cutoff:
			return False
		if time_trial_mode and not self._running and countdown_job is not None:
			return False
		if event_time - self._last_trigger_time < MIN_LAP_TRIGGER_INTERVAL_SEC:
			return False
		self._last_trigger_time = event_time
		if time_trial_mode:
			if not self._running:
				self.Start(silent=True, event_time=event_time)
				pygame.mixer.Sound.play(SOUND_LAP)
			else:
				self.Lap(event_time=event_time)
		elif len(self.laps) + 1 == race_laps:
			self.Finish(event_time=event_time)
		else:
			self.Lap(event_time=event_time)
		return True

	def makeWidgets(self):		
		l2 = Label(self, textvariable=self.lapstr)
		self.lapstr.set('Lap: 0 / 0')
		l2.config(fg=colFg2, bg=colBg2, font=("Roboto 34 bold"))
		l2.pack(fill=X, expand=NO, pady=(40,0), padx=0)
		
		self.l = Label(self, textvariable=self.timestr)
		self.l.config(fg=colFg2, bg=colBg2, font=("Roboto 100 bold"))
		self._setTime(self._elapsedtime)
		self.l.pack(fill=X, expand=NO, pady=(0,46), padx=0)
		
		frm = Frame(self)
		frm.config(bg=colBg2)
		frm.pack(fill=X, expand=1, pady=(0,50))
		
		frm2 = Frame(self)
		frm2.config(bg=colBg2)
		frm2.pack(fill=X, expand=1, pady=(0,65))
		
		self.spt = Label(frm, textvariable=self.lapSplit, anchor=W)
		self.lapSplit.set('Split: ')
		self.spt.config(fg=colFg1, bg=colBg2, font=("Roboto 32 bold"))
		self.spt.pack(pady=0, padx=0, fill=X, expand=1, side=LEFT)
				
		self.best = Label(frm, textvariable=self.bestLap, anchor=E)
		self.bestLap.set('Best: ')
		self.best.config(fg=colFg1, bg=colBg2, font=("Roboto 32 bold"))
		self.best.pack(pady=0, padx=0, fill=X, expand=1, side=RIGHT)

		l3 = Label(frm2, text='- Times -')
		l3.config(fg=colFg1, bg=colBg1, font=('Roboto 16'))
		l3.pack(fill=X, expand=NO, pady=(30,0), padx=0)
		
		self.lap_button = Button(frm2, text='Lap', command=self.Lap, font=('Roboto 24'), bg=colBg1, fg=colFg1, highlightthickness=1, highlightbackground=colFg1, relief=FLAT)
		
		scrollbar = Scrollbar(frm2, orient=VERTICAL, bg=colScroll, highlightthickness=0, relief=FLAT, troughcolor=colBg1, bd=0 )
		self.m = Listbox(frm2,selectmode=EXTENDED, height = 6, yscrollcommand=scrollbar.set)
		self.m.config(bd='0', fg=colFg1, bg=colBg1, highlightthickness=0, font=('Courier 36'))
		self.m.pack(side=LEFT, fill=BOTH, expand=1, pady=0, padx=0)
		scrollbar.config(command=self.m.yview)
		scrollbar.pack(side=RIGHT, fill=Y)

	def _update(self): 
		""" Update the label with elapsed time. """
		self._elapsedtime = time.monotonic() - self._start
		self._setTime(self._elapsedtime)
		self._timer = self.after(25, self._update)

	def _setTime(self, elap):
		""" Set the time string to Minutes:Seconds:Thousandths """
		minutes = int(elap/60)
		seconds = int(elap - minutes*60.0)
		hseconds = int(((elap - minutes*60.0 - seconds)*10000)/10)                
		self.timestr.set('%02d:%02d:%03d' % (minutes, seconds, hseconds))

	def _setLapTime(self, elap):
		""" Set the time string to Minutes:Seconds:Thousandths """
		minutes = int(elap/60)
		seconds = int(elap - minutes*60.0)
		hseconds = int((elap - minutes*60.0 - seconds)*1000)           
		return '%02d:%02d:%03d' % (minutes, seconds, hseconds)
		
	def _bestLap(self, elap):
		if ((elap < self.bestTime) or (self.bestTime == 0)):
			self.bestTime = elap
			self.bestLap.set('Best: '+str(float("{0:.3f}".format(elap))))
			self.best.config(fg=colPurple)
			self._blinkBest(6)

	def _blinkBest(self, remaining_toggles):
		if remaining_toggles <= 0:
			self.best.config(fg=colPurple)
			return
		if self.best.cget('fg') == colPurple:
			self.best.config(fg=colBg2)
		else:
			self.best.config(fg=colPurple)
		self.after(300, self._blinkBest, remaining_toggles - 1)
			

	def Start(self, silent=False, event_time=None):
		""" Start the stopwatch, ignore if running. """
		if not self._running:            
			self._start = (time.monotonic() if event_time is None else event_time) - self._elapsedtime
			self._event_cutoff = time.monotonic() if event_time is None else event_time
			if time_trial_mode:
				self.lapstr.set('Lap: 0')
			else:
				self.lapstr.set('Lap: {} / {}'.format(len(self.laps), race_laps))
			self._update()
			self._running = 1
			if not silent:
				pygame.mixer.Sound.play(SOUND_START)    
    
	def Stop(self, event_time=None):
		""" Stop the stopwatch, ignore if stopped. """
		if self._running:
			self.after_cancel(self._timer)
			if event_time is None:
				event_time = time.monotonic()
			self._elapsedtime = event_time - self._start
			self._setTime(self._elapsedtime)
			self._running = 0

	def Reset(self):
		""" Reset the stopwatch. """
		self._start = time.monotonic()
		self._event_cutoff = self._start
		self._elapsedtime = 0.0
		self._last_trigger_time = 0.0
		self.laps = []
		self.m.delete(0,END)
		self.lapmod2 = self._elapsedtime
		self._setTime(self._elapsedtime)
		self.lapSplit.set('Split: ')
		self.bestLap.set('Best: ')
		self.l.config(fg=colFg1)
		self.spt.config(fg=colFg1)
		self.best.config(fg=colFg1)
		self.bestTime = 0
		# pygame.mixer.Sound.play(SOUND_REVVING)    

		
	def Finish(self, event_time=None):
		""" Finish race for this lane """
		if not self.Lap(event_time=event_time):
			return
		self.Stop(event_time=event_time)
		td = Thread(target=playBuzz, args=())
		td.start()
		pygame.mixer.Sound.play(SOUND_FINISH)    

	def Lap(self, event_time=None):
		'''Makes a lap, only if started'''
		global race_winner
		if (self._running):
			if event_time is None:
				event_time = time.monotonic()
			current_elapsed = event_time - self._start
			self._elapsedtime = current_elapsed
			tempo = current_elapsed - self.lapmod2
			if tempo < MIN_LAP_TIME_SEC:
				return False
			self.laps.append([self._setLapTime(tempo),float("{0:.3f}".format(tempo))])
			self.m.insert(END, self.laps[-1][0])
			self.m.yview_moveto(1)
			self.lapmod2 = current_elapsed
			# Update lap counter       
			if time_trial_mode:
				self.lapstr.set('Lap: {}'.format(len(self.laps)))
			else:
				self.lapstr.set('Lap: {} / {}'.format(len(self.laps), race_laps))
			winning_lap = not time_trial_mode and race_winner is None and len(self.laps) == race_laps
			if winning_lap:
				race_winner = self
			splitTimes(self, announce_leader=not winning_lap)
			self._bestLap(float("{0:.3f}".format(tempo)))
			pygame.mixer.Sound.play(SOUND_LAP)
			if time_trial_mode:
				speak(format_lap_time_speech(float("{0:.3f}".format(tempo))))
			elif winning_lap:
				speak('Lane {} wins'.format(1 if self is sw else 2))
			return True
		return False
	
class raceWidgets(Frame):
	def __init__(self, parent=None, **kw):        
		Frame.__init__(self, parent, kw)
		global LapRace
		self.configure(bg=colBg1)
		LapRace = StringVar()
		l = Label(self, text='Set laps\ncount')
		l.config(bg=colBg1, fg=colFg1, font="Roboto 30")
		l.pack(expand=1)
		LapRace.set(DEFAULT_RACE_LAPS)
		et = Entry(self, textvariable=LapRace, width=5, justify='center')
		et.config(bd='0', bg=colBg2 ,fg=colFg2, highlightthickness=0, font="Roboto 34 bold")
		et.pack(expand=1, pady=8)
		
class Fullscreen_Window:
	def __init__(self):
		self.tk = Tk()
		self.tk.attributes('-zoomed', True)
		self.frame = Frame(self.tk)
		self.frame.pack()
		self.state = True
		self.tk.attributes("-fullscreen", self.state)
		self.tk.bind("<F11>", self.toggle_fullscreen)
		self.tk.bind("<Escape>", self.end_fullscreen)
		
	def toggle_fullscreen(self, event=None):
		self.state = not self.state
		self.tk.attributes("-fullscreen", self.state)
		return "break"
		
	def end_fullscreen(self, event=None):
		self.state = False
		self.tk.attributes("-fullscreen", False)
		
					
		
def triggerLap(channel):
	lap_event_queue.put((channel, time.monotonic()))
	if DEBUG_COUNTER_ENABLED:
		if channel == pins[0]:
			incrementDebugStat('enqueued_lane1')
		elif channel == pins[1]:
			incrementDebugStat('enqueued_lane2')

def processLapEvents():
	processed_any = False
	while True:
		try:
			channel, event_time = lap_event_queue.get_nowait()
		except Empty:
			break
		processed_any = True
		if (channel == pins[0]):
			if DEBUG_COUNTER_ENABLED:
				incrementDebugStat('processed_lane1')
			registered = sw.gpioTrigger(event_time)
			if DEBUG_COUNTER_ENABLED:
				if registered:
					incrementDebugStat('accepted_lane1')
				else:
					incrementDebugStat('ignored_interval_lane1')
		elif (channel == pins[1]):
			if DEBUG_COUNTER_ENABLED:
				incrementDebugStat('processed_lane2')
			registered = sw2.gpioTrigger(event_time)
			if DEBUG_COUNTER_ENABLED:
				if registered:
					incrementDebugStat('accepted_lane2')
				else:
					incrementDebugStat('ignored_interval_lane2')
	delay_ms = 5 if processed_any else 50
	root.tk.after(delay_ms, processLapEvents)

def incrementDebugStat(key, amount=1):
	with debug_stats_lock:
		debug_stats[key] += amount

def getDebugSnapshot():
	with debug_stats_lock:
		return dict(debug_stats)

def updateDebugOverlay():
	if not DEBUG_COUNTER_ENABLED:
		return
	stats = getDebugSnapshot()
	debug_text = (
		'GPIO Debug\n'
		'Q L1/L2: {}/{}\n'
		'P L1/L2: {}/{}\n'
		'A L1/L2: {}/{}\n'
		'I L1/L2: {}/{}'
	).format(
		stats['enqueued_lane1'], stats['enqueued_lane2'],
		stats['processed_lane1'], stats['processed_lane2'],
		stats['accepted_lane1'], stats['accepted_lane2'],
		stats['ignored_interval_lane1'], stats['ignored_interval_lane2']
	)
	debug_label.config(text=debug_text)
	root.tk.after(DEBUG_COUNTER_UPDATE_MS, updateDebugOverlay)
	
def validRaceLaps():
	global race_laps
	if time_trial_mode:
		return True
	try:
		value = int(LapRace.get())
		if value <= 0:
			raise ValueError
	except ValueError:
		messagebox.showerror('Invalid lap count', 'Enter a positive whole number of laps.')
		return False
	race_laps = value
	return True

def StartRace():
	if countdown_job is not None or sw._running or sw2._running or not validRaceLaps():
		return
	start_time = time.monotonic()
	sw.Start(event_time=start_time)
	sw2.Start(event_time=start_time)

def StopRace():
	sw.Stop()
	sw2.Stop()

def cancelCountdown():
	global countdown_job, countdown_widgets
	if countdown_job is not None:
		root.tk.after_cancel(countdown_job)
		countdown_job = None
	for widget in countdown_widgets:
		widget.destroy()
	countdown_widgets = []

def ResetRace():
	global race_winner
	cancelCountdown()
	StopRace()
	sw.Reset()
	sw2.Reset()
	race_winner = None

def QuitRace():
	cancelCountdown()
	root.tk.quit()

def ToggleTimeTrial():
	global time_trial_mode
	time_trial_mode = not time_trial_mode
	ResetRace()
	if time_trial_mode:
		sw.lap_button.pack(side=BOTTOM, fill=X, expand=1, padx=0, pady=10, before=sw.m)
		sw2.lap_button.pack(side=BOTTOM, fill=X, expand=1, padx=0, pady=10, before=sw2.m)
		btn_time_trial.config(text='Time Trial \u25cf', bg=colPurple)
	else:
		sw.lap_button.pack_forget()
		sw2.lap_button.pack_forget()
		btn_time_trial.config(text='Time Trial', bg=colFg1)

def ToggleTTS():
	global tts_enabled, tts_generation
	with tts_lock:
		tts_enabled = not tts_enabled
		if not tts_enabled:
			tts_generation += 1
			while True:
				try:
					tts_queue.get_nowait()
				except Empty:
					break
	if tts_enabled:
		btn_tts.config(text='TTS \u25cf', bg=colPurple)
	else:
		btn_tts.config(text='TTS \U0001f508', bg=colFg1)

def RaceLights():
	global countdown_job, countdown_widgets
	if countdown_job is not None or not validRaceLaps():
		return
	ResetRace()
	photos = [PhotoImage(file=str(BASE_DIR / 'imgs' / name)) for name in
		('light_off_hd.png', 'light_red_hd.png', 'light_green_hd.png')]
	canvas = Canvas(root.tk, width=1920, height=411, bg=colBg1, highlightthickness=0)
	canvas.place(x=0, y=0)
	countdown_widgets = [canvas]
	lights = []
	for x in (720, 960, 1200):
		light = Label(root.tk, image=photos[0], bg=colBg1)
		light.place(x=x, y=240)
		lights.append(light)
		countdown_widgets.append(light)

	def step(index):
		global countdown_job
		if index < 3:
			lights[index].config(image=photos[1])
			pygame.mixer.Sound.play(SOUND_BEEP_RED)
			countdown_job = root.tk.after(int(LIGHTS_INTERVAL_SEC * 1000), step, index + 1)
		else:
			for light in lights:
				light.config(image=photos[2])
			pygame.mixer.Sound.play(SOUND_BEEP_GREEN)
			start_time = time.monotonic()
			sw.Start(event_time=start_time)
			sw2.Start(event_time=start_time)
			countdown_job = root.tk.after(1000, cancelCountdown)
	countdown_job = root.tk.after(int((0.5 + LIGHTS_INTERVAL_SEC) * 1000), step, 0)

def playBuzz():
	GPIO.setup(pins[2], GPIO.OUT)
	pwm = GPIO.PWM(pins[2], 1000)
	pwm.start(20)
	time.sleep(0.1)
	pwm.ChangeDutyCycle(100) #off
	time.sleep(0.2)
	pwm.ChangeDutyCycle(20) #on
	pwm.ChangeFrequency(500)
	time.sleep(0.1)
	pwm.ChangeDutyCycle(100) #off
	time.sleep(0.1)
	pwm.ChangeDutyCycle(20) #on
	time.sleep(0.2)
	pwm.ChangeDutyCycle(100) #off
	time.sleep(0.1)
	pwm.ChangeDutyCycle(20) #on
	pwm.ChangeFrequency(1000)
	time.sleep(0.2)
	pwm.ChangeDutyCycle(100) #off
	time.sleep(0.1)
	pwm.ChangeDutyCycle(20) #on
	pwm.ChangeFrequency(1500)
	time.sleep(0.2)
	pwm.ChangeDutyCycle(100) #off
	time.sleep(0.2)
	pwm.ChangeDutyCycle(20) #on
	pwm.ChangeFrequency(2200)
	time.sleep(1)
	pwm.ChangeDutyCycle(100)
	GPIO.setup(pins[2], GPIO.IN)
	
def splitTimes(completed_lane, announce_leader=True):
	common = min(len(sw.laps), len(sw2.laps))
	if common:
		difference = round(sum(lap[1] for lap in sw.laps[:common]) - sum(lap[1] for lap in sw2.laps[:common]), 3)
		for lane, gap in ((sw, difference), (sw2, -difference)):
			lane.lapSplit.set('Lap {} gap: {:+.3f}'.format(common, gap if gap else 0))
	else:
		difference = 0
		for lane in (sw, sw2):
			lane.lapSplit.set('Lap gap: —')
	if len(sw.laps) != len(sw2.laps):
		leader = sw if len(sw.laps) > len(sw2.laps) else sw2
	elif difference:
		leader = sw if difference < 0 else sw2
	else:
		leader = None
	for lane in (sw, sw2):
		color = colFg1 if leader is None else (colGreen if lane is leader else colRed)
		lane.spt.config(fg=color)
		lane.l.config(fg=color)
	if announce_leader and not time_trial_mode and leader is completed_lane:
		speak('Lane {} in the lead'.format(1 if leader is sw else 2))

def main():
	global root, sw, sw2, inputID, pins, LapRace, pwm, colBg1, colBg2, colFg1, colFg2, colGreen, colRed, colPurple, colScroll, lap_event_queue, debug_stats, debug_stats_lock, debug_label, time_trial_mode, btn_time_trial, tts_enabled, btn_tts
	colBg1 = '#04080c'
	colBg2 = '#101e28'
	colFg1 = '#a1aeb4'
	colFg2 = '#c8d0d4'
	colGreen = '#6ca32c' 
	colRed = '#f34820'
	colPurple = '#e051d4'
	colScroll = '#273a46'	
	pins = [21,23,18] # lane1, lane2, buzzer
	lap_event_queue = Queue()
	debug_stats_lock = Lock()
	debug_stats = {
		'enqueued_lane1': 0,
		'enqueued_lane2': 0,
		'processed_lane1': 0,
		'processed_lane2': 0,
		'accepted_lane1': 0,
		'accepted_lane2': 0,
		'ignored_interval_lane1': 0,
		'ignored_interval_lane2': 0,
	}
	
	time_trial_mode = False
	tts_enabled = False
	
	GPIO.setmode(GPIO.BCM)
	
	root = Fullscreen_Window()
	root.tk.geometry("1920x1080")
	root.tk.configure(bg='#04080c')
	root.tk.title('Tyco Race Control')
	
	bkgc = Canvas(root.tk, width=1920, height=411, bg=colBg2, highlightthickness=0)
	bkgc.place(x=0, y=0)
	
	sw = StopWatch(root.tk)
	sw2 = StopWatch(root.tk)
	sw.pack(side=LEFT, padx=(60,20))
	sw2.pack(side=RIGHT, padx=(20,60))
		
	btnFrm = Frame(root.tk)
	btnFrm.config(bg=colBg1)
	btnFrm.pack(side=BOTTOM, anchor=S, fill=X, padx=20)

	if DEBUG_COUNTER_ENABLED:
		debug_label = Label(root.tk, justify=LEFT, anchor=NW, font=('Courier 12'), bg=colBg1, fg=colFg1)
		debug_label.place(x=20, y=20)
		updateDebugOverlay()

	Button(btnFrm, text='Quit', command=QuitRace, font=('Roboto 24'), bg=colFg1, fg=colBg1, highlightthickness=0, relief=FLAT).pack(side=BOTTOM, anchor=S, fill=X, padx=10, pady=(5,72))
	Button(btnFrm, text='Reset', command=ResetRace, font=('Roboto 24'), bg=colFg1, fg=colBg1, highlightthickness=0, relief=FLAT).pack(side=BOTTOM, anchor=S, fill=X, padx=10, pady=5)
	btn_time_trial = Button(btnFrm, text='Time Trial', command=ToggleTimeTrial, font=('Roboto 24'), bg=colFg1, fg=colBg1, highlightthickness=0, relief=FLAT)
	btn_time_trial.pack(side=BOTTOM, anchor=S, fill=X, padx=10, pady=5)
	btn_tts = Button(btnFrm, text='TTS \U0001f508', command=ToggleTTS, font=('Roboto 24'), bg=colFg1, fg=colBg1, highlightthickness=0, relief=FLAT)
	btn_tts.pack(side=BOTTOM, anchor=S, fill=X, padx=10, pady=5)
	Button(btnFrm, text='Start', command=StartRace, font=('Roboto 36 bold'), bg=colGreen, fg='white', highlightthickness=0, relief=FLAT).pack(side=BOTTOM, anchor=S, fill=X, padx=10, pady=5)
	Button(btnFrm, text='Lights', command=RaceLights, font=('Roboto 36 bold'), bg=colGreen, fg='white', highlightthickness=0, relief=FLAT, pady=25).pack(side=BOTTOM, anchor=S, fill=X, padx=10, pady=5)

	raceSetup = raceWidgets(root.tk)
	raceSetup.pack(side=BOTTOM, anchor=S, fill=X, pady=20)
	
	GPIO.setup(pins[0], GPIO.IN)
	GPIO.add_event_detect(pins[0], GPIO.RISING, callback=triggerLap, bouncetime=GPIO_BOUNCETIME_MS)
	GPIO.setup(pins[1], GPIO.IN)
	GPIO.add_event_detect(pins[1], GPIO.RISING, callback=triggerLap, bouncetime=GPIO_BOUNCETIME_MS)
	root.tk.after(5, processLapEvents)

	try:
		root.tk.mainloop()
	finally:
		cancelCountdown()
		tts_queue.put(None)
		GPIO.cleanup()
	

if __name__ == '__main__':
	main()
