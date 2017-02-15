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

In case you run this bot yourself see `config.yaml.example` for an example
configuration. The actual configuration file has to be named `config.yaml` or be
passed via `--config /path/to/config.yaml`. If you use this bot with Twitch you
need to provide the OAuth token which you get [here](https://twitchapps.com/tmi/)
as the password.

Home-Channel Commands
---------------------

These commands are only available in the home channel (which will be
https://www.twitch.tv/wordcountbot or if you run the bot yourself wherever you
point it to; it can be omitted altogether).

### !help [command]

Show help to given command.

### !channels

List all channels joined by WordCountBot. WordCountBot-admin only.

### !commands

Show the list of commands.

### !join channel

Make WordCountBot join the given channel. Only allowed for operators of the
given channel.

### !leave channel

Make WordCountBot leave the given channel. Only allowed for operators of the
given channel.

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

TODO
----

 * Persist state like which channels are joined and per channel settings (and
   current counts?)
 * Add config option for maximum message length. Twitch has a limit of 500
   character. I don't know if that are UTF-8 bytes, code points or graphemes.
 * Decide on License. Probably MIT, maybe GPL. Definitely Open Source.
