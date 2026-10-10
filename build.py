"""Builds the .nvda-addon package from the addon folder.

Run: python build.py
Print the version: python build.py --version

The add-on's details (name, description, version and so on) are in addon/manifest.ini.
The Add-on Store shows them, so edit that file before each release.
The add-on's help page is made from README.md.
"""

import html
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.join(ROOT, "addon")
MANIFEST = os.path.join(ADDON_DIR, "manifest.ini")
SOUNDS_DIR = os.path.join(ADDON_DIR, "globalPlugins", "progressPulse", "sounds")
REQUIRED_KEYS = (
	"name",
	"summary",
	"description",
	"author",
	"version",
	"minimumNVDAVersion",
	"lastTestedNVDAVersion",
)


def readManifest():
	"""Read the manifest's keys, including multi-line values in triple quotes."""
	with open(MANIFEST, encoding="utf-8") as f:
		text = f.read()
	values = {}
	for match in re.finditer(r'^(\w+)\s*=\s*("""(.*?)"""|"([^"\n]*)"|([^\n]*))', text, re.M | re.S):
		key = match.group(1)
		value = next(group for group in match.groups()[2:] if group is not None)
		values[key] = value.strip()
	return values


def checkManifest(manifest):
	"""Catch mistakes the Add-on Store would reject."""
	problems = [f"{key} is missing" for key in REQUIRED_KEYS if not manifest.get(key)]
	if not re.fullmatch(r"[A-Za-z0-9_-]+", manifest.get("name", "")):
		problems.append("name may only contain letters, numbers, underscores and hyphens")
	if not re.fullmatch(r"\d+\.\d+(\.\d+)?", manifest.get("version", "")):
		problems.append("version must look like 1.0 or 1.0.0")
	for key in ("minimumNVDAVersion", "lastTestedNVDAVersion"):
		if not re.fullmatch(r"\d{4}\.\d+(\.\d+)?", manifest.get(key, "")):
			problems.append(f"{key} must look like 2026.2.0")
	url = manifest.get("url")
	if url and not url.startswith("https://"):
		problems.append("url must start with https://")
	if problems:
		raise SystemExit("Problems in addon/manifest.ini:\n- " + "\n- ".join(problems))
	if url and "USERNAME" in url:
		print("Warning: replace USERNAME in the url in addon/manifest.ini with your GitHub user name.")


def _inline(text):
	text = html.escape(text, quote=False)
	text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
	text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
	return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)


def markdownToHtml(markdown, title):
	"""Enough Markdown for the readme: headings, paragraphs, lists, bold, code and links."""
	body = []
	paragraph = []
	listTag = None

	def flushParagraph():
		if paragraph:
			body.append(f"<p>{_inline(' '.join(paragraph))}</p>")
			paragraph.clear()

	def closeList():
		nonlocal listTag
		if listTag:
			body.append(f"</{listTag}>")
			listTag = None

	for raw in markdown.splitlines():
		line = raw.strip()
		heading = re.match(r"(#{1,6})\s+(.*)", line)
		item = re.match(r"(?:[-*]|(\d+)\.)\s+(.*)", line)
		if not line:
			flushParagraph()
			closeList()
		elif heading:
			flushParagraph()
			closeList()
			level = len(heading.group(1))
			body.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
		elif item:
			flushParagraph()
			tag = "ol" if item.group(1) else "ul"
			if listTag != tag:
				closeList()
				body.append(f"<{tag}>")
				listTag = tag
			body.append(f"<li>{_inline(item.group(2))}</li>")
		elif listTag and raw.startswith((" ", "\t")):
			body[-1] = body[-1][: -len("</li>")] + " " + _inline(line) + "</li>"
		else:
			closeList()
			paragraph.append(line)
	flushParagraph()
	closeList()
	return (
		'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
		f"<title>{html.escape(title)}</title>\n</head>\n<body>\n" + "\n".join(body) + "\n</body>\n</html>\n"
	)


def main():
	manifest = readManifest()
	if "--version" in sys.argv:
		print(manifest["version"])
		return
	checkManifest(manifest)
	if not os.path.isdir(SOUNDS_DIR) or not os.listdir(SOUNDS_DIR):
		raise SystemExit("The built-in sounds are missing. Run: python tools/makeSounds.py")
	with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
		readme = markdownToHtml(f.read(), manifest["summary"])
	out = os.path.join(ROOT, f"{manifest['name']}-{manifest['version']}.nvda-addon")
	with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
		if manifest.get("docFileName"):
			z.writestr(f"doc/en/{manifest['docFileName']}", readme.encode("utf-8"))
		for folder, dirs, files in os.walk(ADDON_DIR):
			dirs[:] = sorted(d for d in dirs if d != "__pycache__")
			for file in sorted(files):
				full = os.path.join(folder, file)
				z.write(full, os.path.relpath(full, ADDON_DIR).replace(os.sep, "/"))
	print(f"Built {out}")


if __name__ == "__main__":
	main()
