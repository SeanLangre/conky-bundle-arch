#!/bin/bash
sleep 10
conky -c $HOME/.config/conky/stock/stock_indices.conkyrc --daemonize
conky -c $HOME/.config/conky/titus/system_conky.conkyrc --daemonize

# Start Twitch chat listener in background
python3 $HOME/.config/conky/twitch_chat/twitch_chat.py &
conky -c $HOME/.config/conky/twitch_chat/twitch_chat.conkyrc --daemonize

# Start Discord notification listener in background
python3 $HOME/.config/conky/discord/discord_notifications.py &
conky -c $HOME/.config/conky/discord/discord_notifications.conkyrc --daemonize