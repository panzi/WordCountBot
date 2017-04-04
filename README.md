WordCountBot
============

Very simple IRC bot that counts mentioned words in the last X seconds. A word is
only counted once per user and channel. This can be used to do simple votings
where the users have to mention the thing they vote for in chat and then you get
the counts with the command `!count THING1 THING2 THING3`.

This bot is active on Twitch under [https://www.twitch.tv/wordcountbot](https://www.twitch.tv/wordcountbot).
If you want this bot to join your channel go to that channel and enter
`!join YOUR_CHANNEL_NAME`. You have to be the channel owner or a mod of
`YOUR_CHANNEL_NAME`. Note that I currently use Heroku's free plan and thus have
no persitence. If my one free server instance restarts if forgets all joined
channels and counted words.

Running the Bot
---------------

In case you run this bot yourself see `config.yaml.example` for an example
configuration. The actual configuration file has to be named `config.yaml` or
has to be passed via the `--config` argument to the script. If you use this bot
with Twitch you need to provide the OAuth token as the password, which you can
get [here](https://twitchapps.com/tmi/).

	python3 countbot.py

### Options

	-c FILE, --config=FILE     Read configuration from FILE.
	         --env-config      Read configuration from the environment.

When reading the configuration from the environment the keys are uppercase and
prefixed with `COUNTBOT_`. Lists are comma separated.

Home-Channel Commands
---------------------

These commands are only available in the home channel of the bot (which is
https://www.twitch.tv/wordcountbot or if you run the bot yourself wherever you
point it to; it can also be omitted).

### !help [command]

Show help to given command.

### !commands

Show the list of commands (ignoring aliases).

### !join channel

Make WordCountBot join the given channel. Only allowed for operators of the
given channel.

**Note:** If I host this bot somewhere and too many people use it for any fee
hosting quota I might disable this command/make it bot admin-only. You can
always host the bot yourself!

### !leave channel

Make WordCountBot leave the given channel. Only allowed for operators of the
given channel.

### !channels

List all channels joined by WordCountBot. WordCountBot-admin only.

### !gcinterval [value]

Get or set gcinterval. WordCountBot-admin only.

Commands
--------

These commands are available in the channels the bot has joined.

### !count [words...]

Count given words or if none given all words. Every word is only counted once
per user and only in the configured time period (the last few seconds/minutes).
If a non-operator invokes this command the list of results is truncated to 10
entries to prevent spamming the channel.

**TODO:** Maybe always truncate the list of results? Maybe make the number of
results configurable (per channel)?

### !countint

Count integer numbers. Every number is only counted once per user and only in
the configured time period (the last few seconds/minutes).

Because of common typos there are these aliases for this command: `!countinit`,
`!initcount`, `!intcount`

### !count1

Count all one-letter words. Every word is only counted once per user and only in
the configured time period (the last few seconds/minutes).

### !clearcount

Clear all counts of this channel. Only allowed for operators etc.

### !countperiod [time]

Get or set the period in which words are counted for this channel. The time can
be given in hours, seconds or minutes, e.g.: 1h, 5min, 300sec, or even
combinations like 5m 30s.

### !countleave

Make WordCountBot leave this channel. Only allowed for operators of the given
channel. Not allowed for the home channel.

Dependencies
------------

 * [Python 3](https://www.python.org/)
 * [irc](https://pypi.org/project/irc/) Python library
 * [yaml](http://pyyaml.org/wiki/PyYAML) Python library

MIT License
-----------

Copyright 2017 Mathias Panzenböck

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
