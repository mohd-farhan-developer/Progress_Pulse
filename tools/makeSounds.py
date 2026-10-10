"""Creates the add-on's built-in sounds. They are synthesised here, so there are no licensing worries.
Run: python tools/makeSounds.py
"""

import math
import os
import random
import struct
import wave

RATE = 44100
SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "addon", "globalPlugins", "progressPulse", "sounds")


def write(name, samples, peak=0.6):
	"""Normalise to peak, add tiny fades so there are no clicks, and save as 16 bit mono WAV."""
	loudest = max(abs(s) for s in samples) or 1.0
	samples = [s * peak / loudest for s in samples]
	fadeIn = int(RATE * 0.002)
	fadeOut = int(RATE * 0.01)
	for i in range(min(fadeIn, len(samples))):
		samples[i] *= i / fadeIn
	for i in range(min(fadeOut, len(samples))):
		samples[-1 - i] *= i / fadeOut
	os.makedirs(SOUNDS_DIR, exist_ok=True)
	with wave.open(os.path.join(SOUNDS_DIR, name + ".wav"), "wb") as w:
		w.setnchannels(1)
		w.setsampwidth(2)
		w.setframerate(RATE)
		w.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in samples))


def times(seconds):
	return [i / RATE for i in range(int(RATE * seconds))]


def drop():
	"""A soft water drop: a sine gliding up slightly, fading quickly."""
	out = []
	phase = 0.0
	duration = 0.09
	for t in times(duration):
		phase += 2 * math.pi * (700 + 250 * t / duration) / RATE
		envelope = min(1.0, t / 0.004) * math.exp(-t / 0.025)
		out.append(envelope * (math.sin(phase) + 0.15 * math.sin(2 * phase)))
	return out


def tick():
	"""A short wooden tick, like a clock."""
	rng = random.Random(1)
	out = []
	for t in times(0.045):
		body = math.exp(-t / 0.006) * (math.sin(2 * math.pi * 1900 * t) + 0.5 * math.sin(2 * math.pi * 3150 * t))
		noise = math.exp(-t / 0.0015) * (rng.random() * 2 - 1) * 0.4
		out.append(body + noise)
	return out


def marimba(freq=523.25, duration=0.35):
	"""A mellow marimba note. Marimba bars have a strong overtone near four times the fundamental."""
	out = []
	for t in times(duration):
		out.append(
			math.exp(-t / 0.11) * math.sin(2 * math.pi * freq * t)
			+ 0.35 * math.exp(-t / 0.025) * math.sin(2 * math.pi * freq * 3.93 * t)
			+ 0.15 * math.exp(-t / 0.008) * math.sin(2 * math.pi * freq * 9.2 * t)
		)
	return out


def bubble():
	"""A small bubble: a quick upward sweep."""
	out = []
	phase = 0.0
	duration = 0.08
	for t in times(duration):
		fraction = t / duration
		phase += 2 * math.pi * 380 * (3.0**fraction) / RATE
		out.append(math.sin(math.pi * fraction) ** 1.5 * math.sin(phase))
	return out


def chime():
	"""A bright three note chime going up (C, E, G), for when something finishes."""
	notes = (1046.5, 1318.5, 1568.0)
	spacing = 0.09
	duration = spacing * len(notes) + 0.6
	out = [0.0] * int(RATE * duration)
	for n, freq in enumerate(notes):
		start = int(RATE * spacing * n)
		for i, t in enumerate(times(duration - spacing * n)):
			value = math.exp(-t / 0.22) * (
				math.sin(2 * math.pi * freq * t)
				+ 0.3 * math.exp(-t / 0.06) * math.sin(2 * math.pi * freq * 2.76 * t)
				+ 0.12 * math.exp(-t / 0.03) * math.sin(2 * math.pi * freq * 5.4 * t)
			)
			out[start + i] += value * min(1.0, t / 0.003)
	return out


def main():
	write("drop", drop())
	write("tick", tick(), peak=0.5)
	write("marimba", marimba())
	write("bubble", bubble())
	write("chime", chime(), peak=0.5)
	print(f"Sounds written to {os.path.normpath(SOUNDS_DIR)}")


if __name__ == "__main__":
	main()
