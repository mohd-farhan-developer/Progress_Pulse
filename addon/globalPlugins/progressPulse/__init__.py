# Progress Pulse - an NVDA add-on that plays your own sounds for progress bars.
# Copyright (C) 2026 Mohd Farhan Hussain
# This file is covered by the GNU General Public License version 2. See LICENSE.

import functools
import math
import os
import threading
import time
from collections import OrderedDict

import addonHandler
import config
import controlTypes
import globalPluginHandler
import gui
import nvwave
import tones
import ui
import winUser
import wx
from gui import guiHelper, nvdaControls
from gui.settingsDialogs import NVDASettingsDialog, SettingsPanel
from logHandler import log
from NVDAObjects.behaviors import ProgressBar
from scriptHandler import script

from . import audio

addonHandler.initTranslation()

CONFIG_SECTION = "progressPulse"
# Config keys of the sounds. A value is "builtin:<name>" for a built-in sound, a path to a WAV file,
# or empty for no sound (for the start, halfway and finished sounds, the regular sound plays instead).
REGULAR = "soundFile"
START = "startSoundFile"
HALFWAY = "halfwaySoundFile"
FINISH = "finishSoundFile"
MILESTONE_SOUNDS = {"start": START, "halfway": HALFWAY, "finish": FINISH}
# Semitones between 0% and 100%.
PITCH_CHANGES = {"none": 0, "small": 6, "medium": 12, "large": 24}

config.conf.spec[CONFIG_SECTION] = {
	"enabled": "boolean(default=True)",
	REGULAR: 'string(default="builtin:drop")',
	START: 'string(default="")',
	HALFWAY: 'string(default="")',
	FINISH: 'string(default="builtin:chime")',
	"pitchChange": 'option("none", "small", "medium", "large", default="medium")',
	"stereoPan": "boolean(default=False)",
	"volume": "integer(default=80, min=0, max=100)",
	"overlap": "boolean(default=False)",
	"announceFinish": "boolean(default=True)",
}

SOUNDS_DIR = os.path.join(os.path.dirname(__file__), "sounds")
BUILT_IN_PREFIX = "builtin:"
# Used when the chosen regular sound file is missing or broken.
FALLBACK_SOUND = BUILT_IN_PREFIX + "drop"
BUILT_IN_SOUNDS = (
	# Translators: name of a built-in sound.
	("drop", _("Water drop")),
	# Translators: name of a built-in sound.
	("tick", _("Soft tick")),
	# Translators: name of a built-in sound.
	("marimba", _("Marimba")),
	# Translators: name of a built-in sound.
	("bubble", _("Bubble")),
	# Translators: name of a built-in sound.
	("chime", _("Success chime")),
)
# Rendered sounds are cached so repeated progress values don't have to be processed again.
CACHE_LIMIT_BYTES = 32 * 1024 * 1024
# Regular sounds closer together than this are skipped, so several busy progress bars don't sound choppy.
MIN_GAP_SECONDS = 0.12
# How many sounds can play at the same time when overlapping is on.
OVERLAP_CHANNELS = 3
# A progress bar that goes back below 100% this soon was only one step (for example one file of many),
# so its "complete" announcement is dropped.
FINISH_ANNOUNCE_DELAY_MS = 1500
# The same announcement isn't repeated within this time, for apps with several bars finishing together.
FINISH_REPEAT_SECONDS = 5

