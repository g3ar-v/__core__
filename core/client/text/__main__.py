import curses
import io
import os.path
import signal
import sys

from core.client.text.text_client import (connect_to_core, ctrl_c_handler,
                                          gui_main, load_settings,
                                          save_settings, simple_cli,
                                          start_log_monitor, start_mic_monitor)
from core.configuration import Configuration
from core.util import get_ipc_directory

sys.stdout = io.StringIO()
sys.stderr = io.StringIO()


def custom_except_hook(exctype, value, traceback):
    print(sys.stdout.getvalue(), file=sys.__stdout__)
    print(sys.stderr.getvalue(), file=sys.__stderr__)
    sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    sys.__excepthook__(exctype, value, traceback)


sys.excepthook = custom_except_hook  # noqa


def main():
    # Monitor system logs
    config = Configuration.get()
    if "log_dir" in config:
        log_dir = os.path.expanduser(config["log_dir"])
        start_log_monitor(os.path.join(log_dir, "skills.log"))
        start_log_monitor(os.path.join(log_dir, "voice.log"))
        start_log_monitor(os.path.join(log_dir, "audio.log"))
    else:
        start_log_monitor("/var/log/core/skills.log")
        start_log_monitor("/var/log/core/voice.log")
        start_log_monitor("/var/log/core/web.log")
        # start_log_monitor("/var/log/core/audio.log")

    # Monitor IPC file containing microphone level info
    start_mic_monitor(os.path.join(get_ipc_directory(), "mic_level"))

    connect_to_core()
    if "--simple" in sys.argv:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        simple_cli()
    else:
        # Special signal handler allows a clean shutdown of the GUI
        signal.signal(signal.SIGINT, ctrl_c_handler)
        load_settings()
        curses.wrapper(gui_main)
        curses.endwin()
        save_settings()


if __name__ == "__main__":
    main()
