"""Entrypoint for enclosure service.

This provides any "enclosure" specific functionality, for example GUI or
control over the Mark-1 Faceplate.
"""
from core.configuration import Configuration
from core.util.log import LOG
from core.util import wait_for_exit_signal, reset_sigint_handler, get_enclosure


def on_ready():
    LOG.info("Enclosure started!")


def on_stopping():
    LOG.info('Enclosure is shutting down...')


def on_error(e='Unknown'):
    LOG.error('Enclosure failed: {}'.format(repr(e)))


def create_enclosure(platform):
    """Create an enclosure based on the provided platform string.
        Circa 2023 there's Linux and Raspberry Pi
        difference: so that pi can access GPio pins

    Args:
        platform (str): platform name string

    Returns:
        Enclosure object
    """
    if platform == "raspberry pi":
        LOG.info("Creating Pi Enclosure")
        from core.client.enclosure.pi import EnclosurePi
        enclosure = EnclosurePi()
    else:
        LOG.info("Creating generic linux enclosure, platform='{}'".format(platform))

        # TODO: Mechanism to load from elsewhere.  E.g. read a script path from
        # the mycroft.conf, then load/launch that script.
        from core.client.enclosure.linux import EnclosureGeneric
        enclosure = EnclosureGeneric()

    return enclosure


def main(ready_hook=on_ready, error_hook=on_error, stopping_hook=on_stopping):
    """Launch one of the available enclosure implementations.

    This depends on the configured platform and can currently either be pi or linux,
    if unconfigured a generic enclosure with only the GUI bus will be started.
    """
    # Read the system configuration
    config = Configuration.get(remote=False)
    platform = get_enclosure() or config.get("enclosure", {}).get("platform")

    enclosure = create_enclosure(platform)
    if enclosure:
        LOG.debug("Enclosure created")
        try:
            reset_sigint_handler()
            enclosure.run()
            ready_hook()
            wait_for_exit_signal()
            enclosure.stop()
            stopping_hook()
        except Exception as e:
            error_hook(e)
    else:
        LOG.info("No enclosure available for this hardware, running headless")


if __name__ == "__main__":
    main()