# Words in the window title or progress bar name, and what to say when it finishes. The first match wins.
FINISH_MESSAGES = (
	# Translators: announced when a progress bar finishes.
	(("uninstall",), _("Uninstall complete")),
	# Translators: announced when a progress bar finishes.
	(("download",), _("Download complete")),
	# Translators: announced when a progress bar finishes.
	(("upload",), _("Upload complete")),
	# Translators: announced when a progress bar finishes.
	(("extract", "unzip", "unpack", "decompress", "unrar"), _("Extraction complete")),
	# Translators: announced when a progress bar finishes.
	(("compress", "archiv"), _("Compression complete")),
	# Translators: announced when a progress bar finishes.
	(("install", "setup"), _("Installation complete")),
	# Translators: announced when a progress bar finishes.
	(("updat",), _("Update complete")),
	# Translators: announced when a progress bar finishes.
	(("copy", "copying"), _("Copy complete")),
	# Translators: announced when a progress bar finishes.
	(("moving",), _("Move complete")),
	# Translators: announced when a progress bar finishes.
	(("delet",), _("Delete complete")),
	# Translators: announced when a progress bar finishes.
	(("convert",), _("Conversion complete")),
	# Translators: announced when a progress bar finishes.
	(("export", "render"), _("Export complete")),
	# Translators: announced when a progress bar finishes.
	(("scan",), _("Scan complete")),
)


def soundPath(value):
	"""The file for a sound setting value ("builtin:<name>" or a path)."""
	if value.startswith(BUILT_IN_PREFIX):
		return os.path.join(SOUNDS_DIR, value[len(BUILT_IN_PREFIX) :] + ".wav")
	return value


def outputDevice():
	try:
		return config.conf["audio"]["outputDevice"]
	except KeyError:
		# NVDA 2024.4 and older keep the output device in the speech settings.
		return config.conf["speech"]["outputDevice"]


class SoundLoader:
	"""Loads sound files, reloading only when a file changes. Problems are logged once per file."""

	def __init__(self):
		self._sounds = {}

	def load(self, value):
		"""Return the sound for a setting value, or None if it is empty or can't be used."""
		if not value:
			return None
		path = soundPath(value)
		try:
			mtime = os.path.getmtime(path)
		except OSError:
			mtime = None
		cached = self._sounds.get(path)
		if cached and cached[0] == mtime:
			return cached[1]
		sound = None
		if mtime is None:
			log.warning(f"Progress Pulse: sound file not found: {path}")
		else:
			try:
				sound = audio.load(path)
			except audio.SoundFileError as e:
				log.warning(f"Progress Pulse: can't use sound file {path}: {e}")
		self._sounds[path] = (mtime, sound)
		return sound

	def regular(self, value):
		"""The regular progress sound, or the fallback sound if the chosen one can't be used.
		None if value is empty, which means no regular sound.
		"""
		if not value:
			return None
		return self.load(value) or self.load(FALLBACK_SOUND)


class RenderCache:
	"""Rendered sounds shared by all channels, dropping the least recently used when full."""

	def __init__(self):
		self._lock = threading.Lock()
		self._items = OrderedDict()
		self._bytes = 0

	def render(self, sound, pitch, left, right):
		key = (sound, round(pitch, 4), round(left, 3), round(right, 3))
		with self._lock:
			data = self._items.get(key)
			if data is not None:
				self._items.move_to_end(key)
				return data
		data = sound.render(pitch, left, right)
		with self._lock:
			if key not in self._items:
				self._items[key] = data
				self._bytes += len(data)
				while self._bytes > CACHE_LIMIT_BYTES and len(self._items) > 1:
					_key, old = self._items.popitem(last=False)
					self._bytes -= len(old)
		return data

	def clear(self):
		with self._lock:
			self._items.clear()
			self._bytes = 0


