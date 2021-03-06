#!/usr/bin/env python3

import os
import re
import sys
import irc.bot
import socket
import traceback
import signal
from irc.client import ServerNotConnectedError
from time import gmtime
from calendar import timegm
from collections import defaultdict, OrderedDict
from unicodedata import normalize as unicode_normalize

WORDS = re.compile(r"(?:-\w|\w)[-\w]*")
TIME = re.compile(r"\s*(\d+)\s*([a-z]+)?\s*")

EXIT_EXCS = SystemExit, KeyboardInterrupt
ROW_TYPES = tuple, list

def normalize(word):
	return unicode_normalize('NFC', word).lower()

def normalize_channel(channel):
	channel = channel.lower()
	if not channel.startswith('#'):
		channel = '#'+channel
	return channel

def parse_int_bound(value):
	value = value.lower()
	if value == 'none' or value == 'null' or value == 'unbounded' or value == 'unlimited':
		return None
	else:
		return int(value, 10)

def parse_time(time):
	if not time:
		raise ValueError(time)

	index = 0
	seconds = 0
	while index < len(time):
		match = TIME.match(time, index)
		if not match:
			raise ValueError(time)

		value = int(match.group(1), 10)
		unit = match.group(2)

		if unit:
			unit = unit.lower()
		else:
			unit = 'seconds'

		if unit == 's' or unit == 'sec' or unit == 'secs' or unit == 'seconds' or unit == 'second':
			seconds += value

		elif unit == 'm' or unit == 'min' or unit == 'mins' or unit == 'minutes' or unit == 'minute':
			seconds += value * 60

		elif unit == 'h' or unit == 'hours' or unit == 'hour':
			seconds += value * 3600

		else:
			raise ValueError(time)

		index = match.end()

	return seconds

def format_time(seconds):
	if seconds == 0:
		return '0sec'

	negative = seconds < 0
	if negative:
		seconds = -seconds
	minutes  = seconds // 60
	seconds -= minutes * 60
	hours    = minutes // 60
	minutes -= hours * 60

	buf = []
	if hours:
		buf.append('%dh' % hours)

	if minutes:
		buf.append('%dmin' % minutes)

	if seconds:
		buf.append('%dsec' % seconds)

	time = ' '.join(buf)

	if negative:
		time = '-'+time

	return time

class ChannelData:
	__slots__ = 'period', 'counts', 'minint', 'maxint', 'result_limit'

	def __init__(self, period, minint=None, maxint=None, result_limit=None, counts=None):
		self.period = period
		self.counts = counts if counts is not None else []
		self.minint = minint
		self.maxint = maxint
		self.result_limit = result_limit
		# maybe more in the future

	def dump(self):
		return {
			'period': self.period,
			'counts': [list(row) for row in self.counts],
			'minint': self.minint,
			'maxint': self.maxint,
			'result_limit': self.result_limit
		}

	def find_first_non_gc_count(self, periodts):
		for index, (user, word, timestamp) in enumerate(self.counts):
			if timestamp >= periodts:
				return index
		return len(self.counts)

