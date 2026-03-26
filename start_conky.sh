#!/bin/bash
CONKY_DIR="$HOME/.config/conky"

# Kill existing instances
pkill -f twitch_chat.py
pkill -f discord_notifications.py
pkill conky
sleep 2

# stock
conky -c "$CONKY_DIR/stock/stock_indices.conkyrc" --daemonize
sleep 1

# system
conky -c "$CONKY_DIR/titus/system_conky.conkyrc" --daemonize
sleep 1

# twitch
python3 "$CONKY_DIR/twitch_chat/twitch_chat.py" &
TWITCH_PY=$!
conky -c "$CONKY_DIR/twitch_chat/twitch_chat.conkyrc" &
TWITCH_CONKY=$!

# discord
python3 "$CONKY_DIR/discord/discord_notifications.py" &
DISCORD_PY=$!
conky -c "$CONKY_DIR/discord/discord_notifications.conkyrc" &
DISCORD_CONKY=$!

# Kill python when conky dies
( wait $TWITCH_CONKY;  kill $TWITCH_PY  2>/dev/null ) &
( wait $DISCORD_CONKY; kill $DISCORD_PY 2>/dev/null ) &
