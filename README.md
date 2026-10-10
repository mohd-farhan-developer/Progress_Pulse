# Progress Pulse

Progress Pulse lets you replace NVDA's progress bar beeps with sounds you like.
You can pick your own sound files, have a different sound when a progress bar starts, reaches half way and finishes, and hear NVDA say something like "Download complete" when it is done.

## What it does

* Plays a pleasant sound instead of NVDA's beep whenever a progress bar moves. Choose from five built-in sounds (Water drop, Soft tick, Marimba, Bubble and Success chime) or use your own sound files.
* The pitch of the sound goes up as the progress goes up, so you can hear how far along it is.
* Optional: the sound moves from your left ear to your right ear as the progress goes up.
* Optional separate sounds for when a progress bar starts, reaches 50%, and reaches 100%.
* When a progress bar finishes, NVDA says what finished, for example "Download complete", "Extraction complete", "Copy complete" or "Installation complete".
* When several progress bars move at the same time, the sounds stay clean instead of choppy. You can also let them overlap.

## Getting started

1. Install the add-on and restart NVDA.
2. Open the NVDA menu (NVDA+N), go to Preferences, then Settings.
3. Choose "Progress Pulse" in the list of categories.
4. Change what you like, then press OK.

The add-on works straight away, so you don't have to change anything: progress plays the Water drop sound, and the Success chime plays when a progress bar finishes.

## Settings

* **Play my sounds for progress bars instead of NVDA's beeps**: turn the add-on's sounds on or off. When off, you hear NVDA's normal beeps.
* **Sound to change**: pick which sound you want to set:
  * Regular sound: plays every time the progress goes up.
  * Start sound: plays when a progress bar begins.
  * Halfway sound: plays when a progress bar reaches 50%.
  * Finished sound: plays when a progress bar reaches 100%.
* **Sound**: choose the sound. Each sound plays as you move through the list, so you can hear it before choosing. The choices are:
  * None. For the start, halfway and finished sounds, the regular sound plays instead. For the regular sound, progress is silent and only the start, halfway and finished sounds play.
  * One of the five built-in sounds: Water drop, Soft tick, Marimba, Bubble or Success chime.
  * Your own file.
* **Choose your own file**: pick a WAV file from your computer. It plays once so you can hear it.
* **Play**: listen to the selected sound again.
* **How much the pitch rises as progress goes up**: No change, A little, Medium or A lot. At 50% your sound always plays at its normal pitch. Start, halfway and finished sounds always play at their normal pitch.
* **Move the sound from left ear to right ear as progress goes up**: 0% plays in your left ear and 100% in your right ear.
* **Volume**: from 0 to 100.
* **Let sounds overlap when several progress bars move at the same time**: when off, a new sound stops the one playing. When on, up to three sounds can play together.
* **Announce when a progress bar finishes**: NVDA says what finished, for example "Download complete". This works even when the add-on's sounds are turned off.
* **Test all sounds**: plays your sounds from 0% to 100% using the settings on screen, before you save them.

## Good to know

* Sound files must be WAV files. If you have an MP3, convert it to WAV first, for example with Audacity or GoldWave.
* Short sounds work best (under half a second). Longer files are cut to 3 seconds, and silence at the start of a file is skipped so the sound plays right away.
* Keep your sound files where they are. If a file is moved or deleted, the add-on uses the Water drop sound instead.
* NVDA's own progress bar settings still apply. In NVDA Settings, Object Presentation, "Progress bar output" must be set to "Beep" or "Speak and beep" to hear sounds. "Report background progress bars" decides whether progress bars in other windows make sounds.
* The finished announcement is chosen from the window title, so it works best in English windows. For other windows NVDA says "Progress complete" and the window's title.
* If a progress bar closes before reaching 100%, there is no finished sound or announcement.

## Keyboard command

You can set a key to turn the add-on's sounds on and off quickly. Open the NVDA menu, go to Preferences, then Input Gestures, open the "Progress Pulse" category and add a gesture to "Turns Progress Pulse sounds on or off".

## Requirements

NVDA 2022.1 or later, including NVDA 2023.3 for Windows 7 and 8. The add-on was built against NVDA 2025.3 and 2026.2.

## Changes

### Version 1.0.0

* First release.

## License

Progress Pulse is free software under the GNU General Public License version 2. See the LICENSE file.
