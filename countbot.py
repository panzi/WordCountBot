#!/usr/bin/env python3

import re
import sys
import irc.bot
from time import gmtime
from calendar import timegm
from collections import defaultdict, OrderedDict
from unicodedata import normalize as unicode_normalize

WORDS = re.compile(r"(?:-\w|\w)[-\w]*")
TIME = re.compile(r"\s*(\d+)\s*([a-z]+)?\s*")

MAX_COUNTS = 10
EXIT_EXCS = SystemExit, KeyboardInterrupt
ROW_TYPES = tuple, list

def normalize(word):
	return unicode_normalize('NFC', word).lower()

def normalize_channel(channel):
	channel = channel.lower()
	if not channel.startswith('#'):
		channel = '#'+channel
	return channel

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

class ChannelConfig:
	__slots__ = 'period',

	def __init__(self, period):
		self.period = period
		# maybe more in the future

	def dump(self):
		return {
			'period': self.period
		}

class CounterBot(irc.bot.SingleServerIRCBot):
	__slots__ = 'home_channel', 'period', 'gcinterval', 'admins', 'ignored_users', 'counts_per_channel', 'join_channels', 'channel_configs'

	def __init__(self, home_channel, default_period, gcinterval, admins, ignored_users, nickname, channels, password=None, server='irc.twitch.tv', port=6667):
		irc.bot.SingleServerIRCBot.__init__(self, [(server, port, password)], nickname, nickname)
		self.home_channel = normalize_channel(home_channel) if home_channel else None
		self.default_period = default_period
		self.gcinterval = gcinterval
		self.admins = set(admin.lower() for admin in admins)
		self.ignored_users = set(user.lower() for user in ignored_users)
		self.counts_per_channel = defaultdict(list)
		self.channel_configs = defaultdict(lambda: ChannelConfig(self.default_period))
		self.set_join_channels(channels)
		self.connection.execute_delayed(self.gcinterval, self.run_gc)

	def set_join_channels(self, channels):
		channels = OrderedDict((normalize_channel(channel), True) for channel in channels)
		if self.home_channel in channels:
			del channels[self.home_channel]
		self.join_channels = list(channels)

	def run_gc(self):
		timestamp = timegm(gmtime())
		rowcount = 0
		for channel, counts in self.counts_per_channel.items():
			config = self.channel_configs[channel]
			periodts = timestamp - config.period
			index = 0
			for index, (user, word, timestamp) in enumerate(counts):
				if timestamp >= periodts:
					break

			if index > 0:
				del counts[:index]
				rowcount += index

		print('gc: Deleted %d rows.' % rowcount if rowcount != 1 else 'gc: Deleted 1 row.')
		self.connection.execute_delayed(self.gcinterval, self.run_gc)

	def on_welcome(self, connection, event):
		if self.home_channel is not None:
			connection.join(self.home_channel)
		for channel in self.join_channels:
			connection.join(channel)
		connection.cap('REQ', 'twitch.tv/membership')

	def on_join(self, connection, event):
		self.connection.privmsg(self.home_channel or event.target, "Joined to %s." % event.target)

	def on_part(self, connection, event):
		channel = event.target

		if channel in self.counts_per_channel:
			del self.counts_per_channel[channel]

		if channel in self.channel_configs:
			del self.channel_configs[channel]

		if self.home_channel is not None:
			self.connection.privmsg(self.home_channel, "Parted from %s." % channel)

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

