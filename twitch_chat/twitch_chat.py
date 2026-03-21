#!/usr/bin/env python3
"""Connect to Twitch IRC and save chat messages for conky display."""

import socket
import re
import os
from pathlib import Path
from collections import deque

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.txt"
CHAT_FILE = SCRIPT_DIR / "chat.txt"
MAX_MESSAGES = 9

def get_channel():
    """Read channel name from config file."""
    if CONFIG_FILE.exists():
        return CONFIG_FILE.read_text().strip().lower()
    return "lirik"

def save_messages(messages):
    """Save messages to file for conky to read."""
    with open(CHAT_FILE, "w") as f:
        for msg in messages:
            f.write(msg + "\n")

def connect_to_channel(channel):
    """Connect to Twitch IRC for the given channel."""
    sock = socket.socket()
    sock.settimeout(5.0)  # Timeout for checking config changes
    sock.connect(("irc.chat.twitch.tv", 6667))
    sock.send(b"NICK justinfan12345\r\n")
    sock.send(f"JOIN #{channel}\r\n".encode())
    return sock

def main():
    channel = get_channel()
    messages = deque(maxlen=MAX_MESSAGES)
    msg_pattern = re.compile(r":(\w+)!\w+@\w+\.tmi\.twitch\.tv PRIVMSG #\w+ :(.+)")

    while True:
        messages.clear()
        messages.append(f"Connecting to #{channel}...")
        save_messages(messages)

        try:
            sock = connect_to_channel(channel)
        except Exception as e:
            messages.append(f"Connection error: {e}")
            save_messages(messages)
            import time
            time.sleep(5)
            channel = get_channel()
            continue

        buffer = ""

        while True:
            # Check if channel changed
            new_channel = get_channel()
            if new_channel != channel:
                channel = new_channel
                sock.close()
                break  # Reconnect to new channel

            try:
                data = sock.recv(2048).decode("utf-8", errors="ignore")
                if not data:
                    break

                buffer += data
                lines = buffer.split("\r\n")
                buffer = lines.pop()

                for line in lines:
                    if line.startswith("PING"):
                        sock.send(b"PONG :tmi.twitch.tv\r\n")
                        continue

                    match = msg_pattern.match(line)
                    if match:
                        username, message = match.groups()
                        if len(message) > 50:
                            message = message[:47] + "..."
                        if len(username) > 12:
                            username = username[:12]
                        messages.append(f"{username}: {message}")
                        save_messages(messages)

            except socket.timeout:
                continue  # Normal timeout, check for config changes
            except Exception as e:
                messages.append(f"Error: {e}")
                save_messages(messages)
                break

        sock.close()

if __name__ == "__main__":
    main()
