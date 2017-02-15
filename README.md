WordCountBot
============

Very simple IRC bot that counts mentioned words in the last X seconds. A word is
only counted once per user and channel. This can be used to do simple votings
where the users have to mention the thing they vote for in chat and then you get
the counts with the command `!count THING1 THING2 THING3`.

This bot will be active on Twitch under https://www.twitch.tv/wordcountbot, but
isn't right now. If you want this bot to join your channel go to the linked
channel and enter `!join YOUR_CHANNEL_NAME`. You have to be the channel owner or
a mod of `YOUR_CHANNEL_NAME`.

Running the Bot
---------------

In case you run this bot yourself see `config.yaml.example` for an example
configuration. The actual configuration file has to be named `config.yaml` or
has to be passed via the `--config` argument to the script. If you use this bot
with Twitch you need to provide the OAuth token as the password, which you can
get [here](https://twitchapps.com/tmi/).

	python3 countbot.py

Home-Channel Commands
---------------------

These commands are only available in the home channel of the bot (which will be
https://www.twitch.tv/wordcountbot or if you run the bot yourself wherever you
point it to; it can also be omitted).

### !help [command]

Show help to given command.

### !commands

Show the list of commands.

### !join channel

Make WordCountBot join the given channel. Only allowed for operators of the
given channel.

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

# !count [words...]

Count given words or if none given all words. Every word is only counted once
per user and only in the configured time period (the last few seconds/minutes).

# !countint

Count integer numbers. Every number is only counted once per user and only in
the configured time period (the last few seconds/minutes).

# !count1

Count all one-letter words. Every word is only counted once per user and only in
the configured time period (the last few seconds/minutes).

# !clearcount

Clear all counts of this channel. Only allowed for operators etc.

# !countperiod [time]

Get or set the period in which words are counted for this channel. The time can
be given in hours, seconds or minutes, e.g.: 1h, 5min, 300sec, or even
combinations like 5m30s, but with no spaces between the parts.

# !countleave

Make WordCountBot leave this channel. Only allowed for operators of the given
channel. Not allowed for the home channel.

Dependencies
------------

 * [irc](https://pypi.org/project/irc/)
 * [yaml](http://pyyaml.org/wiki/PyYAML)

TODO
----

 * Add config option for maximum message length. Twitch has a limit of 500
   characters. I don't know if that are UTF-8 bytes, code points or graphemes.

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
