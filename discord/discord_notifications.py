#!/usr/bin/env python3
"""Monitor D-Bus for Discord notifications and write to file for conky display."""

import json
import os
import signal
import subprocess
import re
import time
from pathlib import Path
from collections import deque

SCRIPT_DIR = Path(__file__).parent
NOTIF_FILE = SCRIPT_DIR / "notifications.txt"
NOTIF_TMP = SCRIPT_DIR / "notifications.tmp"
HISTORY_FILE = SCRIPT_DIR / "history.json"
MAX_NOTIFICATIONS = 8
MAX_CHANNEL_LEN = 20
MAX_MESSAGE_LEN = 45
DEDUP_WINDOW = 2  # seconds

notifications = deque(maxlen=MAX_NOTIFICATIONS)
history = deque(maxlen=MAX_NOTIFICATIONS)
last_notif = {"summary": "", "body": "", "time": 0}


def load_history():
    """Load notification history from disk on startup."""
    try:
        with open(HISTORY_FILE, "r") as f:
            entries = json.load(f)
        for entry in entries[-MAX_NOTIFICATIONS:]:
            history.append(entry)
            notifications.append(format_notification(entry["summary"], entry["body"]))
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass


def save_history():
    """Persist raw notification data to disk."""
    with open(HISTORY_FILE, "w") as f:
        json.dump(list(history), f)


def save_notifications():
    """Atomically write notifications to file for conky to read."""
    with open(NOTIF_TMP, "w") as f:
        if not notifications:
            f.write("Listening for Discord notifications...\n")
        else:
            for entry in notifications:
                f.write(entry + "\n")
    os.rename(NOTIF_TMP, NOTIF_FILE)
    save_history()


def format_notification(summary, body):
    """Format a notification line with conky color codes."""
    if len(summary) > MAX_CHANNEL_LEN:
        summary = summary[:MAX_CHANNEL_LEN - 3] + "..."
    if len(body) > MAX_MESSAGE_LEN:
        body = body[:MAX_MESSAGE_LEN - 3] + "..."
    return f"${{color5}}{summary}${{color}}: {body}"


def is_duplicate(summary, body):
    """Check if this notification is a rapid duplicate."""
    now = time.time()
    if (summary == last_notif["summary"]
            and body == last_notif["body"]
            and now - last_notif["time"] < DEDUP_WINDOW):
        return True
    last_notif["summary"] = summary
    last_notif["body"] = body
    last_notif["time"] = now
    return False


def try_gio_monitor():
    """Try using GLib/Gio BecomeMonitor approach."""
    try:
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio, GLib
    except (ImportError, ValueError):
        return False

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        # Try BecomeMonitor
        match_rule = "type='method_call',interface='org.freedesktop.Notifications',member='Notify'"
        bus.call_sync(
            'org.freedesktop.DBus',
            '/org/freedesktop/DBus',
            'org.freedesktop.DBus.Monitoring',
            'BecomeMonitor',
            GLib.Variant('(asu)', ([match_rule], 0)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

        def on_message(connection, message, incoming):
            if message.get_member() != 'Notify':
                return
            body = message.get_body()
            if body is None:
                return
            # Notify args: (app_name, replaces_id, app_icon, summary, body, actions, hints, timeout)
            app_name = body.get_child_value(0).get_string()
            if app_name.lower() not in ("discord", "vesktop", "vencord"):
                return
            summary = body.get_child_value(3).get_string()
            notif_body = body.get_child_value(4).get_string()
            if not is_duplicate(summary, notif_body):
                history.append({"summary": summary, "body": notif_body})
                notifications.append(format_notification(summary, notif_body))
                save_notifications()

        bus.add_filter(on_message)

        load_history()
        save_notifications()
        loop = GLib.MainLoop()
        loop.run()
        return True

    except Exception:
        return False


def dbus_monitor_fallback():
    """Fallback: parse dbus-monitor output."""
    cmd = [
        "dbus-monitor",
        "--session",
        "type='method_call',interface='org.freedesktop.Notifications',member='Notify'"
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    load_history()
    save_notifications()

    # Parse dbus-monitor text output
    # Notify calls look like:
    #   method call ... member=Notify
    #   string "Discord"       <- app_name
    #   uint32 0               <- replaces_id
    #   string "discord"       <- app_icon
    #   string "Channel Name"  <- summary
    #   string "Message text"  <- body
    in_notify = False
    string_count = 0
    app_name = ""
    summary = ""
    body = ""
    string_pattern = re.compile(r'^\s+string\s+"(.*)"$')

    try:
        for line in proc.stdout:
            line = line.rstrip('\n')

            if 'member=Notify' in line:
                in_notify = True
                string_count = 0
                app_name = ""
                summary = ""
                body = ""
                continue

            if not in_notify:
                continue

            match = string_pattern.match(line)
            if match:
                string_count += 1
                value = match.group(1)
                if string_count == 1:
                    app_name = value
                elif string_count == 3:
                    summary = value
                elif string_count == 4:
                    body = value
                    in_notify = False
                    if app_name.lower() in ("discord", "vesktop", "vencord"):
                        if not is_duplicate(summary, body):
                            history.append({"summary": summary, "body": body})
                            notifications.append(format_notification(summary, body))
                            save_notifications()

            # Reset if we hit a new method call before finishing
            if line.startswith('method call') and 'member=Notify' not in line:
                in_notify = False

    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()


def main():
    signal.signal(signal.SIGTERM, lambda *_: exit(0))

    if not try_gio_monitor():
        dbus_monitor_fallback()


if __name__ == "__main__":
    main()