class CounterBot(irc.bot.SingleServerIRCBot):
	__slots__ = ('home_channel', 'period', 'gcinterval', 'admins', 'ignored_users',
	             'channel_data', 'join_channels', 'max_message_length',
	             'default_minint', 'default_maxint', 'default_result_limit')

	def __init__(self, home_channel, default_period, gcinterval, max_message_length,
		         default_minint, default_maxint, default_result_limit, admins,
		         ignored_users, nickname, channels, password=None,
		         server='irc.twitch.tv', port=6667):
		irc.bot.SingleServerIRCBot.__init__(self, [(server, port, password)], nickname, nickname)
		self.home_channel = normalize_channel(home_channel) if home_channel else None
		self.default_period = default_period
		self.gcinterval = gcinterval
		self.max_message_length = max_message_length
		self.default_minint = default_minint
		self.default_maxint = default_maxint
		self.default_result_limit = default_result_limit
		self.admins = set(admin.lower() for admin in admins)
		self.ignored_users = set(user.lower() for user in ignored_users)
		self.channel_data = defaultdict(self.make_channel_data)
		self.joined_channels = set()
		self.set_join_channels(channels)
		self.gc_scheduled = False
		self.schedule_gc_if_needed()

	def make_channel_data(self):
		return ChannelData(self.default_period, self.default_minint, self.default_maxint, self.default_result_limit)

	def schedule_gc_if_needed(self):
		if not self.gc_scheduled:
			needed = False
			for data in self.channel_data.values():
				if data.counts:
					needed = True
					break
			self.schedule_gc()

	def schedule_gc(self):
		self.connection.execute_delayed(self.gcinterval, self.run_gc)
		self.gc_scheduled = True

	def set_join_channels(self, channels):
		channels = OrderedDict((normalize_channel(channel), True) for channel in channels)
		if self.home_channel in channels:
			del channels[self.home_channel]
		self.join_channels = list(channels)

	def run_gc(self):
		self.gc_scheduled = False
		timestamp = timegm(gmtime())
		delchannels = []
		for channel in self.channel_data:
			if channel not in self.joined_channels:
				delchannels.append(channel)

		rowcount = 0
		for channel in delchannels:
			rowcount += len(self.channel_data[channel].counts)
			del self.channel_data[channel]

		needed = False
		for data in self.channel_data.values():
			periodts = timestamp - data.period
			index = data.find_first_non_gc_count(periodts)

			if index > 0:
				del data.counts[:index]
				rowcount += index

			if data.counts:
				needed = True

		print('gc: Deleted %d rows.' % rowcount if rowcount != 1 else 'gc: Deleted 1 row.')

		if needed:
			self.schedule_gc()

	def on_welcome(self, connection, event):
		if self.home_channel is not None:
			self.do_join(self.home_channel)

		for channel in self.join_channels:
			self.do_join(channel)

		connection.cap('REQ', 'twitch.tv/membership')

		if self.home_channel is not None:
			self.chunked_privmsg(self.home_channel, "%s booted!" % self.connection.get_nickname())

	def do_join(self, channel):
		self.connection.join(channel)
		self.joined_channels.add(channel)
		self.chunked_privmsg(self.home_channel or channel, "Joined to %s." % channel)

	def do_part(self, channel):
		self.connection.part(channel)

		# delete data immediately, don't trust what the IRC server says
		if channel in self.channel_data:
			del self.channel_data[channel]

		if channel in self.joined_channels:
			self.joined_channels.remove(channel)

		if self.home_channel is not None:
			self.chunked_privmsg(self.home_channel, "Parted from %s." % channel)

	def on_nicknameinuse(self, connection, event):
		print('Error: nickname in use', file=sys.stderr)

	def on_error(self, connection, event):
		print('Error: '+' '.join(event.arguments), file=sys.stderr)

	def on_pubmsg(self, connection, event):
		sender = event.source.nick

		if sender in self.ignored_users:
			return

		channel = event.target
		message = event.arguments[0]

		if message.startswith("!"):
			command, *args = message.rstrip().split()
			command = command[1:]
			if channel == self.home_channel:
				method = 'home_cmd_'+command
				if not hasattr(self, method):
					method = 'cmd_'+command
			else:
				method = 'cmd_'+command

			if hasattr(self, method):
				try:
					cmd = getattr(self, method)

					min_argc = max_argc = cmd.__code__.co_argcount - 2
					if cmd.__defaults__:
						min_argc -= len(cmd.__defaults__)
					if cmd.__code__.co_flags & 0x4:
						max_argc = None

					argc = len(args)
					if max_argc is not None and argc > max_argc:
						self.answer(event,
							'@%s: Too many arguments. !%s takes no more than %d argument(s).' %
							(sender, command, max_argc))

					elif argc < min_argc:
						self.answer(event,
							'@%s: Not enough arguments. !%s takes at least %d argument(s).' %
							(sender, command, min_argc))

					else:
						cmd(event, *args)

				except Exception as exc:
					if isinstance(exc, EXIT_EXCS):
						raise

					traceback.print_exc()

					self.chunked_privmsg(self.home_channel,
						'Error processing command !%s in channel %s performed by %s: %s' %
						(command, channel, sender, exc))

		else:
			timestamp = timegm(gmtime())
			words = WORDS.findall(message)
			if words:
				counts = self.channel_data[channel].counts
				for word in words:
					counts.append((sender, normalize(word), timestamp))

				if not self.gc_scheduled:
					self.schedule_gc()

	def is_allowed(self, user, channel):
		if user in self.admins:
			return True

		if channel is None:
			return False

		chan = self.channels[channel]
		return chan.is_oper(user) or chan.is_admin(user) or chan.is_owner(user)

	def cmd_countperiod(self, event, *time):
		"""
			Get or set the period in which words are counted for this channel.
			The time can be given in hours, seconds or minutes, e.g.: 1h, 5min, 300sec, or 5m 30s
		"""
		sender = event.source.nick
		channel = event.target
		if self.is_allowed(sender, channel):
			data = self.channel_data[event.target]
			if not time:
				self.answer(event, "@%s: count period = %s" % (sender, format_time(data.period)))
			else:
				time = ' '.join(time)
				try:
					seconds = parse_time(time)
				except ValueError as ex:
					self.answer(event, "@%s: Illegal count period: %s" % (sender, time))
				else:
					data.period = seconds
					self.answer(event, "@%s: Changed count period to %s" % (sender, format_time(data.period)))
		else:
			self.answer(event, "@%s: You don't have permissions to do that." % sender)

	def cmd_count(self, event, *words):
		"""
			Count given words or if none given all words.
			Every word is only counted once per user.
		"""
		timestamp = timegm(gmtime())
		channel = event.target
		data = self.channel_data[channel]
		periodts = timestamp - data.period
		channel_counts = data.counts
		all_user_words = defaultdict(set)

		if words:
			word_counts = dict((normalize(word), 0) for word in words)
			for user, word, timestamp in reversed(channel_counts):
				if timestamp < periodts:
					break

				if word in word_counts:
					user_words = all_user_words[user]
					if word not in user_words:
						word_counts[word] += 1
						user_words.add(word)

			# de-normalize counted words
			word_counts = dict((word, word_counts[normalize(word)]) for word in words)
		else:
			word_counts = defaultdict(int)
			for user, word, timestamp in reversed(channel_counts):
				if timestamp < periodts:
					break

				user_words = all_user_words[user]
				if word not in user_words:
					word_counts[word] += 1
					user_words.add(word)

		self.report_counts(event, word_counts)

	def cmd_countint(self, event, minint=None, maxint=None):
		"""
			Count integer numbers.
			Every number is only counted once per user.
		"""
		timestamp = timegm(gmtime())
		channel = event.target
		data = self.channel_data[channel]
		minint = parse_int_bound(minint) if minint is not None else data.minint
		maxint = parse_int_bound(maxint) if maxint is not None else data.maxint
		periodts = timestamp - data.period
		channel_counts = data.counts
		all_user_words = defaultdict(set)

		word_counts = defaultdict(int)
		for user, word, timestamp in reversed(channel_counts):
			if timestamp < periodts:
				break

			try:
				num = int(word, 10)
			except ValueError:
				pass
			else:
				user_words = all_user_words[user]
				if minint is not None and num < minint:
					pass
				elif maxint is not None and num > maxint:
					pass
				elif num not in user_words:
					word_counts[num] += 1
					user_words.add(num)

		self.report_counts(event, word_counts)

	cmd_countinit = cmd_countint
	cmd_intcount  = cmd_countint
	cmd_initcount = cmd_countint

	def cmd_count1(self, event):
		"""
			Count all one-letter words.
			Every word is only counted once per user.
		"""
		timestamp = timegm(gmtime())
		channel = event.target
		data = self.channel_data[channel]
		periodts = timestamp - data.period
		channel_counts = data.counts
		all_user_words = defaultdict(set)

		word_counts = defaultdict(int)
		for user, word, timestamp in reversed(channel_counts):
			if timestamp < periodts:
				break

			if len(word) == 1:
				user_words = all_user_words[user]
				if not word in user_words:
					word_counts[word] += 1
					user_words.add(word)

		self.report_counts(event, word_counts)

	def cmd_clearcount(self, event):
		"""
			Clear all counts of this channel. Only allowed for operators etc.
		"""
		sender = event.source.nick
		channel = event.target
		if self.is_allowed(sender, channel):
			data = self.channel_data[channel]
			rowcount = len(data.counts)
			del data.counts[:]
			self.answer(event, 'Deleted %d rows.' % rowcount if rowcount != 1 else 'Deleted 1 row.')
		else:
			self.answer(event, "@%s: You don't have permissions to do that." % sender)

	def cmd_countminint(self, event, value=None):
		"""
			Get or set channel default minimum integer for !countint.
		"""
		sender = event.source.nick
		channel = event.target
		data = self.channel_data[channel]
		if value is None:
			self.answer(event, "@%s: !countint minimum is %s." % (sender, data.minint if data.minint is not None else 'unbounded'))
		elif self.is_allowed(sender, channel):
			data.minint = parse_int_bound(value)
			self.answer(event, "@%s: Changed !countint minimum to %s" % (sender, data.minint if data.minint is not None else 'unbounded'))
		else:
			self.answer(event, "@%s: You don't have permissions to do that." % sender)

	cmd_countintmin = cmd_countminint

	def cmd_countmaxint(self, event, value=None):
		"""
			Get or set channel default maximum integer for !countint.
		"""
		sender = event.source.nick
		channel = event.target
		data = self.channel_data[channel]
		if value is None:
			self.answer(event, "@%s: !countint maximum is %s." % (sender, data.maxint if data.maxint is not None else 'unbounded'))
		elif self.is_allowed(sender, channel):
			data.maxint = parse_int_bound(value)
			self.answer(event, "@%s: Changed !countint maximum to %s" % (sender, data.maxint if data.maxint is not None else 'unbounded'))
		else:
			self.answer(event, "@%s: You don't have permissions to do that." % sender)

	cmd_countintmax = cmd_countmaxint

	def cmd_count_result_limit(self, event, value=None):
		"""
			Get or set channel default result list entry limit.
		"""
		sender = event.source.nick
		channel = event.target
		data = self.channel_data[channel]
		if value is None:
			self.answer(event, "@%s: Count result list entry limit is %s." % (sender, data.result_limit if data.result_limit is not None else 'unlimited'))
		elif self.is_allowed(sender, channel):
			data.result_limit = parse_int_bound(value)
		else:
			self.answer(event, "@%s: You don't have permissions to do that." % sender)

	def cmd_countleave(self, event):
		"""
			Make WordCountBot leave this channel. Only allowed for operators of the given channel.
		"""
		self.home_cmd_leave(event, event.target)

	def home_cmd_commands(self, event):
		"""
			Show the list of commands.
		"""
		channel_commands = []
		home_commands = []
		sender = event.source.nick
		for name in dir(self):
			if name.startswith('cmd_'):
				if getattr(self, name).__name__ == name:
					# otherwise its an alias
					channel_commands.append('!'+name[4:])

			elif name.startswith('home_cmd_'):
				if getattr(self, name).__name__ == name:
					# otherwise its an alias
					home_commands.append('!'+name[9:])

		channel_commands.sort()
		home_commands.sort()
		message = '@%s: Commands: %s' % (sender, ', '.join(channel_commands))
		if self.home_channel is not None:
			message += ' %s-only commands: %s' % (self.home_channel, ', '.join(home_commands))
		self.answer(event, message)

	def home_cmd_help(self, event, command=None):
		"""
			Show help to given command.
		"""
		sender = event.source.nick
		if command is None:
			self.answer(event,
				"@%s: type !commands for a list of commands or !help <command> "
				"for help to !command. For more see: https://github.com/panzi/WordCountBot" % sender)
		else:
			channel = event.target
			if command.startswith('!'):
				command = command[1:]

			if channel == self.home_channel:
				method = 'home_cmd_'+command
				if not hasattr(self, method):
					method = 'cmd_'+command
			else:
				method = 'cmd_'+command

			if hasattr(self, method):
				cmd = getattr(self, method)
				doc = cmd.__doc__
				usage = ['Usage: !', command]

				min_argc = argc = cmd.__code__.co_argcount
				if cmd.__defaults__:
					min_argc -= len(cmd.__defaults__)

				varnames = cmd.__code__.co_varnames
				for i in range(2, min_argc):
					usage.append(' ')
					usage.append(varnames[i])

				for i in range(min_argc, argc):
					usage.append(' [')
					usage.append(varnames[i])
					usage.append(']')

				if cmd.__code__.co_flags & 0x4:
					usage.append(' [')
					usage.append(varnames[argc])
					usage.append('...]')

				self.answer(event, ''.join(usage))
				if doc:
					doc = doc.lstrip('\n').rstrip().split('\n')
					first = doc[0]
					indent = first[:len(first) - len(first.lstrip())]
					indent_len = len(indent)
					for line in doc:
						if line.startswith(indent):
							line = line[indent_len:]
						self.answer(event, line)
			else:
				self.answer(event, "@%s: No such command !%s" % (sender, command))

	def home_cmd_join(self, event, channel):
		"""
			Make WordCountBot join the given channel. Only allowed for operators of the given channel.
		"""
		channel = normalize_channel(channel)
		sender = event.source.nick
		if self.is_allowed(sender, channel):
			self.do_join(channel)
		else:
			self.answer(event, "@%s: You don't have permissions to do that." % sender)

	def home_cmd_gcinterval(self, event, *value):
		"""
			Get or set gcinterval. WordCountBot-admin only.
		"""
		sender = event.source.nick
		if self.is_allowed(sender, self.home_channel):
			if not value:
				self.answer(event, "@%s: gcinterval = %s" % (sender, format_time(self.gcinterval)))
			else:
				value = ' '.join(value)
				try:
					seconds = parse_time(value)
					if seconds <= 0:
						raise ValueError(value)
				except ValueError as ex:
					self.answer(event, "@%s: Illegal gcinterval: %s" % (sender, value))
				else:
					self.gcinterval = seconds
					self.answer(event, "@%s: Changed gcinterval to %s" % (sender, format_time(self.gcinterval)))
		else:
			self.answer(event, "@%s: You don't have permissions to do that." % sender)

	def home_cmd_leave(self, event, channel):
		"""
			Make WordCountBot leave the given channel. Only allowed for operators of the given channel.
		"""
		channel = normalize_channel(channel)
		sender = event.source.nick
		if self.is_allowed(sender, channel):
			if channel == self.home_channel:
				self.answer(event, "@%s: Cannot leave home channel." % sender)
			else:
				self.do_part(channel)
		else:
			self.answer(event, "@%s: You don't have permissions to do that." % sender)

	def home_cmd_channels(self, event):
		"""
		List all channels joined by WordCountBot. WordCountBot-admin only.
		"""
		sender = event.source.nick
		if self.is_allowed(sender, self.home_channel):
			self.answer(event, 'Joined channels: ' + ', '.join(self.channels))
		else:
			self.answer(event, "@%s: You don't have permissions to do that." % sender)

	def report_counts(self, event, word_counts):
		data = self.channel_data[event.target]
		period = data.period
		if word_counts:
			result_limit = data.result_limit
			counts = list(word_counts.items())
			counts.sort(key=lambda item: (-item[1], item[0]))
			if result_limit is not None and len(counts) > result_limit:
				counts = counts[:result_limit]
			self.answer(event, 'Word-counts within the last %s: %s' % (
				format_time(period), ' — '.join('%s: %d' % item for item in counts)))
		else:
			self.answer(event, 'No words counted in the last %s.' % format_time(period))

	def answer(self, event, message):
		channel = event.target
		nick = self.connection.get_nickname()
		if event.source.nick != nick or self.channels[channel].is_oper(nick):
			self.chunked_privmsg(channel, message)
		else:
			self.connection.execute_delayed(1, lambda: self.chunked_privmsg(channel, message))

	def _send_raw(self, bytes):
		if self.connection.socket is None:
			raise ServerNotConnectedError("Not connected.")
		try:
			self.connection.socket.send(bytes)
		except socket.error:
			self.connection.disconnect("Connection reset by peer.")

	def chunked_privmsg(self, channel, message):
		print('%s: %s' % (channel, message))
		maxlen = self.max_message_length
		channel_utf8 = channel.encode('utf-8')
		if maxlen is not None:
			maxlen -= len(channel_utf8) + 11 # len("PRIVMSG "+...+" "+...+"\r\n")
			if maxlen <= 0:
				maxlen = 8
		message_utf8 = message.encode('utf-8')
		N = len(message_utf8)
		if maxlen and N > maxlen:
			index = 0
			while index < N:
				next_index = index + maxlen
				if next_index >= N:
					self._send_raw(b''.join((b'PRIVMSG ',channel_utf8,b' :',message_utf8[index:],b'\r\n')))
					break

				space_index = None
				for i in range(next_index, index - 1, -1):
					byte = message_utf8[i]
					if byte == 32 or byte == 9:
						space_index = i
						break

				if space_index is None:
					# at least don't cut in the middle of a multi-byte sequence
					while next_index > index:
						byte = message_utf8[next_index]
						if byte < 128 or byte >= 192:
							break
						next_index -= 1
					chunk = message_utf8[index:next_index]
				else:
					chunk = message_utf8[index:space_index].rstrip()
					next_index = space_index + 1

				self._send_raw(b''.join((b'PRIVMSG ',channel_utf8,b' :',chunk,b'\r\n')))
				index = next_index
		else:
			self._send_raw(b''.join((b'PRIVMSG ',channel_utf8,b' :',message_utf8,b'\r\n')))

	def dump(self):
		return {
			'version': '1.0',
			'channels': list(self.joined_channels),
			'default_period': self.default_period,
			'gcinterval': self.gcinterval,
			'channel_data': dict(
				(channel, self.channel_data[channel].dump())
				for channel in self.channel_data)
		}

	def load(self, state):
		version = state['version']
		if version != '1.0':
			raise ValueError('unsupported state version: %s' % version)

		if 'default_period' in state:
			default_period = int(state['default_period'])
			if default_period <= 0:
				raise ValueError('illegal default period: %r' % default_period)
			self.default_period = default_period
		else:
			default_period = self.default_period

		if 'gcinterval' in state:
			gcinterval = int(state['gcinterval'])
			if gcinterval <= 0:
				raise ValueError('illegal gcinterval: %r' % gcinterval)
			self.gcinterval = gcinterval

		if 'default_minint' in state:
			default_minint = state['default_minint']
			if default_minint is not None:
				default_minint = int(default_minint)
			self.default_minint = default_minint
		else:
			default_minint = self.default_minint

		if 'default_maxint' in state:
			default_maxint = state['default_maxint']
			if default_maxint is not None:
				default_maxint = int(default_maxint)
			self.default_maxint = default_maxint
		else:
			default_maxint = self.default_maxint

		if 'default_result_limit' in state:
			default_result_limit = state['default_result_limit']
			if default_result_limit is not None:
				default_result_limit = int(default_result_limit)
			if default_result_limit < 1:
				raise ValueError('illegal default_result_limit: %r' % default_result_limit)
			self.default_result_limit = default_result_limit
		else:
			default_result_limit = self.default_result_limit

		if 'channel_data' in state:
			channel_data = defaultdict(self.make_channel_data)
			for channel, data in state['channel_data'].items():
				period = data.get('period', default_period)
				minint = data.get('minint', default_minint)
				maxint = data.get('maxint', default_maxint)
				result_limit = data.get('result_limit', default_result_limit)

				rows = data.get('counts')
				channel_counts = []
				if rows:
					for row in rows:
						if type(row) not in ROW_TYPES or len(row) != 3:
							raise ValueError('illegal counts-row for channel %s: %r' % (channel, row))

						user, word, timestamp = row

						if type(user) is not str or type(word) is not str or type(timestamp) is not int:
							raise ValueError('illegal counts-row for channel %s: %r' % (channel, row))

						channel_counts.append((user, word, timestamp))

				channel_data[channel] = ChannelData(period, minint, maxint, result_limit, channel_counts)
			self.channel_data = channel_data

		if 'channels' in state:
			self.set_join_channels(state['channels'])

	def start(self):
		try:
			super(CounterBot, self).start()
		except InterruptedError:
			pass
		finally:
			if self.home_channel is not None:
				if self.connection.socket:
					self.chunked_privmsg(self.home_channel, '%s is shutting down.' % self.connection.get_nickname())

