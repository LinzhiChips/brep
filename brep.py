#!/usr/bin/python3
#
# brep.py - Browse miner reports
#
# Copyright (C) 2021 Linzhi Ltd.
#
# This work is licensed under the terms of the MIT License.
# A copy of the license can be found in the file COPYING.txt
#

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.0')

from gi.repository import Gtk, Gdk, GLib
from gi.repository import WebKit2
import sys, os, argparse, re
import zipfile


# @@@ very site-specific
DEFAULT_URL = "file:///home/lavasnow/fw/overlay/www/index.html"

report_sel = None
file_sel = None
file_text = None
file_browser = None
busy = False
url = DEFAULT_URL


class Button(Gtk.EventBox):
	def set_bg(self, color):
		self.override_background_color(Gtk.StateFlags.NORMAL,
		    color)

	def select(self):
		global busy

		busy = True
		self.action(*self.data)
		busy = False
		self.set_bg(self.bg_color_selected)

	def deselect(self):
		self.set_bg(self.bg_color_normal)

	def add_arg(self, arg):
		self.data.append(arg)

	def __init__(self, label, action, *data):
		super(Button, self).__init__()
		self.action = action
		self.data = list(data)
		self.label = Gtk.Label() 
		self.label.set_label(label)
#		style = "weight='bold'"
#		self.label.set_markup("<span " + style + ">" + label +
#		    "</span>")
		hbox = Gtk.HBox()
		hbox.pack_start(self.label, False, True, 5)
		self.add(hbox)
		self.bg_color_selected = Gdk.RGBA(1.0, 0.9, 0)
		self.bg_color_normal = Gdk.RGBA(0.8, 0.8, 0.8)
		self.deselect()


class ButtonGroup(Gtk.ScrolledWindow):
	def select(self, button, event = None):
		if busy:
			return
		if self.selected is not None:
			self.selected.deselect()
		button.select()
		self.selected = button

	def button(self, label, action, *data, select = False):
		button = Button(label, action, *data)
		self.vbox.pack_start(button, False, True, 0)
		if self.selected == None or select:
			self.selected = button
			button.select()
		button.connect("button-press-event", self.select)
		return button

	def reset(self):
		for child in self.vbox.get_children():
			self.vbox.remove(child)

	def __init__(self):
		super(ButtonGroup, self).__init__()
		self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
		self.vbox = Gtk.VBox()
		self.vbox.set_spacing(2)
		self.add(self.vbox)
		self.selected = None


class Browser:
	def load_changed(self, web, event):
		self.waiting = event != WebKit2.LoadEvent.FINISHED

	def console_message(self, web, msg, line, source, user_data):
		print(msg)

	def sync(self):
		while Gtk.events_pending() or self.waiting:
			Gtk.main_iteration()

	def js_complete(self, webview, result, user_data = None):
		if result is not None:
			self.web.run_javascript_finish(result)
		self.waiting = False
		self.sync()

	def js(self, script):
		self.sync()
		self.waiting = True
		self.web.run_javascript(script, None, self.js_complete, None)

	def mqtt(self, topic, payload):
		# https://stackoverflow.com/a/18935765/8179289
		escaped = payload.translate(str.maketrans({
			"\n":	r"\\n",
			'"':	r'\"',
		}))
		self.js('dispatch_message("' + topic + '", "' + escaped + '")')

	def load(self, url = DEFAULT_URL):
		self.url = url
		self.web.load_uri(url)
		self.waiting = True

	def reload(self):
		self.load(self.url)
		
	def widget(self):
		return self.web

	def __init__(self, url = DEFAULT_URL):
		self.web = WebKit2.WebView()
		self.url = url
		self.load(url)
		self.web.connect("load-changed", self.load_changed)
		settings = self.web.get_settings()
		settings.set_enable_write_console_messages_to_stdout(True)


class TextWindow(Gtk.ScrolledWindow):
	def set(self, text):
		buffer = self.text.get_buffer()
		buffer.set_text(text)
		
	def __init__(self):
		super(TextWindow, self).__init__()
		self.set_policy(Gtk.PolicyType.AUTOMATIC,
		    Gtk.PolicyType.AUTOMATIC)
		self.text = Gtk.TextView()
		self.add(self.text)


def show_file(text):
	file_browser.widget().hide()
	file_text.set(text)
	file_text.show()


def process_messages(text):
	file_browser.reload()
	msg = []
	last = None
	for line in text.split("\n"):
		m = re.match("^(/\S+) \d+ (\d+) \S+ (.*)$", line)
		if m:
			msg.append({
				"seq":		int(m.group(2)),
				"topic":	m.group(1),
				"payload":	m.group(3),
			})
			last = msg[-1]
		else:
			last["payload"] += "\n" + line
	if last is not None:
		last["payload"] = last["payload"][:-1]
	msg.sort(key = lambda x: x["seq"])
	for m in msg:
		file_browser.mqtt(m["topic"], m["payload"])
		file_browser.sync()


def show_browser(text = None):
	if text is not None:
		file_text.hide()
		file_browser.widget().show()
		process_messages(text)


def show_report(report):
	last_file = None
	if file_sel.selected is not None:
		last_file = file_sel.selected.label.get_label()
	with zipfile.ZipFile(report) as zip:
		file_sel.reset()
		file_text.set("")
		browser_button = file_sel.button("Browser", show_browser,
		    select = last_file == "Browser")
		for name in zip.namelist():
			with zip.open(name) as file:
				text = file.read().decode()
				file_sel.button(name, show_file, text,
				    select = name == last_file)
				if name == "messages.txt":
					browser_button.add_arg(text)
		file_sel.show_all()
		file_text.show_all()
		if browser_button == file_sel.selected:
			file_sel.select(browser_button)

	
Gtk.init(sys.argv)

parser = argparse.ArgumentParser()
parser.add_argument("--url", "-u", help = "URL of UI code")
parser.add_argument("args", nargs = "*", default = [], help = "report files")
args = parser.parse_args()

if args.url is not None:
	url = args.url

main = Gtk.Window()
main.set_default_size(1000, 800)
main.connect("destroy", Gtk.main_quit)

hbox = Gtk.HBox()
hbox.set_spacing(2)
report_sel = ButtonGroup()
file_sel = ButtonGroup()
file_text = TextWindow()
file_browser = Browser(url + "?sandbox")

for report in args.args:
	name = os.path.basename(report)
	name = os.path.splitext(name)[0]
	report_sel.button(name, show_report, report) 

hbox.pack_start(report_sel, False, True, 0)
hbox.pack_start(file_sel, False, True, 0)
hbox.pack_start(file_text, True, True, 0)
hbox.pack_start(file_browser.widget(), True, True, 0)
main.add(hbox)

main.show_all()
file_text.hide()

Gtk.main()
