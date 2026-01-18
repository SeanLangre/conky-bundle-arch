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
MAX_MESSAGES = 15

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

def main():
    channel = get_channel()
    messages = deque(maxlen=MAX_MESSAGES)

    # Connect to Twitch IRC (anonymous read-only)
    sock = socket.socket()
    sock.connect(("irc.chat.twitch.tv", 6667))
    sock.send(b"NICK justinfan12345\r\n")
    sock.send(f"JOIN #{channel}\r\n".encode())

    # Save initial empty/status file
    messages.append(f"Connecting to #{channel}...")
    save_messages(messages)

    buffer = ""
    msg_pattern = re.compile(r":(\w+)!\w+@\w+\.tmi\.twitch\.tv PRIVMSG #\w+ :(.+)")

    while True:
        try:
            data = sock.recv(2048).decode("utf-8", errors="ignore")
            if not data:
                break

            buffer += data
            lines = buffer.split("\r\n")
            buffer = lines.pop()

            for line in lines:
                # Respond to PING to stay connected
                if line.startswith("PING"):
                    sock.send(b"PONG :tmi.twitch.tv\r\n")
                    continue

                # Parse chat messages
                match = msg_pattern.match(line)
                if match:
                    username, message = match.groups()
                    # Truncate long messages
                    if len(message) > 50:
                        message = message[:47] + "..."
                    # Truncate long usernames
                    if len(username) > 12:
                        username = username[:12]
                    messages.append(f"{username}: {message}")
                    save_messages(messages)

        except Exception as e:
            messages.append(f"Error: {e}")
            save_messages(messages)
            break

    sock.close()

if __name__ == "__main__":
    main()