def main(args):
	import yaml
	import argparse

	parser = argparse.ArgumentParser()
	parser.add_argument('-c', '--config', default='config.yaml')
	parser.add_argument('--env-config', help='read configuration from environment', action='store_true', default=False)
	opts = parser.parse_args(args)

	if opts.env_config:
		config = {}
		for key in ('host', 'nickname', 'password', 'default_period',
		            'default_minint', 'default_maxint', 'default_result_limit',
		            'gcinterval', 'max_message_length', 'state', 'home_channel'):
			envkey = 'COUNTBOT_'+key.upper()
			value = os.getenv(envkey)
			if value:
				config[key] = value

		for key in ('channels', 'admins', 'ignore'):
			envkey = 'COUNTBOT_'+key.upper()
			value = os.getenv(envkey)
			if value:
				config[key] = value.split(',')
	else:
		with open(opts.config,'rb') as fp:
			config = yaml.load(fp)

	server, port = config.get('host','irc.twitch.tv:6667').split(':', 1)
	port = int(port)

	statefile = config.get('state')
	default_minint = config.get('default_minint')
	default_maxint = config.get('default_maxint')
	default_result_limit = config.get('default_result_limit')

	bot = CounterBot(
		config.get('home_channel'),
		int(config.get('default_period', 60 * 5)),
		int(config.get('gcinterval', 60 * 10)),
		int(config.get('max_message_length', 512)),
		int(default_minint) if default_minint is not None else None,
		int(default_maxint) if default_maxint is not None else None,
		int(default_result_limit) if default_result_limit is not None else None,
		config.get('admins') or [],
		config.get('ignore') or [],
		config['nickname'],
		config.get('channels') or [],
		config.get('password'),
		server,
		port)

	shutdown = lambda signum, frame: bot.disconnect()
	signal.signal(signal.SIGINT, shutdown)
	signal.signal(signal.SIGTERM, shutdown)

	config = parser = opts = None

	if statefile:
		try:
			with open(statefile, 'r') as fp:
				print('Loading state from %s...' % statefile)
				state = yaml.load(fp)
		except FileNotFoundError:
			pass
		else:
			bot.load(state)
			state = fp = None

	try:
		print('Starting bot...')
		bot.start()
	finally:
		if statefile:
			print('\nDumping state to %s...' % statefile)
			state = bot.dump()

			with open(statefile, 'w') as fp:
				yaml.dump(state, fp)

if __name__ == '__main__':
	import sys

	try:
		main(sys.argv[1:])
	except KeyboardInterrupt:
		print()
