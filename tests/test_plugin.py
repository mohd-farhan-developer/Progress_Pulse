"""Tests for the NVDA side of the add-on, using small stand-ins for NVDA's modules.
Run: python -m unittest discover -s tests
"""

import builtins
import enum
import os
import sys
import time
import types
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _module(name, **attrs):
	module = types.ModuleType(name)
	module.__dict__.update(attrs)
	sys.modules[name] = module
	return module


class FakeTimer:
	"""Stands in for wx.CallLater; tests fire timers by hand."""

	pending = []

	def __init__(self, ms, func, *args, **kwargs):
		self.func, self.args, self.kwargs = func, args, kwargs
		self.stopped = False
		FakeTimer.pending.append(self)

	def Stop(self):
		self.stopped = True

	@classmethod
	def fireAll(cls):
		timers, cls.pending = cls.pending, []
		for timer in timers:
			if not timer.stopped:
				timer.func(*timer.args, **timer.kwargs)


class FakeWavePlayer:
	fed = []

	def __init__(self, **kwargs):
		self.kwargs = kwargs

	def stop(self):
		pass

	def feed(self, data):
		FakeWavePlayer.fed.append(len(data))

	def idle(self):
		pass


class State(enum.Enum):
	INVISIBLE = 1
	OFFSCREEN = 2


beeps = []
messages = []
windowTitles = {}


class FakeProgressBar:
	"""Behaves like NVDA's ProgressBar.event_valueChange for the beep."""

	def __init__(self, percent, handle=1, name="", location=(0, 0, 100, 10)):
		self.value = f"{percent}%"
		self.windowHandle = handle
		self.name = name
		self.location = location
		self.states = set()
		self.isInForeground = True
		self.parent = None

	def event_valueChange(self):
		percent = float(self.value.strip("%"))
		sys.modules["tones"].beep(110 * 2 ** (percent / 25.0), 40)


def installStubs():
	builtins._ = lambda text: text
	_module("addonHandler", initTranslation=lambda: None)

	class Conf(dict):
		spec = {}

	conf = Conf(
		audio={"outputDevice": "default"},
		presentation={
			"progressBarUpdates": {
				"beepMinHZ": 110,
				"progressBarOutputMode": "beep",
				"reportBackgroundProgressBars": False,
			},
		},
	)
	_module("config", conf=conf)
	_module("controlTypes", State=State)
	_module(
		"globalPluginHandler",
		GlobalPlugin=type("GlobalPlugin", (), {"__init__": lambda self: None, "terminate": lambda self: None}),
	)
	_module("nvwave", WavePlayer=FakeWavePlayer, AudioPurpose=types.SimpleNamespace(SOUNDS="sounds"))
	_module("tones", beep=lambda hz, length, *args, **kwargs: beeps.append(hz))
	_module("ui", message=messages.append)
	_module(
		"winUser",
		GA_ROOT=2,
		getAncestor=lambda hwnd, flags: hwnd,
		getWindowText=lambda hwnd: windowTitles.get(hwnd, ""),
	)
	_module("wx", CallLater=FakeTimer)
	gui = _module("gui", messageBox=None)
	gui.guiHelper = _module("gui.guiHelper")
	gui.nvdaControls = _module("gui.nvdaControls")
	gui.settingsDialogs = _module(
		"gui.settingsDialogs",
		NVDASettingsDialog=type("NVDASettingsDialog", (), {"categoryClasses": []}),
		SettingsPanel=object,
	)
	_module("logHandler", log=types.SimpleNamespace(warning=print, exception=print, debugWarning=print))
	_module("NVDAObjects")
	_module("NVDAObjects.behaviors", ProgressBar=FakeProgressBar)
	_module("scriptHandler", script=lambda **kwargs: (lambda func: func))


installStubs()
sys.path.insert(0, os.path.join(ROOT, "addon", "globalPlugins"))
import progressPulse  # noqa: E402

CONF = sys.modules["config"].conf
DEFAULTS = dict(
	enabled=True,
	soundFile="builtin:drop",
	startSoundFile="",
	halfwaySoundFile="",
	finishSoundFile="builtin:chime",
	pitchChange="medium",
	stereoPan=False,
	volume=80,
	overlap=False,
	announceFinish=True,
)


