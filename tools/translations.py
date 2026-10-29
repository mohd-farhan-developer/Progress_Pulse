"""Translation helpers for the build, with no extra tools to install.

- compilePo: turns a translator's .po file into the .mo file NVDA reads.
- makePot: collects every translatable text from the add-on into a .pot template for translators.
"""

import ast
import datetime
import re
import struct


def _unquote(text):
	"""Read one "quoted" .po string, including escapes such as \\n and \\"."""
	return ast.literal_eval(text)


def readPo(path):
	"""Return {key: translation} for the finished entries in a .po file.
	The key is msgid, or msgctxt + "\\x04" + msgid; plural entries use "\\0" between forms.
	Fuzzy (unchecked) and empty translations are left out, so NVDA shows the original English instead.
	"""
	entries = []
	entry = None
	field = None

	def finish():
		if entry is not None:
			entries.append(entry)

	with open(path, encoding="utf-8-sig") as f:
		lines = f.read().splitlines()
	for number, line in enumerate(lines, start=1):
		line = line.strip()
		if not line:
			continue
		if line.startswith("#"):
			if line.startswith("#,") and "fuzzy" in line:
				if entry is not None and any(k.startswith("msgstr") for k in entry):
					finish()
					entry = None
				entry = entry or {}
				entry["fuzzy"] = True
			continue
		match = re.match(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[(\d+)\])?)\s+(".*")$', line)
		if match:
			keyword, index, value = match.groups()
			if keyword in ("msgctxt", "msgid") and entry is not None and any(k.startswith("msgstr") for k in entry):
				finish()
				entry = None
			if entry is None:
				entry = {}
			field = keyword
			entry[field] = _unquote(value)
			continue
		if line.startswith('"') and field and entry is not None:
			entry[field] += _unquote(line)
			continue
		raise ValueError(f"{path}, line {number}: can't read {line!r}")
	finish()

	catalog = {}
	for item in entries:
		if item.get("fuzzy") and item.get("msgid"):
			continue
		key = item.get("msgid", "")
		if "msgctxt" in item:
			key = item["msgctxt"] + "\x04" + key
		if "msgid_plural" in item:
			key += "\0" + item["msgid_plural"]
			forms = [item[k] for k in sorted((k for k in item if k.startswith("msgstr[")), key=lambda k: int(k[7:-1]))]
			value = "\0".join(forms)
			if not any(forms):
				continue
		else:
			value = item.get("msgstr", "")
			if not value:
				continue
		catalog[key] = value
	return catalog


def moBytes(catalog):
	"""A GNU .mo file (the format Python's gettext and NVDA read) as bytes."""
	keys = sorted(catalog)
	ids = [k.encode("utf-8") for k in keys]
	strs = [catalog[k].encode("utf-8") for k in keys]
	count = len(keys)
	headerSize = 7 * 4
	idTable = headerSize
	strTable = idTable + count * 8
	dataStart = strTable + count * 8
	offsets = []
	data = b""
	for text in ids:
		offsets.append((len(text), dataStart + len(data)))
		data += text + b"\0"
	for text in strs:
		offsets.append((len(text), dataStart + len(data)))
		data += text + b"\0"
	header = struct.pack("<7I", 0x950412DE, 0, count, idTable, strTable, 0, dataStart)
	return header + b"".join(struct.pack("<2I", length, offset) for length, offset in offsets) + data


def compilePo(poPath):
	"""Return (.mo bytes, catalog) for a .po file."""
	catalog = readPo(poPath)
	return moBytes(catalog), catalog


def _quote(text):
	escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t")
	if "\n" not in escaped:
		return f'"{escaped}"'
	parts = escaped.split("\n")
	pieces = [part + "\\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
	return '""\n' + "\n".join(f'"{piece}"' for piece in pieces)


def _translatorComment(lines, lineNumber):
	"""The "# Translators:" comment just above a line, if any (lineNumber is 1-based)."""
	comment = []
	index = lineNumber - 2
	while index >= 0:
		stripped = lines[index].strip()
		if stripped.startswith("#"):
			comment.insert(0, stripped.lstrip("#").strip())
			if stripped.lstrip("#").strip().startswith("Translators:"):
				return " ".join(comment)
			index -= 1
		elif stripped.endswith(("(", ",")) or not stripped:
			# Skip the start of a multi-line call, e.g. "wx.CheckBox(" above the comment's text.
			index -= 1
			if comment:
				break
		else:
			break
	return ""


def makePot(sourcePath, relativePath, potPath, project):
	"""Collect every _("...") text from sourcePath into a .pot template."""
	with open(sourcePath, encoding="utf-8") as f:
		source = f.read()
	lines = source.splitlines()
	found = {}
	for node in ast.walk(ast.parse(source)):
		if (
			isinstance(node, ast.Call)
			and isinstance(node.func, ast.Name)
			and node.func.id == "_"
			and node.args
			and isinstance(node.args[0], ast.Constant)
			and isinstance(node.args[0].value, str)
		):
			text = node.args[0].value
			entry = found.setdefault(text, {"lines": [], "comment": ""})
			entry["lines"].append(node.lineno)
			entry["comment"] = entry["comment"] or _translatorComment(lines, node.lineno)
	now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M+0000")
	out = [
		'msgid ""',
		'msgstr ""',
		f'"Project-Id-Version: {project}\\n"',
		f'"POT-Creation-Date: {now}\\n"',
		'"MIME-Version: 1.0\\n"',
		'"Content-Type: text/plain; charset=UTF-8\\n"',
		'"Content-Transfer-Encoding: 8bit\\n"',
		"",
	]
	for text, entry in sorted(found.items(), key=lambda item: min(item[1]["lines"])):
		if entry["comment"]:
			out.append(f"#. {entry['comment']}")
		out.append("#: " + " ".join(f"{relativePath}:{line}" for line in sorted(entry["lines"])))
		out.append(f"msgid {_quote(text)}")
		out.append('msgstr ""')
		out.append("")
	with open(potPath, "w", encoding="utf-8", newline="\n") as f:
		f.write("\n".join(out))
	return len(found)
