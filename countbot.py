#!/usr/bin/env python3

import re
import irc.bot
import logging
from time import gmtime
from calendar import timegm
from collections import defaultdict
from unicodedata import normalize as unicode_normalize

logger = logging.getLogger('countbot')

WORDS = re.compile(r"(?:-\w|\w)[-\w]*")

def normalize(word):
	return unicode_normalize('NFC', word).lower()

class CounterBot(irc.bot.SingleServerIRCBot):
	def __init__(self, period, admins, ignored_users, nickname, channels, password=None, server='irc.twitch.tv', port=6667):
		irc.bot.SingleServerIRCBot.__init__(self, [(server, port, password)], nickname, nickname)
		self.period = period
		self.admins = set(admin.lower() for admin in admins)
		self.ignored_users = set(user.lower() for user in ignored_users)
		self.counts_per_channel = defaultdict(list)
		self.join_channels = [channel if channel.startswith('#') else '#'+channel for channel in channels]
		self.connection.execute_every(period, self.clearold)

	def clearold(self):
		timestamp = timegm(gmtime())
		periodts = timestamp - self.period
		rowcount = 0
		for counts in self.counts_per_channel.values():
			index = 0
			for index, (user, word, timestamp) in enumerate(counts):
				if timestamp >= periodts:
					break

			if index > 0:
				del counts[:index]
				rowcount += index

		print('gc: Deleted %d rows.' % rowcount if rowcount != 1 else 'gc: Deleted 1 row.')

	def on_welcome(self, connection, event):
		for channel in self.join_channels:
			connection.join(channel)
		connection.cap('REQ', 'twitch.tv/membership')

	def on_nicknameinuse(self, connection, event):
		logger.error('nickname in use')

	def on_error(self, connection, event):
		logger.error(' '.join(event.arguments))

	def on_pubmsg(self, connection, event):
		sender = event.source.nick

		if sender in self.ignored_users:
			return

		message = event.arguments[0]
		channel = event.target
		timestamp = timegm(gmtime())

#		print('PUBMSG', channel, sender, message)

		if message.startswith("!"):
			command, *args = message.rstrip().split()
			periodts = timestamp - self.period
			if command == '!count':
				words = args
				channel_counts = self.counts_per_channel[channel]
				all_user_words = defaultdict(set)

				if words:
					word_counts = dict((normalize(word), 0) for word in words)
					for user, word, timestamp in reversed(channel_counts):
						if timestamp < periodts:
							break

						if word in word_counts:
							user_words = all_user_words[word]
							if word not in user_words:
								word_counts[word] += 1
								user_words.add(word)

					# use the user provided way of lower/upper case
					word_counts = dict((word, word_counts[normalize(word)]) for word in words)
				else:
					word_counts = defaultdict(int)
					for user, word, timestamp in reversed(channel_counts):
						if timestamp < periodts:
							break

						user_words = all_user_words[word]
						if word not in user_words:
							word_counts[word] += 1
							user_words.add(word)

				self.report_counts(event, word_counts)

			elif command == '!countint':
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
						user_words = all_user_words[num]
						if num not in user_words:
							word_counts[num] += 1
							user_words.add(num)

				self.report_counts(event, word_counts)

			elif command == '!count1':
				channel_counts = self.counts_per_channel[channel]
				all_user_words = defaultdict(set)

				word_counts = defaultdict(int)
				for user, word, timestamp in reversed(channel_counts):
					if timestamp < periodts:
						break

					if len(word) == 1:
						user_words = all_user_words[word]
						if not word in user_words:
							word_counts[word] += 1
							user_words.add(word)

				self.report_counts(event, word_counts)

			elif command == '!clear':
				chan = self.channels[channel]
				if sender in self.admins or chan.is_oper(sender) or chan.is_admin(sender) or chan.is_owner(sender):
					rowcount = len(self.counts_per_channel[channel])
					if rowcount > 0:
						self.counts_per_channel[channel] = []
					self.answer(event, 'Deleted %d rows.' % rowcount if rowcount != 1 else 'Deleted 1 row.')
				else:
					self.answer(event, "@%s: You don't have permissions to do that." % sender)

		else:
			words = WORDS.findall(message)
			counts = self.counts_per_channel[channel]
			for word in words:
				counts.append((sender, normalize(word), timestamp))

	def report_counts(self, event, word_counts):
		counts = list(word_counts.items())
		counts.sort(key=lambda item: (item[1], item[0]))
		self.answer(event, ', '.join('%s: %d' % item for item in counts))

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

def main(args):
	import yaml
	import argparse

	parser = argparse.ArgumentParser()
	parser.add_argument('-c', '--config', default='config.yaml')
	parser.add_argument('-l', '--log-level', type=int, default=0)
	opts = parser.parse_args(args)

	logger.setLevel(opts.log_level)

	with open(opts.config,'rb') as fp:
		config = yaml.load(fp)

	server, port = config.get('host','irc.twitch.tv:6667').split(':', 1)
	port = int(port)

	bot = CounterBot(
		int(config.get('period', 60 * 5)),
		config.get('admins') or [],
		config.get('ignore') or [],
		config['nickname'],
		config['channels'],
		config.get('password'),
		server,
		port)

	bot.start()

if __name__ == '__main__':
	import sys

	try:
		main(sys.argv[1:])
	except KeyboardInterrupt:
		print()
