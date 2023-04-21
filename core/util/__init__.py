"""Mycroft util library.

A collections of utils and tools for making skill development easier.
"""
from __future__ import absolute_import

import os

import core.audio
from core.util.format import nice_number
from .string_utils import camel_case_split
from .audio_utils import (play_audio_file, play_wav, play_ogg, play_mp3,
                          record, find_input_device)
from .file_utils import (
    resolve_resource_file,
    read_stripped_lines,
    read_dict,
    create_file,
    get_temp_path,
    ensure_directory_exists,
    curate_cache,
    get_cache_directory)
from .network_utils import connected
from .process_utils import (reset_sigint_handler, create_daemon,
                            wait_for_exit_signal, create_echo_function,
                            start_message_bus_client)
from .log import LOG
from .parse import extract_datetime, extract_number, normalize
from .signal import check_for_signal, create_signal, get_ipc_directory
from .platform import get_arch, get_enclosure
