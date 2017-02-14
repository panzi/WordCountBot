#!/usr/bin/env python3

import re
import irc.bot
import logging
import sqlite3
from time import gmtime
from calendar import timegm

logger = logging.getLogger('countbot')

WORDS = re.compile(r"[-\w]+")

class CounterBot(irc.bot.SingleServerIRCBot):
	def __init__(self, dbfile, period, nickname, channels, password=None, server='irc.twitch.tv', port=6667):
		irc.bot.SingleServerIRCBot.__init__(self, [(server, port, password)], nickname, nickname)
		self.period = period
		self.sqlcon = sqlite3.connect(dbfile)
		self.sqlcon.execute('create table if not exists counts (channel text, user text, word text, timestamp integer)')
		self.sqlcon.execute('create unique index if not exists counts_index on counts (channel, user, word, timestamp)')
		self.sqlcon.commit()
		self.join_channels = [channel if channel.startswith('#') else '#'+channel for channel in channels]
		self.connection.execute_every(period, self.clearold)

	def clearold(self):
		timestamp = timegm(gmtime())
		periodts = timestamp - self.period
		rowcount = self.sqlcon.execute(
			'delete from counts where timestamp < ?',
			(periodts, )).rowcount
		self.sqlcon.commit()
		print('Deleted %d rows.' % rowcount if rowcount != 1 else 'Deleted 1 row.')

	def on_welcome(self, connection, event):
		for channel in self.join_channels:
			connection.join(channel)
		connection.cap('REQ', 'twitch.tv/membership')

	def on_nicknameinuse(self, connection, event):
		logger.error('nickname in use')

	def on_error(self, connection, event):
		logger.error(' '.join(event.arguments))

	def on_pubmsg(self, connection, event):
		sender  = event.source.nick
		message = event.arguments[0]
		channel = event.target
		timestamp = timegm(gmtime())

#		print('PUBMSG', channel, sender, message)

		if message.startswith("!"):
			command, *args = message.rstrip().split()
			if command == '!count':
				words = args
				periodts = timestamp - self.period
				counts = []

				if words:
					for word in words:
						cur = self.sqlcon.execute(
							'select count(distinct user) from counts where channel = ? and word = ? and timestamp >= ?',
							(channel, word.lower(), periodts))
						count, = cur.fetchone()
						counts.append((word, count))
				else:
					cur = self.sqlcon.execute(
						'select word, count(distinct user) from counts where channel = ? and timestamp >= ? group by word',
						(channel, periodts))
					counts = cur.fetchall()

				counts.sort(key=lambda item: (item[1], item[0]))
				self.answer(event, ', '.join('%s: %d' % item for item in counts))

			elif command == '!clear':
				if self.channels[channel].is_oper(sender):
					rowcount = self.sqlcon.execute(
						'delete from counts where channel = ?',
						(channel, )).rowcount
					self.sqlcon.commit()
					self.answer(event, 'Deleted %d rows.' % rowcount if rowcount != 1 else 'Deleted 1 row.')

		else:
			words = WORDS.findall(message)
			self.sqlcon.executemany(
				"insert or ignore into counts (channel, user, word, timestamp) values (?, ?, ?, ?)",
				[(channel, sender, word.lower(), timestamp) for word in words])
			self.sqlcon.commit()

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

	def close(self):
		self.sqlcon.close()

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

	dbfile = config.get('dbfile', ':memory:')
	server, port = config.get('host','irc.twitch.tv:6667').split(':', 1)
	port = int(port)

	bot = CounterBot(
		dbfile,
		int(config.get('period', 60 * 5)),
		config['nickname'],
		config['channels'],
		config.get('password'),
		server,
		port)

	try:
		bot.start()
	finally:
		bot.close()

if __name__ == '__main__':
	import sys

	try:
		main(sys.argv[1:])
	except KeyboardInterrupt:
		print()
