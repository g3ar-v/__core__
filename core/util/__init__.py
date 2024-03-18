"""Core util library.

A collections of utils and tools for making skill development easier.
"""
from __future__ import absolute_import

import os

import core.audio

from .audio_utils import (find_input_device, play_audio_file, play_mp3,
                          play_ogg, play_wav, record)
from .file_utils import (create_file, curate_cache, ensure_directory_exists,
                         get_cache_directory, get_temp_path, read_dict,
                         read_stripped_lines, resolve_resource_file)
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
