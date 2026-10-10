"""Tests for sound loading and processing. Run: python -m unittest discover -s tests"""

import math
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "progressPulse"))
import audio  # noqa: E402

TONE = [0.5 * math.sin(2 * math.pi * 440 * i / 22050) for i in range(2205)]


def writeWav(path, formatTag, channels, rate, width, samples, extensible=False, leadingSilence=0):
	samples = [0.0] * leadingSilence + samples
	data = bytearray()
	for s in samples:
		for _c in range(channels):
			if formatTag == 3:
				data += struct.pack("<f" if width == 4 else "<d", s)
			elif width == 1:
				data += bytes([int(s * 127) + 128])
			elif width == 2:
				data += struct.pack("<h", int(s * 32767))
			elif width == 3:
				data += int(s * 8388607).to_bytes(3, "little", signed=True)
			else:
				data += struct.pack("<i", int(s * 2147483647))
	if extensible:
		guid = struct.pack("<H", formatTag) + bytes.fromhex("000000001000800000aa00389b71")
		fmt = struct.pack(
			"<HHIIHHHHI",
			0xFFFE,
			channels,
			rate,
			rate * channels * width,
			channels * width,
			width * 8,
			22,
			width * 8,
			3,
		) + guid
	else:
		fmt = struct.pack("<HHIIHH", formatTag, channels, rate, rate * channels * width, channels * width, width * 8)
	# An unrelated LIST chunk with an odd size checks that chunks are skipped and padded correctly.
	body = (
		b"WAVE"
		+ b"LIST" + struct.pack("<I", 3) + b"abc\x00"
		+ b"fmt " + struct.pack("<I", len(fmt)) + fmt
		+ b"data" + struct.pack("<I", len(data)) + data
	)
	with open(path, "wb") as f:
		f.write(b"RIFF" + struct.pack("<I", len(body)) + body)


class LoadTests(unittest.TestCase):
	def setUp(self):
		self.dir = tempfile.TemporaryDirectory()
		self.addCleanup(self.dir.cleanup)

	def path(self, name):
		return os.path.join(self.dir.name, name)

	def test_formats(self):
		cases = [
			("pcm8", 1, 1, 1, False),
			("pcm16stereo", 1, 2, 2, False),
			("pcm24extensible", 1, 2, 3, True),
			("pcm32", 1, 1, 4, False),
			("float32extensible", 3, 2, 4, True),
			("float64", 3, 1, 8, False),
		]
		for name, formatTag, channels, width, extensible in cases:
			with self.subTest(name):
				path = self.path(name + ".wav")
				writeWav(path, formatTag, channels, 22050, width, TONE, extensible, leadingSilence=500)
				sound = audio.load(path)
				self.assertEqual(sound.rate, 22050)
				# The leading silence (and the tone's first zero sample) is trimmed.
				self.assertEqual(len(sound.samples), len(TONE) - 1)
				self.assertAlmostEqual(max(abs(x) for x in sound.samples), 0.5, delta=0.01)

	def test_longFileIsCutAndFaded(self):
		path = self.path("long.wav")
		writeWav(path, 1, 2, 48000, 2, [0.3 * math.sin(i / 10) for i in range(48000 * 5)])
		sound = audio.load(path)
		self.assertAlmostEqual(sound.duration, audio.MAX_SECONDS, delta=0.01)
		self.assertEqual(sound.samples[-1], 0)

	def test_rejected(self):
		notWav = self.path("notwav.wav")
		with open(notWav, "wb") as f:
			f.write(b"hello world")
		adpcm = self.path("adpcm.wav")
		writeWav(adpcm, 2, 1, 22050, 2, TONE[:10])
		silent = self.path("silent.wav")
		writeWav(silent, 1, 1, 22050, 2, [0.0] * 100)
		for path in (notWav, adpcm, silent, self.path("missing.wav")):
			with self.subTest(os.path.basename(path)):
				with self.assertRaises(audio.SoundFileError):
					audio.load(path)


class RenderTests(unittest.TestCase):
	def test_pitchChangesLength(self):
		sound = audio.Sound(TONE, 22050)
		normal = sound.render(1.0, 1, 1)
		higher = sound.render(2.0, 1, 1)
		# 16 bit stereo at 44100: 4 bytes per frame, twice as many frames as the 22050 source.
		self.assertAlmostEqual(len(normal) / 4, len(TONE) * 2, delta=2)
		self.assertAlmostEqual(len(higher) / 4, len(TONE), delta=2)

	def test_channels(self):
		data = audio.Sound([0.5] * 10, 44100).render(1.0, 1.0, 0.0)
		left, right = struct.unpack_from("<hh", data)
		self.assertGreater(left, 16000)
		self.assertEqual(right, 0)


class SoundParamsTests(unittest.TestCase):
	def test_pitch(self):
		self.assertAlmostEqual(audio.soundParams(0, 12, False, 100)[0], 0.5 ** 0.5)
		self.assertAlmostEqual(audio.soundParams(50, 12, False, 100)[0], 1.0)
		self.assertAlmostEqual(audio.soundParams(100, 12, False, 100)[0], 2 ** 0.5)
		self.assertEqual(audio.soundParams(100, 0, False, 100)[0], 1.0)

	def test_panAndVolume(self):
		self.assertEqual(audio.soundParams(0, 0, True, 100)[1:], (1.0, 0.0))
		_pitch, left, right = audio.soundParams(50, 0, True, 50)
		self.assertAlmostEqual(left, 0.5)
		self.assertAlmostEqual(right, 0.5)
		_pitch, left, right = audio.soundParams(100, 0, True, 100)
		self.assertAlmostEqual(left, 0.0)
		self.assertAlmostEqual(right, 1.0)


if __name__ == "__main__":
	unittest.main()
