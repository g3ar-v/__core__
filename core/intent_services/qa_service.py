import re
from itertools import chain
from threading import Lock

from langchain.chains import LLMChain

# from langchain.callbacks import StopStream
from langchain.chat_models import ChatOpenAI
from langchain.llms import LlamaCpp
from lingua_franca.format import nice_date_time

import core.intent_services
from core.configuration import Configuration
from core.llm import LLM, main_persona_prompt
from core.llm.llm import CustomCallback
from core.util import LOG, flatten_list
from core.util.resource_files import CoreResources
from core.util.time import now_local

config = Configuration.get()


class QAService:
    """
    Core persona of the system, provides conversation and retrieval of
    relevant information
    """

    # TODO: add to active skill list for convesation
    # TODO: fix "I don't understand at the end"
    def __init__(self, bus):
        self.bus = bus
        self.skill_id = "persona"
        self.lock = Lock()
        self.answered = False
        self.interrupted = False
        self._vocabs = {}
        self.llm = LLM(bus)

    def voc_match(self, utterance, voc_filename, lang, exact=False):
        """Determine if the given utterance contains the vocabulary provided.

        By default the method checks if the utterance contains the given vocab
        thereby allowing the user to say things like "yes, please" and still
        match against "Yes.voc" containing only "yes". An exact match can be
        requested.

        The method checks the "res/text/{lang}" folder of mycroft-core.
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
                answered = self.handle_query_response(utterance)
                if answered:
                    match = core.intent_services.IntentMatch("persona", None, {}, None)
                break

        return match

    def is_question_like(self, utterance, lang):
        # skip utterances meant for common play
        if self.voc_match(utterance, "common_play", lang):
            return False
        return True

    def handle_query_response(self, message):
        today = now_local()
        date = nice_date_time(today)

        # NOTE:
        # use offline or online model
        if config.get("llm", {}).get("model_type", {}) == "online":
            model = ChatOpenAI(
                temperature=0.7,
                max_tokens=256,
                model="gpt-3.5-turbo",
                streaming=True,
                callbacks=[CustomCallback(self.bus, None)],
            )
        else:
            model_name = config.get("llm", {}).get("model_type", {})
            model = LlamaCpp(
                model_path=config.get("llm", {}).get(model_name, {}).get("model_dir"),
                n_gpu_layers=1,
                n_batch=512,
                n_ctx=2048,
                f16_kv=True,
                verbose=True,
                streaming=True,
                callbacks=[CustomCallback(self.bus, None)],
            )
        gptchain = LLMChain(
            llm=model or self.llm.model, verbose=True, prompt=main_persona_prompt
        )

        chat_history = self.llm.chat_history.load_memory_variables({})["chat_history"]
        try:
            gptchain.predict(
                curr_conv=chat_history,
                rel_mem=None,
                date_str=date,
                query=message,
            )

            self.answered = True
            return self.answered
        except Exception as e:
            LOG.error("error in llm response: {}".format(e))
            return None
