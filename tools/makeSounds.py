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


def bandpass(samples, cutoffs, q):
	"""A resonant filter whose centre frequency can move, for whooshes and knocks."""
	low = band = 0.0
	out = []
	for x, cutoff in zip(samples, cutoffs):
		f = 2 * math.sin(math.pi * min(cutoff, 6000) / RATE)
		low += f * band
		high = x - low - band / q
		band += f * high
		out.append(band)
	return out


def bellNote(freq, duration, ring, brightness=1.0):
	"""A soft bell: a few uneven overtones that fade at different speeds."""
	out = []
	for t in times(duration):
		value = math.sin(2 * math.pi * freq * t) * math.exp(-t * 6.9 / ring)
		value += 0.25 * brightness * math.sin(2 * math.pi * freq * 2.76 * t) * math.exp(-t * 6.9 / (ring * 0.35))
		value += 0.1 * brightness * math.sin(2 * math.pi * freq * 5.4 * t) * math.exp(-t * 6.9 / (ring * 0.15))
		out.append(value * min(1.0, t / 0.003))
	return out


def mix(length, *parts):
	"""Mix (start time, samples) pairs into one sound."""
	out = [0.0] * int(RATE * length)
	for start, samples in parts:
		offset = int(RATE * start)
		for i, value in enumerate(samples[: len(out) - offset]):
			out[offset + i] += value
	return out


def kalimba(freq=659.26):
	"""A thumb piano note: a pure, sweet tone with a quick metallic overtone at the start."""
	out = []
	for t in times(0.6):
		value = math.sin(2 * math.pi * freq * t) * math.exp(-t * 6.9 / 0.55)
		value += 0.3 * math.sin(2 * math.pi * freq * 5.9 * t) * math.exp(-t * 6.9 / 0.05)
		out.append(value * min(1.0, t / 0.002))
	return out


def glassTap(freq=1396.9):
	"""A light tap on a glass: a clear high ring with a gentle shimmer."""
	out = []
	for t in times(0.45):
		value = (math.sin(2 * math.pi * freq * t) + math.sin(2 * math.pi * freq * 1.003 * t)) * math.exp(-t * 6.9 / 0.4)
		value += 0.3 * math.sin(2 * math.pi * freq * 2.71 * t) * math.exp(-t * 6.9 / 0.1)
		out.append(value * min(1.0, t / 0.001))
	return out


def woodKnock():
	"""A soft knock on wood: two low resonances that stop almost at once."""
	rng = random.Random(3)
	hit = [rng.random() * 2 - 1 for _ in range(int(RATE * 0.12))]
	hit = [x * math.exp(-i / RATE / 0.004) for i, x in enumerate(hit)]
	body = bandpass(hit, [420] * len(hit), 12)
	ring = bandpass(hit, [1150] * len(hit), 10)
	return [b + 0.4 * r for b, r in zip(body, ring)]


def softPluck(freq=329.63, duration=0.55):
	"""A gentle guitar string pluck (Karplus-Strong): a burst of noise circling a short loop, mellowing as it goes."""
	rng = random.Random(4)
	period = int(RATE / freq)
	loop = [rng.random() * 2 - 1 for _ in range(period)]
	# Soften the pluck so it sounds like a fingertip rather than a pick.
	for _ in range(3):
		loop = [(loop[i] + loop[i - 1]) / 2 for i in range(period)]
	# Centre the loop on zero, or the string would carry a constant offset that wastes loudness.
	average = sum(loop) / period
	loop = [x - average for x in loop]
	out = []
	for i in range(int(RATE * duration)):
		value = loop[i % period]
		loop[i % period] = 0.996 * 0.5 * (value + loop[(i + 1) % period])
		out.append(value)
	return out


def pop():
	"""A tiny soft pop, like a small bubble bursting."""
	out = []
	phase = 0.0
	for t in times(0.05):
		phase += 2 * math.pi * (300 + 700 * min(1.0, t / 0.012)) / RATE
		out.append(math.sin(phase) * min(1.0, t / 0.002) * math.exp(-t / 0.012))
	return out


def risingWhoosh():
	"""A short airy sweep upward, for when something starts."""
	rng = random.Random(5)
	duration = 0.45
	noise = [rng.random() * 2 - 1 for _ in range(int(RATE * duration))]
	cutoffs = [300 * (10 ** (i / len(noise))) for i in range(len(noise))]
	air = bandpass(noise, cutoffs, 3)
	out = []
	for i, value in enumerate(air):
		t = i / RATE
		shape = min(1.0, t / 0.3) * min(1.0, (duration - t) / 0.08)
		out.append(value * shape)
	return out


def dingDong():
	"""Two soft bell notes, high then low, for the halfway point."""
	return mix(1.05, (0.0, bellNote(659.26, 0.7, 0.6)), (0.3, bellNote(523.25, 0.75, 0.7)))


def singleBell():
	"""One clear, calm bell, for when something finishes."""
	return bellNote(880.0, 1.5, 1.3)


def levelComplete():
	"""A quick happy rise of four notes (C, E, G, high C), like finishing a level in a game."""
	notes = (523.25, 659.26, 783.99, 1046.5)
	parts = []
	for n, freq in enumerate(notes):
		last = n == len(notes) - 1
		length = 0.45 if last else 0.12
		tone = []
		for t in times(length):
			value = math.sin(2 * math.pi * freq * t) + 0.3 * math.sin(6 * math.pi * freq * t) + 0.12 * math.sin(10 * math.pi * freq * t)
			tone.append(value * min(1.0, t / 0.004) * math.exp(-t * 6.9 / (0.45 if last else 0.2)))
		parts.append((0.09 * n, tone))
	return mix(0.09 * 3 + 0.45, *parts)


def main():
	write("drop", drop())
	write("tick", tick(), peak=0.5)
	write("marimba", marimba())
	write("bubble", bubble())
	write("chime", chime(), peak=0.5)
	write("kalimba", kalimba())
	write("glass", glassTap(), peak=0.45)
	write("wood", woodKnock(), peak=0.85)
	write("pluck", softPluck())
	write("pop", pop(), peak=0.5)
	write("whoosh", risingWhoosh(), peak=0.5)
	write("dingdong", dingDong(), peak=0.5)
	write("bell", singleBell(), peak=0.5)
	write("levelup", levelComplete(), peak=0.45)
	print(f"Sounds written to {os.path.normpath(SOUNDS_DIR)}")


if __name__ == "__main__":
	main()
