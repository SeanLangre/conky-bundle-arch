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
DEBUG_LOG = SCRIPT_DIR / "debug_apps.log"
MAX_NOTIFICATIONS = 8
MAX_CHANNEL_LEN = 20
MAX_MESSAGE_LEN = 45
DEDUP_WINDOW = 2  # seconds

DISCORD_NAMES = ("discord", "vesktop", "vencord")

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


def strip_bidi(text):
    """Remove Unicode bidirectional control characters."""
    return re.sub(r'[\u2066-\u2069\u200e\u200f\u202a-\u202e]', '', text)


def escape_conky(text):
    """Escape characters that conky would interpret."""
    return text.replace('\\', '\\\\').replace('$', '$$').replace('#', '')


def format_notification(summary, body):
    """Format a notification line with conky color codes."""
    summary = strip_bidi(summary)
    body = strip_bidi(body)
    if len(summary) > MAX_CHANNEL_LEN:
        summary = summary[:MAX_CHANNEL_LEN - 3] + "..."
    if len(body) > MAX_MESSAGE_LEN:
        body = body[:MAX_MESSAGE_LEN - 3] + "..."
    summary = escape_conky(summary)
    body = escape_conky(body)
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


def is_discord_source(*values):
    """Return True when any source hint matches Discord clients."""
    for value in values:
        if not value:
            continue
        lower_value = value.lower()
        if any(name in lower_value for name in DISCORD_NAMES):
            return True
    return False


def add_notification(summary, body):
    """Add a notification if not a duplicate."""
    if not is_duplicate(summary, body):
        history.append({"summary": summary, "body": body})
        notifications.append(format_notification(summary, body))
        save_notifications()


def debug_log(msg):
    """Append debug info to log file."""
    with open(DEBUG_LOG, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


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

        # Monitor both regular notifications and portal notifications
        match_rules = [
            "type='method_call',interface='org.freedesktop.Notifications',member='Notify'",
            "type='method_call',interface='org.freedesktop.portal.Notification',member='AddNotification'",
        ]
        bus.call_sync(
            'org.freedesktop.DBus',
            '/org/freedesktop/DBus',
            'org.freedesktop.DBus.Monitoring',
            'BecomeMonitor',
            GLib.Variant('(asu)', (match_rules, 0)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

        def on_message(connection, message, incoming):
            member = message.get_member()
            interface = message.get_interface()
            body = message.get_body()
            if body is None:
                return

            debug_log(f"member={member} interface={interface} sender={message.get_sender()}")

            if member == 'Notify':
                # Standard notification: (app_name, replaces_id, app_icon, summary, body, ...)
                app_name = body.get_child_value(0).get_string()
                debug_log(f"  Notify app_name={app_name}")
                if app_name.lower() not in DISCORD_NAMES:
                    return
                summary = body.get_child_value(3).get_string()
                notif_body = body.get_child_value(4).get_string()
                add_notification(summary, notif_body)

            elif member == 'AddNotification':
                # Portal notification: (id, notification_dict)
                # The dict contains 'title' and 'body' keys
                try:
                    notif_id = body.get_child_value(0).get_string()
                    notif_dict = body.get_child_value(1)
                    debug_log(f"  AddNotification id={notif_id} type={notif_dict.get_type_string()}")
                    # Extract title and body from the variant dict
                    summary = ""
                    notif_body = ""
                    desktop_entry = ""
                    app_name = ""
                    default_action = ""
                    n_entries = notif_dict.n_children()
                    for i in range(n_entries):
                        entry = notif_dict.get_child_value(i)
                        key = entry.get_child_value(0).get_string()
                        val = entry.get_child_value(1).get_variant()
                        debug_log(f"    key={key} val={val.get_type_string()}")
                        if key == "title":
                            summary = val.get_string()
                        elif key == "body":
                            notif_body = val.get_string()
                        elif key in ("desktop-entry", "desktop_entry"):
                            desktop_entry = val.get_string()
                        elif key in ("app-name", "app_name"):
                            app_name = val.get_string()
                        elif key == "default-action":
                            default_action = val.get_string()
                    if not is_discord_source(notif_id, desktop_entry, app_name, default_action):
                        debug_log("  AddNotification ignored (non-Discord source)")
                        return
                    if summary or notif_body:
                        add_notification(summary, notif_body)
                except Exception as e:
                    debug_log(f"  AddNotification parse error: {e}")

        bus.add_filter(on_message)

        load_history()
        save_notifications()
        loop = GLib.MainLoop()
        loop.run()
        return True

    except Exception as e:
        debug_log(f"BecomeMonitor failed: {e}")
        return False


def dbus_monitor_fallback():
    """Fallback: parse dbus-monitor output."""
    cmd = [
        "dbus-monitor",
        "--session",
        "type='method_call',interface='org.freedesktop.Notifications',member='Notify'",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    load_history()
    save_notifications()

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
                    if app_name.lower() in DISCORD_NAMES:
                        add_notification(summary, body)

            if line.startswith('method call') and 'member=Notify' not in line:
                in_notify = False

    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()


def main():
    signal.signal(signal.SIGTERM, lambda *_: exit(0))

    # Clear debug log on start
    with open(DEBUG_LOG, "w") as f:
        f.write("")

    if not try_gio_monitor():
        dbus_monitor_fallback()


if __name__ == "__main__":
    main()