#		print('PUBMSG', channel, sender, message)

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

					print('Error: channel=%s, user=@%s, command=!%s: %s' %
						(channel, sender, command, exc), file=sys.stderr)

					self.connection.privmsg(self.home_channel,
						'Error processing command !%s in channel %s performed by %s: %s' %
						(command, channel, sender, exc))

		else:
			timestamp = timegm(gmtime())
			words = WORDS.findall(message)
			counts = self.counts_per_channel[channel]
			for word in words:
				counts.append((sender, normalize(word), timestamp))

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
			config = self.channel_configs[event.target]
			if not time:
				self.answer(event, "@%s: count period = %s" % (sender, format_time(config.period)))
			else:
				time = ' '.join(time)
				try:
					seconds = parse_time(time)
				except ValueError as ex:
					self.answer(event, "@%s: Illegal count period: %s" % (sender, time))
				else:
					config.period = seconds
					self.answer(event, "@%s: changed count period to %s" % (sender, format_time(config.period)))
		else:
			self.answer(event, "@%s: You don't have permissions to do that." % sender)

	def cmd_count(self, event, *words):
		"""
			Count given words or if none given all words.
			Every word is only counted once per user.
		"""
		timestamp = timegm(gmtime())
		channel = event.target
		periodts = timestamp - self.channel_configs[channel].period
		channel_counts = self.counts_per_channel[channel]
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

	def cmd_countint(self, event):
		"""
			Count integer numbers.
			Every number is only counted once per user.
		"""
		timestamp = timegm(gmtime())
		channel = event.target
		periodts = timestamp - self.channel_configs[channel].period
		channel_counts = self.counts_per_channel[channel]
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
				if num not in user_words:
					word_counts[num] += 1
					user_words.add(num)

		self.report_counts(event, word_counts)

	def cmd_count1(self, event):
		"""
			Count all one-letter words.
			Every word is only counted once per user.
		"""
		timestamp = timegm(gmtime())
		channel = event.target
		periodts = timestamp - self.channel_configs[channel].period
		channel_counts = self.counts_per_channel[channel]
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
			rowcount = len(self.counts_per_channel[channel])
			if rowcount > 0:
				self.counts_per_channel[channel] = []
			self.answer(event, 'Deleted %d rows.' % rowcount if rowcount != 1 else 'Deleted 1 row.')
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
				channel_commands.append('!'+name[4:])

			elif name.startswith('home_cmd_'):
				home_commands.append('!'+name[9:])

		channel_commands.sort()
		home_commands.sort()
		self.answer(event, '@%s: Commands: %s' % (sender, ', '.join(channel_commands)))
		if self.home_channel is not None:
			self.answer(event, '@%s: %s-only commands: %s' % (sender, self.home_channel, ', '.join(home_commands)))

	def home_cmd_help(self, event, command=None):
		"""
			Show help to given command.
		"""
		sender = event.source.nick
		if command is None:
			self.answer(event, "@%s: type !commands for a list of commands or !help <command> for help to !command" % sender)
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
			self.connection.join(channel)
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
					self.answer(event, "@%s: gcinterval changed to %s" % (sender, format_time(self.gcinterval)))
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
				self.connection.part(channel)
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
		if word_counts:
			counts = list(word_counts.items())
			counts.sort(key=lambda item: (item[1], item[0]), reverse=True)
			if not self.is_allowed(event.source.nick, event.target) and len(counts) > MAX_COUNTS:
				counts = counts[:MAX_COUNTS]
			self.answer(event, ', '.join('%s: %d' % item for item in counts))
		else:
			self.answer(event, 'No words counted.')

	def answer(self, event, message):
		channel = event.target
		nick = self.connection.get_nickname()
		if event.source.nick != nick or self.channels[channel].is_oper(nick):
			self._answer(channel, message)
		else:
			self.connection.execute_delayed(1, lambda: self._answer(channel, message))

	def _answer(self, channel, message):
		print('%s %s: %s' % (channel, self.connection.get_nickname(), message))
		self.connection.privmsg(channel, message)

	def dump(self):
		return {
			'version': '1.0',
			'channels': [str(channel) for channel in self.channels],
			'default_period': self.default_period,
			'gcinterval': self.gcinterval,
			'channel_configs': dict(
				(channel, self.channel_configs[channel].dump())
				for channel in self.channel_configs),
			'counts_per_channel': dict(
				(channel, [list(row) for row in self.counts_per_channel[channel]])
				for channel in self.counts_per_channel)
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

		if 'gcinterval' in state:
			gcinterval = int(state['gcinterval'])
			if gcinterval <= 0:
				raise ValueError('illegal gcinterval: %r' % gcinterval)
			self.gcinterval = gcinterval

		if 'counts_per_channel' in state:
			counts_per_channel = defaultdict(list)
			for channel, rows in state['counts_per_channel'].items():
				counts_per_channel[channel] = channel_counts = []
				for row in rows:
					if type(row) not in ROW_TYPES or len(row) != 3:
						raise ValueError('illegal counts-row for channel %s: %r' % (channel, row))

					user, word, timestamp = row

					if type(user) is not str or type(word) is not str or type(timestamp) is not int:
						raise ValueError('illegal counts-row for channel %s: %r' % (channel, row))

					channel_counts.append((user, word, timestamp))

			self.counts_per_channel = counts_per_channel

		if 'channel_configs' in state:
			channel_configs = defaultdict(lambda: ChannelConfig(self.default_period))
			for channel, config in state['channel_configs'].items():
				channel_configs[channel] = ChannelConfig(**config)
			self.channel_configs = channel_configs

		if 'channels' in state:
			self.set_join_channels(state['channels'])

def main(args):
	import yaml
	import argparse

	parser = argparse.ArgumentParser()
	parser.add_argument('-c', '--config', default='config.yaml')
	opts = parser.parse_args(args)

	with open(opts.config,'rb') as fp:
		config = yaml.load(fp)

	server, port = config.get('host','irc.twitch.tv:6667').split(':', 1)
	port = int(port)

	statefile = config.get('state')

	bot = CounterBot(
		config.get('home_channel'),
		int(config.get('default_period', 60 * 5)),
		int(config.get('gcinterval', 60 * 10)),
		config.get('admins') or [],
		config.get('ignore') or [],
		config['nickname'],
		config.get('channels') or [],
		config.get('password'),
		server,
		port)

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
			state = yaml.dump(state)

			with open(statefile, 'w') as fp:
				fp.write(state)

if __name__ == '__main__':
	import sys

	try:
		main(sys.argv[1:])
	except KeyboardInterrupt:
		print()
