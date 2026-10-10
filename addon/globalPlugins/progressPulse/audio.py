# Progress Pulse - sound file loading and processing.
# Copyright (C) 2026 Mohd Farhan Hussain
# This file is covered by the GNU General Public License version 2. See LICENSE.
# This module has no NVDA imports so it can be tested outside NVDA.

import math
import struct
from array import array

OUTPUT_RATE = 44100
# Longer files are cut to this length so a progress update never plays a whole song.
MAX_SECONDS = 3.0
# Samples quieter than this at the start of a file are trimmed, so the sound plays without delay.
SILENCE_THRESHOLD = 0.002
FADE_SECONDS = 0.01

WAVE_FORMAT_PCM = 0x0001
WAVE_FORMAT_IEEE_FLOAT = 0x0003
WAVE_FORMAT_EXTENSIBLE = 0xFFFE


class SoundFileError(Exception):
	"""Raised when a sound file can't be read."""


class Sound:
	"""A mono sound held as floats between -1 and 1."""

	def __init__(self, samples, rate):
		self.samples = samples
		self.rate = rate

	@property
	def duration(self):
		return len(self.samples) / self.rate

	def render(self, pitch=1.0, left=1.0, right=1.0):
		"""Return 16 bit stereo PCM at OUTPUT_RATE.
		@param pitch: playback speed factor; 2.0 is one octave up.
		@param left: gain for the left channel.
		@param right: gain for the right channel.
		"""
		src = self.samples
		n = len(src)
		if n == 0:
			return b""
		step = self.rate / OUTPUT_RATE * pitch
		outLen = int((n - 1) / step) + 1
		out = array("h", bytes(outLen * 4))
		leftScale = left * 32767
		rightScale = right * 32767
		last = n - 1
		pos = 0.0
		for i in range(outLen):
			idx = int(pos)
			a = src[idx]
			if idx < last:
				a += (src[idx + 1] - a) * (pos - idx)
			if a > 1.0:
				a = 1.0
			elif a < -1.0:
				a = -1.0
			out[2 * i] = int(a * leftScale)
			out[2 * i + 1] = int(a * rightScale)
			pos += step
		return out.tobytes()


def _readFormatAndData(f):
	header = f.read(12)
	if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
		raise SoundFileError("This is not a WAV file.")
	fmt = None
	while True:
		chunkHeader = f.read(8)
		if len(chunkHeader) < 8:
			raise SoundFileError("The file has no sound data.")
		chunkId = chunkHeader[:4]
		size = struct.unpack("<I", chunkHeader[4:])[0]
		if chunkId == b"fmt ":
			fmt = _parseFormat(f.read(size))
			if size & 1:
				f.read(1)
		elif chunkId == b"data":
			if fmt is None:
				raise SoundFileError("The file's format information is missing.")
			formatTag, channels, rate, sampleWidth = fmt
			frameSize = channels * sampleWidth
			wanted = int(rate * MAX_SECONDS) * frameSize
			data = f.read(min(size, wanted))
			truncated = size > wanted
			data = data[: len(data) - len(data) % frameSize]
			return fmt, data, truncated
		else:
			f.seek(size + (size & 1), 1)


def _parseFormat(body):
	if len(body) < 16:
		raise SoundFileError("The file's format information is damaged.")
	formatTag, channels, rate, _byteRate, blockAlign, bits = struct.unpack_from("<HHIIHH", body)
	if formatTag == WAVE_FORMAT_EXTENSIBLE and len(body) >= 26:
		# The first two bytes of the sub format GUID hold the real format tag.
		formatTag = struct.unpack_from("<H", body, 24)[0]
	if channels < 1 or rate < 1 or blockAlign < 1:
		raise SoundFileError("The file's format information is damaged.")
	sampleWidth = blockAlign // channels
	if formatTag == WAVE_FORMAT_PCM:
		if sampleWidth not in (1, 2, 3, 4):
			raise SoundFileError(f"{bits} bit sound is not supported.")
	elif formatTag == WAVE_FORMAT_IEEE_FLOAT:
		if sampleWidth not in (4, 8):
			raise SoundFileError(f"{bits} bit floating point sound is not supported.")
	else:
		raise SoundFileError(
			"This WAV file is compressed (for example ADPCM or MP3 inside WAV). Please save it as plain PCM WAV.",
		)
	return formatTag, channels, rate, sampleWidth


def _decode(formatTag, sampleWidth, data):
	"""Return interleaved samples as floats between -1 and 1."""
	if formatTag == WAVE_FORMAT_IEEE_FLOAT:
		return array("f" if sampleWidth == 4 else "d", data).tolist()
	if sampleWidth == 1:
		return [(v - 128) / 128.0 for v in data]
	if sampleWidth == 2:
		return [v / 32768.0 for v in array("h", data)]
	if sampleWidth == 3:
		fromBytes = int.from_bytes
		return [
			fromBytes(data[i : i + 3], "little", signed=True) / 8388608.0 for i in range(0, len(data), 3)
		]
	return [v / 2147483648.0 for v in array("i", data)]


def load(path):
	"""Load a WAV file as a L{Sound}.
	@raise SoundFileError: if the file can't be used.
	"""
	try:
		with open(path, "rb") as f:
			(formatTag, channels, rate, sampleWidth), data, truncated = _readFormatAndData(f)
	except OSError as e:
		raise SoundFileError(f"The file could not be opened: {e.strerror or e}")
	except struct.error:
		raise SoundFileError("The file is damaged.")
	interleaved = _decode(formatTag, sampleWidth, data)
	if channels == 1:
		mono = interleaved
	else:
		scale = 1.0 / channels
		mono = [sum(frame) * scale for frame in zip(*(interleaved[c::channels] for c in range(channels)))]
	start = 0
	while start < len(mono) and abs(mono[start]) < SILENCE_THRESHOLD:
		start += 1
	mono = mono[start:]
	if not mono:
		raise SoundFileError("The file is silent.")
	if truncated:
		fadeLen = min(len(mono), int(rate * FADE_SECONDS))
		for i in range(fadeLen):
			mono[-1 - i] *= i / fadeLen
	return Sound(array("f", mono), rate)


def soundParams(percent, pitchRange, stereoPan, volume):
	"""Work out how to play the sound for a progress value.
	@param percent: progress from 0 to 100.
	@param pitchRange: semitones between 0% and 100%; 50% plays at the file's own pitch. 0 keeps the pitch.
	@param volume: 0 to 100.
	@return: (pitch, left, right) for L{Sound.render}.
	"""
	fraction = min(max(percent, 0.0), 100.0) / 100.0
	pitch = 1.0
	if pitchRange:
		pitch = 2 ** ((fraction - 0.5) * pitchRange / 12.0)
	gain = min(max(volume, 0), 100) / 100.0
	left = right = gain
	if stereoPan:
		# Moves from the left ear at 0% to the right ear at 100%, staying full volume in the middle.
		angle = fraction * math.pi / 2
		left = gain * min(1.0, math.cos(angle) * math.sqrt(2))
		right = gain * min(1.0, math.sin(angle) * math.sqrt(2))
	return pitch, left, right