class Channel:
	"""Plays one sound at a time on a background thread so NVDA never waits for audio."""

	def __init__(self, cache):
		self._cache = cache
		self._wavePlayer = None
		self._device = None
		self._lock = threading.Lock()
		self._pending = None
		self._wake = threading.Event()
		self._running = True
		self._thread = threading.Thread(target=self._run, name=f"{__name__}.Channel", daemon=True)
		self._thread.start()

	def play(self, sound, pitch, left, right):
		player = self._getWavePlayer()
		if not player:
			return
		with self._lock:
			self._pending = (player, sound, pitch, left, right)
		# A new sound cuts off the one this channel is playing.
		player.stop()
		self._wake.set()

	def _getWavePlayer(self):
		device = outputDevice()
		if self._wavePlayer and device == self._device:
			return self._wavePlayer
		kwargs = dict(
			channels=2,
			samplesPerSec=audio.OUTPUT_RATE,
			bitsPerSample=16,
			outputDevice=device,
			wantDucking=False,
		)
		purpose = getattr(nvwave, "AudioPurpose", None)
		if purpose:
			kwargs["purpose"] = purpose.SOUNDS
		try:
			self._wavePlayer = nvwave.WavePlayer(**kwargs)
		except Exception:
			log.warning("Progress Pulse couldn't open the audio device", exc_info=True)
			self._wavePlayer = None
		self._device = device
		return self._wavePlayer

	def _run(self):
		while True:
			self._wake.wait()
			self._wake.clear()
			if not self._running:
				return
			with self._lock:
				job, self._pending = self._pending, None
			if job is None:
				continue
			player, sound, pitch, left, right = job
			try:
				data = self._cache.render(sound, pitch, left, right)
				with self._lock:
					if self._pending is not None:
						# A newer sound arrived while rendering; play that one instead.
						continue
				player.feed(data)
				player.idle()
			except Exception:
				log.exception("Error playing progress bar sound")

	def terminate(self):
		self._running = False
		self._wake.set()
		if self._wavePlayer:
			self._wavePlayer.stop()
		self._thread.join(1)
		self._wavePlayer = None


class SoundOutput:
	"""Decides which channel plays a sound, and skips regular sounds that come too close together."""

	def __init__(self):
		self._cache = RenderCache()
		self._channels = []
		self._next = 0
		self._lastPlayed = 0.0

	def play(self, sound, pitch, left, right, overlap=False, important=False):
		"""@param important: milestone and preview sounds, which are never skipped."""
		now = time.monotonic()
		if not important and now - self._lastPlayed < MIN_GAP_SECONDS:
			return
		self._lastPlayed = now
		count = OVERLAP_CHANNELS if overlap else 1
		while len(self._channels) < count:
			self._channels.append(Channel(self._cache))
		if overlap:
			channel = self._channels[self._next % count]
			self._next += 1
		else:
			channel = self._channels[0]
		channel.play(sound, pitch, left, right)

	def terminate(self):
		for channel in self._channels:
			channel.terminate()
		self._channels = []
		self._cache.clear()


class ProgressTracker:
	"""Remembers each progress bar's last value to notice when it starts, passes halfway or finishes."""

	MAX_BARS = 100

	def __init__(self):
		self._last = OrderedDict()

	def update(self, key, percent):
		"""@return: "start", "halfway", "finish" or None."""
		previous = self._last.pop(key, None)
		self._last[key] = percent
		if len(self._last) > self.MAX_BARS:
			self._last.popitem(last=False)
		if previous is None:
			return "start" if percent < 10 else None
		if percent < 10 <= previous:
			# The bar went back to the beginning, for example for the next file.
			return "start"
		if previous < 100 <= percent:
			return "finish"
		if previous < 50 <= percent:
			return "halfway"
		return None


def finishMessage(obj):
	"""What to announce when obj finishes, based on its name and its window's title."""
	texts = []
	title = ""
	try:
		texts.append(obj.name or "")
		title = winUser.getWindowText(winUser.getAncestor(obj.windowHandle, winUser.GA_ROOT)) or ""
		texts.append(title)
		texts.append((obj.parent and obj.parent.name) or "")
	except Exception:
		log.debugWarning("Progress Pulse couldn't read the progress bar's window", exc_info=True)
	combined = " ".join(texts).lower()
	for words, message in FINISH_MESSAGES:
		if any(word in combined for word in words):
			return message
	title = title.strip()
	# Windows copy dialogs have titles like "100% Complete", which add nothing.
	if title and "%" not in title:
		# Translators: announced when a progress bar finishes in a window that isn't recognised.
		# {title} is the window's title.
		return _("Progress complete, {title}").format(title=title)
	# Translators: announced when a progress bar finishes in a window that isn't recognised.
	return _("Progress complete")


