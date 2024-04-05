import time

from source.util.signal import check_for_signal


def is_speaking():
    """Determine if Text to Speech is occurring

    Returns:
        bool: True while still speaking
    """
    return check_for_signal("isSpeaking", -1)


def wait_while_speaking():
    """Pause as long as Text to Speech is still happening

    Pause while Text to Speech is still happening.  This always pauses
    briefly to ensure that any preceeding request to speak has time to
    begin.
    """
    time.sleep(0.3)  # Wait briefly in for any queued speech to begin
    while is_speaking():
        time.sleep(0.1)


def stop_speaking():
    """Stop system speech.

    TODO: Skills should only be able to stop speech they've initiated
    """
    if is_speaking():
        from source.messagebus.send import send

        send("core.audio.speech.stop")

        # Block until stopped
        while check_for_signal("isSpeaking", -1):
            time.sleep(0.25)
