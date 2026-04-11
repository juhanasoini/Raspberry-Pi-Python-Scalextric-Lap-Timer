from tkinter import *
from threading import Thread, Lock
from queue import Queue, Empty
from pathlib import Path
# from PIL import Image
import RPi.GPIO as GPIO
import time
import struct
import math
import pygame

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
SOUND_BEEP_GREEN = generate_tone(1000, 300, volume=0.5)
DEFAULT_RACE_LAPS = 3
LIGHTS_INTERVAL_SEC = 0.5
GPIO_BOUNCETIME_MS = 120
MIN_LAP_TRIGGER_INTERVAL_SEC = 0.15
DEBUG_COUNTER_ENABLED = True
DEBUG_COUNTER_UPDATE_MS = 200

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
		self.today = time.strftime("%d %b %Y %H-%M-%S", time.localtime())
	
	def gpioTrigger(self, event_time=None):
		if event_time is None:
			event_time = time.time()
		if (event_time - self._last_trigger_time) < MIN_LAP_TRIGGER_INTERVAL_SEC:
			return False
		self._last_trigger_time = event_time
		if (len(self.laps)+1 == int(LapRace.get())): # Finish Race if last lap
			self.Finish()
		else:
			self.Lap()
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
		
		Button(frm2, text='Finish Line', command=self.Finish, font=('Roboto 24'), bg=colBg1, fg=colFg1, highlightthickness=1, highlightbackground=colFg1, relief=FLAT).pack(side=BOTTOM, fill=X, expand=1, padx=0, pady=0)
		Button(frm2, text='Lap', command=self.Lap, font=('Roboto 24'), bg=colBg1, fg=colFg1, highlightthickness=1, highlightbackground=colFg1, relief=FLAT).pack(side=BOTTOM, fill=X, expand=1, padx=0, pady=10)
		
		scrollbar = Scrollbar(frm2, orient=VERTICAL, bg=colScroll, highlightthickness=0, relief=FLAT, troughcolor=colBg1, bd=0 )
		self.m = Listbox(frm2,selectmode=EXTENDED, height = 6, yscrollcommand=scrollbar.set)
		self.m.config(bd='0', fg=colFg1, bg=colBg1, highlightthickness=0, font=('Courier 36'))
		self.m.pack(side=LEFT, fill=BOTH, expand=1, pady=0, padx=0)
		scrollbar.config(command=self.m.yview)
		scrollbar.pack(side=RIGHT, fill=Y)

	def _update(self): 
		""" Update the label with elapsed time. """
		self._elapsedtime = time.time() - self._start
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
		return '%02d:%02d:%02d' % (minutes, seconds, hseconds)
		
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
			

	def Start(self):                                                     
		""" Start the stopwatch, ignore if running. """
		if not self._running:            
			self._start = time.time() - self._elapsedtime
			self.lapstr.set('Lap: {} / {}'.format(len(self.laps), int(LapRace.get())))
			self._update()
			self._running = 1
			pygame.mixer.Sound.play(SOUND_START)    
    
	def Stop(self, event_time=None):
		""" Stop the stopwatch, ignore if stopped. """
		if self._running:
			self.after_cancel(self._timer)
			if event_time is None:
				event_time = time.time()
			self._elapsedtime = event_time - self._start
			self._setTime(self._elapsedtime)
			self._running = 0

	def Reset(self):
		""" Reset the stopwatch. """
		self._start = time.time()
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
		self.Lap(event_time=event_time)
		self.Stop(event_time=event_time)
		td = Thread(target=playBuzz, args=())
		td.start()
		pygame.mixer.Sound.play(SOUND_FINISH)    

	def Lap(self, event_time=None):
		'''Makes a lap, only if started'''
		if (self._running):
			if event_time is None:
				event_time = time.time()
			current_elapsed = event_time - self._start
			self._elapsedtime = current_elapsed
			tempo = current_elapsed - self.lapmod2
			if tempo <= 0:
				return
			self.laps.append([self._setLapTime(tempo),float("{0:.3f}".format(tempo))])
			self.m.insert(END, self.laps[-1][0])
			self.m.yview_moveto(1)
			self.lapmod2 = current_elapsed
			# Update lap counter       
			self.lapstr.set('Lap: {} / {}'.format(len(self.laps), int(LapRace.get())))
			splitTimes()
			self._bestLap(float("{0:.3f}".format(tempo)))
			pygame.mixer.Sound.play(SOUND_LAP)    
	
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
	lap_event_queue.put((channel, time.time()))
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
	
def StartRace():
	sw.Start()
	sw2.Start()
	
def StopRace():
	sw.Stop()
	sw2.Stop()
	
def ResetRace():
	sw.Reset()
	sw2.Reset()
	
def RaceLights():
	StopRace()
	ResetRace()
	photo = PhotoImage(file="imgs/light_off_hd.png")
	photo2 = PhotoImage(file="imgs/light_red_hd.png")
	photo3 = PhotoImage(file="imgs/light_green_hd.png")
	lights = []
	coords = [[720,240],[960,240],[1200,240]]

	cv = Canvas(root.tk, width=1920, height=1080, bg=colBg1, highlightthickness=0)
	cv.place(x=0, y=0)

	for i in range(3):
		lights.append(Label(root.tk, image=photo, bg=colBg1))
		lights[i].image = photo
		lights[i].place(x=coords[i][0], y=coords[i][1])
	
	lights.append(cv)
	
	root.tk.update()
	time.sleep(0.5)
	
	for i in range(3):
		time.sleep(LIGHTS_INTERVAL_SEC)
		lights[i].config(image = photo2)
		lights[i].image = photo2
		root.tk.update()
		pygame.mixer.Sound.play(SOUND_BEEP_RED)
		
	for i in range(3):
		lights[i].config(image = photo3)
		lights[i].image = photo3
	
	time.sleep(LIGHTS_INTERVAL_SEC)
	root.tk.update()
	pygame.mixer.Sound.play(SOUND_BEEP_GREEN)
	
	root.tk.after(1000, LightsOut, lights)
	
	StartRace()
	