class FinishAnnouncer:
	"""Announces finished progress bars, after a short wait to make sure they really finished."""

	def __init__(self):
		self._timers = {}
		self._lastText = None
		self._lastTime = 0.0

	def update(self, key, percent, event, obj):
		if percent < 100:
			timer = self._timers.pop(key, None)
			if timer:
				timer.Stop()
		if event == "finish" and config.conf[CONFIG_SECTION]["announceFinish"]:
			text = finishMessage(obj)
			old = self._timers.pop(key, None)
			if old:
				old.Stop()
			self._timers[key] = wx.CallLater(FINISH_ANNOUNCE_DELAY_MS, self._announce, key, text)

	def _announce(self, key, text):
		self._timers.pop(key, None)
		now = time.monotonic()
		if text == self._lastText and now - self._lastTime < FINISH_REPEAT_SECONDS:
			return
		self._lastText = text
		self._lastTime = now
		ui.message(text)

	def cancel(self):
		for timer in self._timers.values():
			timer.Stop()
		self._timers = {}


_loader = SoundLoader()
_tracker = ProgressTracker()
_announcer = FinishAnnouncer()
_output = None


def playSound(sound, percent, settings, important=False, followPitch=True):
	"""Play sound for a progress percentage.
	@param settings: a mapping like the config section (the settings panel passes its unsaved values).
	@param followPitch: False plays the file at its own pitch, used for milestone sounds.
	"""
	if _output is None or sound is None:
		return
	pitchRange = PITCH_CHANGES.get(settings["pitchChange"], 0) if followPitch else 0
	pitch, left, right = audio.soundParams(percent, pitchRange, settings["stereoPan"], settings["volume"])
	_output.play(sound, pitch, left, right, overlap=settings["overlap"], important=important)


def _percentage(obj):
	try:
		return min(max(0.0, float(obj.value.strip("%\0"))), 100.0)
	except (AttributeError, ValueError):
		return None


