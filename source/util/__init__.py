"""Core util library.

A collections of utils and tools for making skill development easier.
"""

from __future__ import absolute_import

import os

import xdg.BaseDirectory  # Added import statement

import source.audio

from .audio_utils import (find_input_device, play_audio_file, play_mp3,
                          play_ogg, play_wav, record)
from .file_utils import get_temp_path  # Updated import
from .file_utils import (create_file, curate_cache, ensure_directory_exists,
                         get_cache_directory, read_dict, read_stripped_lines)
from .log import LOG
from .network_utils import connected_to_the_internet
# from .parse import extract_datetime, extract_number, normalize
from .platform import get_arch, get_enclosure
from .process_utils import (create_daemon, create_echo_function,
                            reset_sigint_handler, start_message_bus_client,
                            wait_for_exit_signal)
from .signal import check_for_signal, create_signal, get_ipc_directory
from .string_utils import camel_case_split

# from core.util.format import nice_number


def flatten_list(some_list, tuples=True):
    def _flatten(l):
        return [item for sublist in l for item in sublist]

    if tuples:
        while any(isinstance(x, list) or isinstance(x, tuple) for x in some_list):
            some_list = _flatten(some_list)
    else:
        while any(isinstance(x, list) for x in some_list):
            some_list = _flatten(some_list)
    return some_list


def resolve_resource_file(res_name):
    """Convert a resource into an absolute filename.

    Resource names are in the form: 'filename.ext'
    or 'path/filename.ext'

    The system wil look for $XDG_DATA_DIRS/core/res_name first
    (defaults to ~/.local/share/core/res_name), and if not found will
    look at /opt/core/res_name, then finally it will look for res_name
    in the 'core/res' folder of the source code package.

    Example:
        With mycore running as the user 'bob', if you called
        ``resolve_resource_file('snd/beep.wav')``
        it would return either:
        '$XDG_DATA_DIRS/core/beep.wav',
        '/home/bob/.core/snd/beep.wav' or
        '/opt/core/snd/beep.wav' or
        '.../core/res/snd/beep.wav'
        where the '...' is replaced by the path
        where the package has been installed.

    Args:
        res_name (str): a resource path/name

    Returns:
        (str) path to resource or None if no resource found
    """

    config = source.configuration.Configuration.get()

    # First look for fully qualified file (e.g. a user setting)
    if os.path.isfile(res_name):
        return res_name

    # Now look for XDG_DATA_DIRS
    for conf_dir in xdg.BaseDirectory.load_data_paths("core"):
        filename = os.path.join(conf_dir, res_name)
        if os.path.isfile(filename):
            return filename

    # Now look in the old user location
    filename = os.path.join(os.path.expanduser("~"), ".core", res_name)
    if os.path.isfile(filename):
        return filename

    # Next look for /opt/core/res/res_name
    data_dir = os.path.join(os.path.expanduser(config["data_dir"]), "res")
    filename = os.path.expanduser(os.path.join(data_dir, res_name))
    if os.path.isfile(filename):
        return filename

    # Finally look for it in the source package
    filename = os.path.join(os.path.dirname(__file__), "..", "res", res_name)
    filename = os.path.abspath(os.path.normpath(filename))
    if os.path.isfile(filename):
        return filename

    return None  # Resource cannot be resolved
