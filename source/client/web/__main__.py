import asyncio

from source.client.web.web_client import start_web_ui
from source.messagebus.client.client import MessageBusClient
from source.util.process_utils import create_daemon, wait_for_exit_signal


def connect(bus):
    bus.run_forever()


def main():
    # RUN WEBSOCKET SERVER FOR UI

    try:
        bus = MessageBusClient()
        create_daemon(connect, args=(bus,))

        asyncio.get_event_loop().run_until_complete(start_web_ui(bus))

    except Exception:
        pass

    else:
        wait_for_exit_signal()


if __name__ == "__main__":
    main()