class PluginTests(unittest.TestCase):
	def setUp(self):
		CONF["progressPulse"] = dict(DEFAULTS)
		CONF["presentation"]["progressBarUpdates"]["progressBarOutputMode"] = "beep"
		beeps.clear()
		messages.clear()
		windowTitles.clear()
		FakeWavePlayer.fed.clear()
		FakeTimer.pending = []
		progressPulse._tracker = progressPulse.ProgressTracker()
		progressPulse._announcer = progressPulse.FinishAnnouncer()
		self.plugin = progressPulse.GlobalPlugin()
		self.addCleanup(self.plugin.terminate)
		self.played = []
		realParams = progressPulse.audio.soundParams

		def recordParams(percent, *args):
			self.played.append(round(percent))
			return realParams(percent, *args)

		progressPulse.audio.soundParams = recordParams
		self.addCleanup(setattr, progressPulse.audio, "soundParams", realParams)

	def update(self, percent, **kwargs):
		FakeProgressBar(percent, **kwargs).event_valueChange()
		# Leave a gap so sounds aren't skipped as too close together.
		time.sleep(progressPulse.MIN_GAP_SECONDS + 0.02)

	def test_replacesBeepAndRestoresTones(self):
		realBeep = sys.modules["tones"].beep
		for percent in (0, 37, 100):
			self.update(percent)
		self.assertEqual(self.played, [0, 37, 100])
		self.assertEqual(beeps, [])
		self.assertIs(sys.modules["tones"].beep, realBeep)
		time.sleep(0.2)
		self.assertEqual(len(FakeWavePlayer.fed), 3)

	def test_disabledUsesNvdaBeep(self):
		CONF["progressPulse"]["enabled"] = False
		self.update(50)
		self.assertEqual([round(hz) for hz in beeps], [440])
		self.assertEqual(self.played, [])

	def test_differentBarsTooCloseTogetherAreSkipped(self):
		FakeProgressBar(20, location=(0, 0, 100, 10)).event_valueChange()
		FakeProgressBar(60, location=(0, 50, 100, 10)).event_valueChange()
		time.sleep(0.2)
		self.assertEqual(len(FakeWavePlayer.fed), 1)

	def test_oneFastBarPlaysEveryStep(self):
		# A progress bar moving 1% at a time faster than the gap still gets a sound for every step,
		# following NVDA's beep interval.
		for percent in range(20, 31):
			FakeProgressBar(percent).event_valueChange()
		self.assertEqual(self.played, list(range(20, 31)))

	def test_milestoneSoundsAlwaysPlay(self):
		FakeProgressBar(98).event_valueChange()
		FakeProgressBar(100).event_valueChange()
		# The finish sound plays at its own pitch even right after another sound.
		self.assertEqual(self.played, [98, 100])

	def test_trackerEvents(self):
		tracker = progressPulse.ProgressTracker()
		events = [tracker.update("bar", p) for p in (0, 30, 60, 99, 100, 100, 5)]
		self.assertEqual(events, ["start", None, "halfway", None, "finish", None, "start"])
		self.assertIsNone(progressPulse.ProgressTracker().update("bar", 40))

	def test_finishAnnouncement(self):
		windowTitles[7] = "Extracting from photos.rar"
		self.update(50, handle=7)
		self.update(100, handle=7)
		self.assertEqual(messages, [])
		FakeTimer.fireAll()
		self.assertEqual(messages, ["Extraction complete"])

	def test_finishAnnouncementCancelledWhenBarRestarts(self):
		windowTitles[7] = "Downloading files"
		self.update(50, handle=7)
		self.update(100, handle=7)
		self.update(0, handle=7)
		FakeTimer.fireAll()
		self.assertEqual(messages, [])

	def test_finishAnnouncementNotRepeated(self):
		windowTitles[7] = "Downloading"
		for location in ((0, 0, 100, 10), (0, 50, 100, 10)):
			self.update(50, handle=7, location=location)
			self.update(100, handle=7, location=location)
		FakeTimer.fireAll()
		self.assertEqual(messages, ["Download complete"])

	def test_finishAnnouncementWorksWithSoundsOff(self):
		CONF["progressPulse"]["enabled"] = False
		self.update(50)
		self.update(100)
		FakeTimer.fireAll()
		self.assertEqual(messages, ["Progress complete"])

	def test_progressOutputOffDoesNothing(self):
		CONF["presentation"]["progressBarUpdates"]["progressBarOutputMode"] = "off"
		self.update(50)
		self.update(100)
		FakeTimer.fireAll()
		self.assertEqual((self.played, messages), ([], []))

	def test_unknownWindowUsesTitle(self):
		windowTitles[3] = "My Program"
		bar = FakeProgressBar(100, handle=3)
		self.assertEqual(progressPulse.finishMessage(bar), "Progress complete, My Program")
		windowTitles[3] = "100% Complete"
		self.assertEqual(progressPulse.finishMessage(bar), "Progress complete")

	def test_missingFileFallsBackToBuiltIn(self):
		CONF["progressPulse"]["soundFile"] = os.path.join(ROOT, "missing.wav")
		self.update(50)
		self.assertEqual(self.played, [50])

	def test_noRegularSoundIsSilent(self):
		CONF["progressPulse"]["soundFile"] = ""
		self.update(30)
		self.update(40)
		self.assertEqual((self.played, beeps), ([], []))
		# The finished sound still plays.
		self.update(100)
		self.assertEqual(self.played, [100])

	def test_builtInSoundsLoad(self):
		loader = progressPulse.SoundLoader()
		for name, _label in progressPulse.BUILT_IN_SOUNDS:
			with self.subTest(name):
				self.assertIsNotNone(loader.load(progressPulse.BUILT_IN_PREFIX + name))

	def test_outputDeviceInOlderNvda(self):
		self.assertEqual(progressPulse.outputDevice(), "default")
		audioSection = CONF.pop("audio")
		self.addCleanup(CONF.__setitem__, "audio", audioSection)
		CONF["audio"] = {}
		CONF["speech"] = {"outputDevice": "Speakers"}
		self.assertEqual(progressPulse.outputDevice(), "Speakers")

	def test_terminateRestoresNvda(self):
		self.plugin.terminate()
		self.assertIs(FakeProgressBar.event_valueChange, progressPulse._originalEventValueChange)
		self.assertNotIn(
			progressPulse.ProgressPulsePanel,
			sys.modules["gui.settingsDialogs"].NVDASettingsDialog.categoryClasses,
		)


if __name__ == "__main__":
	unittest.main()
