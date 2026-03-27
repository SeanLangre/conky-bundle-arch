#!/bin/bash
CONKY_DIR="$HOME/.config/conky"

# Kill existing instances
pkill -x conky
pkill -f twitch_chat.py
pkill -f discord_notifications.py
pkill -f get_stocks.py
sleep 2

# stock
conky -c "$CONKY_DIR/stock/stock_indices.conkyrc" --daemonize
sleep 1

# system
conky -c "$CONKY_DIR/titus/system_conky.conkyrc" --daemonize
sleep 1

# twitch
python3 "$CONKY_DIR/twitch_chat/twitch_chat.py" &
disown $!
conky -c "$CONKY_DIR/twitch_chat/twitch_chat.conkyrc" --daemonize
sleep 1

# discord
python3 "$CONKY_DIR/discord/discord_notifications.py" &
disown $!
conky -c "$CONKY_DIR/discord/discord_notifications.conkyrc" --daemonize
