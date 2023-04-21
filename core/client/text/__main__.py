import sys
import signal
import io
import os.path
import curses
from core.util import get_ipc_directory
from .text_client import (
        load_settings, save_settings, simple_cli, gui_main,
        start_log_monitor, start_mic_monitor, connect_to_mycroft,
        ctrl_c_handler
    )
from core.configuration import Configuration

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
    if 'log_dir' in config:
        log_dir = os.path.expanduser(config['log_dir'])
        start_log_monitor(os.path.join(log_dir, 'skills.log'))
        start_log_monitor(os.path.join(log_dir, 'voice.log'))
    else:
        start_log_monitor("/var/log/mycroft/skills.log")
        start_log_monitor("/var/log/mycroft/voice.log")

    # Monitor IPC file containing microphone level info
    start_mic_monitor(os.path.join(get_ipc_directory(), "mic_level"))

    connect_to_mycroft()
    if '--simple' in sys.argv:
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
