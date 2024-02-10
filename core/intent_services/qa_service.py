import re
from itertools import chain
from threading import Lock

import core.intent_services
from core.api import SystemApi
from core.configuration import Configuration
from core.llm import LLM, main_persona_prompt, parser
from core.messagebus.message import Message
from core.util import LOG, flatten_list
from core.util.resource_files import CoreResources

config = Configuration.get()


# TODO: create a fallback timer to skip function after a while if information has not
# been produced
class QAService:
    """
    Core persona of the system, provides conversation and retrieval of
    relevant information
    """

    def __init__(self, bus):
        self.bus = bus
        self.skill_id = "persona"
        self.lock = Lock()
        self.answered = False
        self.interrupted = False
        self._vocabs = {}
        self.api = SystemApi()

    def voc_match(self, utterance, voc_filename, lang, exact=False):
        """Determine if the given utterance contains the vocabulary provided.

        By default the method checks if the utterance contains the given vocab
        thereby allowing the user to say things like "yes, please" and still
        match against "Yes.voc" containing only "yes". An exact match can be
        requested.

        The method checks the "res/text/{lang}" folder of CORE.
        The result is cached to avoid hitting the disk each time the method is called.

        Args:
            utterance (str): Utterance to be tested
            voc_filename (str): Name of vocabulary file (e.g. 'yes' for
                                'res/text/en-us/yes.voc')
            lang (str): Language code, defaults to self.lang
            exact (bool): Whether the vocab must exactly match the utterance

        Returns:
            bool: True if the utterance has the given vocabulary it
        """
        match = False

        if lang not in self._vocabs:
            resources = CoreResources(language=lang)
            vocab = resources.load_vocabulary_file(voc_filename)
            self._vocabs[lang] = list(chain(*vocab))

        if utterance:
            if exact:
                # Check for exact match
                match = any(i.strip() == utterance for i in self._vocabs[lang])
            else:
                # Check for matches against complete words
                match = any(
                    [
                        re.match(r".*\b" + i + r"\b.*", utterance)
                        for i in self._vocabs[lang]
                    ]
                )

        return match

    def match(self, utterances, lang, message):
        """Send common query request and select best response

        Args:
            utterances (list): List of tuples,
                               utterances and normalized version
            lang (str): Language code
            message: Message for session context
        Returns:
            IntentMatch or None
        """
        # we call flatten in case someone is sending the old style list of tuples
        # LOG.info("utterances: {}".format(utterances))
        utterances = flatten_list(utterances)
        match = None
        # LOG.info("utterances after flattening: {}".format(utterances))
        for utterance in utterances:
            if self.is_question_like(utterance, lang):
                message.data["lang"] = lang  # only used for speak
                message.data["utterance"] = utterance
                # LOG.info(f"message passed to the persona's matching func: {message}")
                answered = self.handle_query_response(utterance, message)
                if answered:
                    # NOTE: imported in format to prevent circular import error
                    match = core.intent_services.IntentMatch(
                        "persona", None, None, None
                    )
                break

        return match

    def is_question_like(self, utterance, lang) -> bool:
        # skip utterances meant for common play
        if self.voc_match(utterance, "common_play", lang):
            return False
        return True

    def handle_query_response(self, utterance: str, message: dict) -> bool:
        try:
            if message.data.get("context", {}).get("source", {}) == "ui_backend":
                response = LLM.llm_response(
                    query=utterance,
                    prompt=main_persona_prompt,
                    send_to_ui=False,
                    parser=parser,
                )
                self.bus.emit(
                    Message(
                        "core.utterance.response",
                        {"done": True, "message": {"content": response}},
                    )
                )

            else:
                response = LLM.llm_response(
                    query=utterance, prompt=main_persona_prompt, parser=parser
                )

            return True
        except Exception as e:
            LOG.error("error in QA response: {}".format(e))
            return False
