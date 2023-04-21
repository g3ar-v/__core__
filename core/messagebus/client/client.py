from mycroft_bus_client import MessageBusClient as _MessageBusClient
from mycroft_bus_client.client import MessageWaiter

from core.messagebus.load_config import load_message_bus_config
from core.util.process_utils import create_echo_function


class MessageBusClient(_MessageBusClient):
    def __init__(self, host=None, port=None, route=None, ssl=None):
        config_overrides = dict(host=host, port=port, route=route, ssl=ssl)
        config = load_message_bus_config(**config_overrides)
        super().__init__(config.host, config.port, config.route, config.ssl)


def echo():
    message_bus_client = MessageBusClient()

    def repeat_utterance(message):
        message.msg_type = 'speak'
        message_bus_client.emit(message)

    message_bus_client.on('message', create_echo_function(None))
    message_bus_client.on('recognizer_loop:utterance', repeat_utterance)
    message_bus_client.run_forever()


if __name__ == "__main__":
    echo()