def LightsOut(lights):
	for i in range(3):
		lights[i].destroy()
	lights[3].destroy()
	root.tk.update()
		
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
	
def splitTimes():
	c1 = 0
	c2 = 0
	sameDiff = 0
	extraDiff = 0
	totalDiff = 0
	if (len(sw.laps) > len(sw2.laps)):  # Lane 1 in the lead
		sameLaps = len(sw2.laps)
		extraLaps = len(sw.laps) - len(sw2.laps)
		sameArr = [sw.laps[:sameLaps], sw2.laps[:sameLaps]]
		extraArr = sw.laps[-extraLaps:]
		for i in range(len(sameArr[0])):
			c1 += sameArr[0][i][1]
			c2 += sameArr[1][i][1]
			sameDiff = c2 - c1
		for i in range(len(extraArr)):
			extraDiff += extraArr[i][1]
		totalDiff = abs(sameDiff + extraDiff)
		sw.lapSplit.set('Split: -'+str(float("{0:.3f}".format(totalDiff))))
		sw.spt.config(fg=colGreen)
		sw.l.config(fg=colGreen)
		sw2.lapSplit.set('Split: +'+str(float("{0:.3f}".format(totalDiff))))
		sw2.spt.config(fg=colRed)
		sw2.l.config(fg=colRed)
	elif (len(sw.laps) < len(sw2.laps)):  # Lane 2 in the lead
		sameLaps = len(sw.laps)
		extraLaps = len(sw2.laps) - len(sw.laps)
		sameArr = [sw2.laps[:sameLaps], sw.laps[:sameLaps]]
		extraArr = sw2.laps[-extraLaps:]
		for i in range(len(sameArr[0])):
			c1 += sameArr[0][i][1]
			c2 += sameArr[1][i][1]
			sameDiff = c2 - c1
		for i in range(len(extraArr)):
			extraDiff += extraArr[i][1]
		totalDiff = abs(sameDiff + extraDiff)
		sw2.lapSplit.set('Split: -'+str(float("{0:.3f}".format(totalDiff))))
		sw2.spt.config(fg=colGreen)
		sw2.l.config(fg=colGreen)
		sw.lapSplit.set('Split: +'+str(float("{0:.3f}".format(totalDiff))))
		sw.spt.config(fg=colRed)
		sw.l.config(fg=colRed)
	else:  # equal Laps - just need the total same difference
		sameLaps = len(sw.laps)
		sameArr = [sw2.laps[:sameLaps], sw.laps[:sameLaps]]
		for i in range(len(sameArr[0])):
			c1 += sameArr[0][i][1]
			c2 += sameArr[1][i][1]
			totalDiff = c2 - c1
		if (totalDiff > 0):
			sw.lapSplit.set('Split: +'+str(float("{0:.3f}".format(abs(totalDiff)))))
			sw.spt.config(fg=colRed)
			sw.l.config(fg=colRed)
			sw2.lapSplit.set('Split: -'+str(float("{0:.3f}".format(abs(totalDiff)))))
			sw2.spt.config(fg=colGreen)
			sw2.l.config(fg=colGreen)
		else:
			sw2.lapSplit.set('Split: +'+str(float("{0:.3f}".format(abs(totalDiff)))))
			sw2.spt.config(fg=colRed)
			sw2.l.config(fg=colRed)
			sw.lapSplit.set('Split: -'+str(float("{0:.3f}".format(abs(totalDiff)))))
			sw.spt.config(fg=colGreen)
			sw.l.config(fg=colGreen)
				
		
				
def main():
	global root, sw, sw2, inputID, pins, LapRace, pwm, colBg1, colBg2, colFg1, colFg2, colGreen, colRed, colPurple, colScroll, lap_event_queue, debug_stats, debug_stats_lock, debug_label
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

	Button(btnFrm, text='Quit', command=root.tk.quit, font=('Roboto 24'), bg=colFg1, fg=colBg1, highlightthickness=0, relief=FLAT).pack(side=BOTTOM, anchor=S, fill=X, padx=10, pady=(5,72))
	Button(btnFrm, text='Reset', command=ResetRace, font=('Roboto 24'), bg=colFg1, fg=colBg1, highlightthickness=0, relief=FLAT).pack(side=BOTTOM, anchor=S, fill=X, padx=10, pady=5)
	Button(btnFrm, text='Stop', command=StopRace, font=('Roboto 24'), bg=colFg1, fg=colBg1, highlightthickness=0, relief=FLAT).pack(side=BOTTOM, anchor=S, fill=X, padx=10, pady=5) 
	Button(btnFrm, text='Start', command=StartRace, font=('Roboto 36 bold'), bg=colGreen, fg='white', highlightthickness=0, relief=FLAT).pack(side=BOTTOM, anchor=S, fill=X, padx=10, pady=5)
	Button(btnFrm, text='Lights', command=RaceLights, font=('Roboto 36 bold'), bg=colGreen, fg='white', highlightthickness=0, relief=FLAT).pack(side=BOTTOM, anchor=S, fill=X, padx=10, pady=5)

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
		GPIO.cleanup()
	

if __name__ == '__main__':
	main()