def _barKey(obj):
	# Like NVDA, tell progress bars apart by their position on screen.
	try:
		left, top, width, height = obj.location
	except Exception:
		left = top = width = height = 0
	return (obj.windowHandle, left + width // 2, top + height // 2)


def _handleUpdate(obj):
	"""Track the update and decide what replaces NVDA's beep.
	@return: a function taking the beep's pitch in Hz, or None to leave NVDA's beep alone.
	"""
	pbConf = config.conf["presentation"]["progressBarUpdates"]
	mode = pbConf["progressBarOutputMode"]
	states = obj.states
	if mode == "off" or controlTypes.State.INVISIBLE in states or controlTypes.State.OFFSCREEN in states:
		return None
	percent = _percentage(obj)
	if percent is None:
		return None
	if not pbConf["reportBackgroundProgressBars"] and not obj.isInForeground:
		return None
	key = _barKey(obj)
	event = _tracker.update(key, percent)
	_announcer.update(key, percent, event, obj)
	conf = config.conf[CONFIG_SECTION]
	if not conf["enabled"] or mode not in ("beep", "both"):
		return None
	milestone = _loader.load(conf[MILESTONE_SOUNDS[event]]) if event else None
	if milestone:
		# Milestones always play, even when NVDA wouldn't beep for this small a change.
		playSound(milestone, percent, conf, important=True, followPitch=False)
		return lambda hz: None
	if not conf[REGULAR]:
		# No regular sound chosen: progress is silent apart from the start, halfway and finished sounds.
		return lambda hz: None
	regular = _loader.regular(conf[REGULAR])
	minHz = pbConf["beepMinHZ"]
	if regular is None or minHz <= 0:
		return None
	important = event is not None

	def playRegular(hz):
		# NVDA's beep is minHz * 2 ** (percent / 25); turn it back into a percentage.
		playSound(regular, 25 * math.log2(hz / minHz) if hz > 0 else 0, conf, important=important)

	return playRegular


_originalEventValueChange = ProgressBar.event_valueChange


@functools.wraps(_originalEventValueChange)
def _eventValueChange(self):
	replacement = None
	try:
		replacement = _handleUpdate(self)
	except Exception:
		log.exception("Progress Pulse couldn't handle a progress bar update")
	if replacement is None:
		return _originalEventValueChange(self)
	# Swap tones.beep only while NVDA handles this progress bar.
	realBeep = tones.beep
	mainThread = threading.get_ident()

	def progressBeep(hz, length, *args, **kwargs):
		if threading.get_ident() != mainThread:
			return realBeep(hz, length, *args, **kwargs)
		replacement(hz)

	tones.beep = progressBeep
	try:
		return _originalEventValueChange(self)
	finally:
		tones.beep = realBeep


SOUND_SLOTS = (
	# Translators: an item in the "Sound to change" list.
	(REGULAR, _("Regular sound (plays as progress goes up)")),
	# Translators: an item in the "Sound to change" list.
	(START, _("Start sound (when a progress bar begins)")),
	# Translators: an item in the "Sound to change" list.
	(HALFWAY, _("Halfway sound (at 50%)")),
	# Translators: an item in the "Sound to change" list.
	(FINISH, _("Finished sound (at 100%)")),
)
PITCH_CHOICES = (
	# Translators: a choice for how much the pitch rises with progress.
	("none", _("No change")),
	# Translators: a choice for how much the pitch rises with progress.
	("small", _("A little")),
	# Translators: a choice for how much the pitch rises with progress.
	("medium", _("Medium")),
	# Translators: a choice for how much the pitch rises with progress.
	("large", _("A lot")),
)


class ProgressPulsePanel(SettingsPanel):
	# Translators: title of the add-on's settings panel.
	title = _("Progress Pulse")

	def makeSettings(self, settingsSizer):
		helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		conf = config.conf[CONFIG_SECTION]

		self.enabledCheckBox = helper.addItem(
			# Translators: checkbox in the settings panel.
			wx.CheckBox(self, label=_("&Play my sounds for progress bars instead of NVDA's beeps")),
		)
		self.enabledCheckBox.SetValue(conf["enabled"])

		self._values = {key: conf[key] for key, _label in SOUND_SLOTS}
		# The last own file chosen for each sound, kept while trying built-in sounds.
		self._ownFiles = {
			key: value if value and not value.startswith(BUILT_IN_PREFIX) else ""
			for key, value in self._values.items()
		}
		self.slotChoice = helper.addLabeledControl(
			# Translators: label of the list choosing which sound to change.
			_("Sound to &change:"),
			wx.Choice,
			choices=[label for _key, label in SOUND_SLOTS],
		)
		self.slotChoice.SetSelection(0)
		self.slotChoice.Bind(wx.EVT_CHOICE, lambda evt: self._refreshSoundChoice())
		self.soundChoice = helper.addLabeledControl(
			# Translators: label of the list of sounds. Each sound plays when it is selected.
			_("&Sound:"),
			wx.Choice,
			choices=[],
		)
		self.soundChoice.Bind(wx.EVT_CHOICE, self.onSoundChoice)
		buttons = guiHelper.ButtonHelper(wx.HORIZONTAL)
		# Translators: button that opens a dialog to choose a sound file.
		chooseButton = buttons.addButton(self, label=_("C&hoose your own file..."))
		chooseButton.Bind(wx.EVT_BUTTON, self.onChoose)
		# Translators: button that plays the selected sound.
		playButton = buttons.addButton(self, label=_("Pla&y"))
		playButton.Bind(wx.EVT_BUTTON, self.onPlay)
		helper.addItem(buttons)
		self._refreshSoundChoice()

		self.pitchChoice = helper.addLabeledControl(
			# Translators: label of the list choosing how much the pitch rises with progress.
			_("How much the p&itch rises as progress goes up:"),
			wx.Choice,
			choices=[label for _key, label in PITCH_CHOICES],
		)
		self.pitchChoice.SetSelection([key for key, _label in PITCH_CHOICES].index(conf["pitchChange"]))

		self.panCheckBox = helper.addItem(
			# Translators: checkbox in the settings panel.
			wx.CheckBox(self, label=_("Move the sound from &left ear to right ear as progress goes up")),
		)
		self.panCheckBox.SetValue(conf["stereoPan"])

		self.volumeSpin = helper.addLabeledControl(
			# Translators: label of a spin box.
			_("&Volume (0 to 100):"),
			nvdaControls.SelectOnFocusSpinCtrl,
			min=0,
			max=100,
			initial=conf["volume"],
		)

		self.overlapCheckBox = helper.addItem(
			wx.CheckBox(
				self,
				# Translators: checkbox in the settings panel. When off, a new sound stops the previous one.
				label=_("Let sounds &overlap when several progress bars move at the same time"),
			),
		)
		self.overlapCheckBox.SetValue(conf["overlap"])

		self.announceCheckBox = helper.addItem(
			wx.CheckBox(
				self,
				# Translators: checkbox in the settings panel.
				label=_('&Announce when a progress bar finishes, for example "Download complete"'),
			),
		)
		self.announceCheckBox.SetValue(conf["announceFinish"])

		# Translators: button that plays all the sounds from 0 to 100 percent.
		testButton = helper.addItem(wx.Button(self, label=_("&Test all sounds")))
		testButton.Bind(wx.EVT_BUTTON, self.onTest)
		self._testTimers = []

	def _selectedSlot(self):
		return SOUND_SLOTS[self.slotChoice.GetSelection()][0]

	def _refreshSoundChoice(self):
		"""Fill the sound list for the selected sound to change, and select its current value."""
		slot = self._selectedSlot()
		if slot == REGULAR:
			# Translators: an item in the sound list for the regular sound.
			noneLabel = _("None (silent, only the start, halfway and finished sounds play)")
		else:
			# Translators: an item in the sound list for the start, halfway and finished sounds.
			noneLabel = _("None (the regular sound plays)")
		ownFile = self._ownFiles[slot]
		if not ownFile:
			# Translators: an item in the sound list when no own file has been chosen yet.
			ownLabel = _("Your own file (use the Choose your own file button)")
		elif os.path.isfile(ownFile):
			# Translators: an item in the sound list. {file} is the file's name.
			ownLabel = _("Your own file: {file}").format(file=os.path.basename(ownFile))
		else:
			# Translators: an item in the sound list when the chosen file no longer exists.
			ownLabel = _("Your own file: {file} (file not found)").format(file=os.path.basename(ownFile))
		self._soundOptions = (
			[("", noneLabel)]
			+ [(BUILT_IN_PREFIX + name, label) for name, label in BUILT_IN_SOUNDS]
			+ [("own", ownLabel)]
		)
		self.soundChoice.SetItems([label for _value, label in self._soundOptions])
		value = self._values[slot]
		values = [optionValue for optionValue, _label in self._soundOptions]
		if value in values:
			self.soundChoice.SetSelection(values.index(value))
		else:
			self.soundChoice.SetSelection(len(values) - 1)

	def onSoundChoice(self, evt):
		slot = self._selectedSlot()
		value = self._soundOptions[self.soundChoice.GetSelection()][0]
		if value == "own":
			value = self._ownFiles[slot]
		self._values[slot] = value
		# Play each sound as it is selected, so it can be heard while moving through the list.
		self.onPlay()

	def _panelSettings(self):
		return {
			"pitchChange": PITCH_CHOICES[self.pitchChoice.GetSelection()][0],
			"stereoPan": self.panCheckBox.GetValue(),
			"volume": self.volumeSpin.GetValue(),
			"overlap": self.overlapCheckBox.GetValue(),
		}

	def _soundFor(self, slot):
		"""The sound that would play for slot with the panel's current choices, or None for silence."""
		if slot != REGULAR:
			sound = _loader.load(self._values[slot])
			if sound:
				return sound
		return _loader.regular(self._values[REGULAR])

	def onChoose(self, evt):
		slot = self._selectedSlot()
		current = self._ownFiles[slot]
		with wx.FileDialog(
			self,
			# Translators: title of the file dialog.
			_("Choose a sound"),
			defaultDir=os.path.dirname(current) if current else os.path.expanduser("~"),
			# Translators: file type filter in the file dialog.
			wildcard=_("WAV sound files (*.wav)") + "|*.wav",
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
		) as dialog:
			if dialog.ShowModal() != wx.ID_OK:
				return
			path = dialog.GetPath()
		try:
			audio.load(path)
		except audio.SoundFileError as e:
			gui.messageBox(
				# Translators: error shown when the chosen file can't be used. {error} is the reason.
				_("This file can't be used.\n\n{error}\n\nPlease choose a WAV sound file.").format(error=e),
				# Translators: title of the error message.
				_("Progress Pulse"),
				wx.OK | wx.ICON_ERROR,
				self,
			)
			return
		self._ownFiles[slot] = path
		self._values[slot] = path
		self._refreshSoundChoice()
		self.onPlay()

	def onPlay(self, evt=None):
		slot = self._selectedSlot()
		playSound(self._soundFor(slot), 50, self._panelSettings(), important=True, followPitch=False)

	def onTest(self, evt):
		self._stopTest()
		settings = self._panelSettings()
		steps = (
			(START, 0),
			(REGULAR, 25),
			(HALFWAY, 50),
			(REGULAR, 75),
			(FINISH, 100),
		)
		delay = 200
		for slot, percent in steps:
			sound = self._soundFor(slot)
			if sound is None:
				continue
			isMilestone = slot != REGULAR and _loader.load(self._values[slot]) is not None
			self._testTimers.append(
				wx.CallLater(
					delay,
					playSound,
					sound,
					percent,
					settings,
					important=True,
					followPitch=not isMilestone,
				),
			)
			# Leave room to hear each sound, but keep the test short for long files.
			delay += int(min(max(sound.duration * 1000 + 150, 400), 1500))

	def _stopTest(self):
		for timer in self._testTimers:
			timer.Stop()
		self._testTimers = []

	def onDiscard(self):
		self._stopTest()

	def onSave(self):
		self._stopTest()
		conf = config.conf[CONFIG_SECTION]
		conf["enabled"] = self.enabledCheckBox.GetValue()
		for key, value in self._values.items():
			conf[key] = value
		for key, value in self._panelSettings().items():
			conf[key] = value
		conf["announceFinish"] = self.announceCheckBox.GetValue()


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super().__init__()
		global _output
		_output = SoundOutput()
		ProgressBar.event_valueChange = _eventValueChange
		NVDASettingsDialog.categoryClasses.append(ProgressPulsePanel)

	def terminate(self):
		global _output
		ProgressBar.event_valueChange = _originalEventValueChange
		try:
			NVDASettingsDialog.categoryClasses.remove(ProgressPulsePanel)
		except ValueError:
			pass
		_announcer.cancel()
		if _output:
			_output.terminate()
			_output = None
		super().terminate()

	@script(
		# Translators: description of the command in Input Gestures.
		description=_("Turns Progress Pulse sounds on or off (off uses NVDA's normal beeps)"),
		# Translators: category of the command in Input Gestures.
		category=_("Progress Pulse"),
	)
	def script_toggle(self, gesture):
		conf = config.conf[CONFIG_SECTION]
		conf["enabled"] = not conf["enabled"]
		if conf["enabled"]:
			# Translators: reported when the add-on's sounds are turned on.
			ui.message(_("Progress Pulse sounds on"))
		else:
			# Translators: reported when the add-on's sounds are turned off.
			ui.message(_("Progress Pulse sounds off, using NVDA beeps"))
