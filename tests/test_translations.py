"""Tests for turning translators' .po files into the .mo files NVDA reads."""

import gettext
import glob
import io
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from tools.translations import compilePo, makePot, readPo  # noqa: E402

SAMPLE = r'''msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\n"

#. Translators: a comment
#: file.py:1
msgid "Water drop"
msgstr "Gota de agua"

msgid ""
"Two\n"
"lines with \"quotes\""
msgstr ""
"Dos\n"
"líneas con \"comillas\""

#, fuzzy
msgid "Unchecked"
msgstr "Not reviewed yet"

msgid "Untranslated"
msgstr ""

msgctxt "menu"
msgid "Open"
msgstr "Abrir"

msgid "{count} sound"
msgid_plural "{count} sounds"
msgstr[0] "{count} sonido"
msgstr[1] "{count} sonidos"
'''


def load(poText):
	with tempfile.TemporaryDirectory() as folder:
		path = os.path.join(folder, "nvda.po")
		with open(path, "w", encoding="utf-8") as f:
			f.write(poText)
		mo, catalog = compilePo(path)
	return gettext.GNUTranslations(io.BytesIO(mo)), catalog


class CompileTests(unittest.TestCase):
	def test_roundTrip(self):
		t, _catalog = load(SAMPLE)
		self.assertEqual(t.gettext("Water drop"), "Gota de agua")
		self.assertEqual(t.gettext('Two\nlines with "quotes"'), 'Dos\nlíneas con "comillas"')
		self.assertEqual(t.pgettext("menu", "Open"), "Abrir")
		self.assertEqual(t.ngettext("{count} sound", "{count} sounds", 1), "{count} sonido")
		self.assertEqual(t.ngettext("{count} sound", "{count} sounds", 3), "{count} sonidos")

	def test_fuzzyAndEmptyStayEnglish(self):
		t, catalog = load(SAMPLE)
		self.assertEqual(t.gettext("Unchecked"), "Unchecked")
		self.assertEqual(t.gettext("Untranslated"), "Untranslated")
		self.assertNotIn("Unchecked", catalog)


class AddonTranslationTests(unittest.TestCase):
	def test_everyTranslationCompilesAndKeepsPlaceholders(self):
		files = glob.glob(os.path.join(ROOT, "addon", "locale", "*", "LC_MESSAGES", "nvda.po"))
		for path in files:
			catalog = readPo(path)
			for original, translated in catalog.items():
				if not original:
					continue
				with self.subTest(language=path.split(os.sep)[-3], text=original):
					# A missing or renamed {placeholder} would break or crash the message in NVDA.
					self.assertEqual(sorted(re.findall(r"\{\w*\}", original)), sorted(re.findall(r"\{\w*\}", translated)))
			compilePo(path)

	def test_potHasEveryText(self):
		source = os.path.join(ROOT, "addon", "globalPlugins", "progressPulse", "__init__.py")
		with tempfile.TemporaryDirectory() as folder:
			pot = os.path.join(folder, "test.pot")
			count = makePot(source, "x.py", pot, "test")
			with open(pot, encoding="utf-8") as f:
				text = f.read()
		self.assertGreater(count, 50)
		self.assertIn('msgid "Download complete"', text)
		self.assertIn("#. Translators: announced when a progress bar finishes.", text)


if __name__ == "__main__":
	unittest.main()
