
import mycroft_bus_client
from mycroft_bus_client.message import dig_for_message


class Message(mycroft_bus_client.Message):
    """Mycroft specific Message class."""
    def utterance_remainder(self):
        """
        For intents get the portion not consumed by Adapt.

        For example: if they say 'Turn on the family room light' and there are
        entity matches for "turn on" and "light", then it will leave behind
        " the family room " which is then normalized to "family room".

        Returns:
            str: Leftover words or None if not an utterance.
        """
        # utt = normalize(self.data.get("utterance", ""))
        # if utt and "__tags__" in self.data:
        #     for token in self.data["__tags__"]:
        #         # Substitute only whole words matching the token
        #         utt = re.sub(r'\b' + token.get("key", "") + r"\b", "", utt)

        # return normalize(utt)
        pass
