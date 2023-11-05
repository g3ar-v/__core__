import re
from itertools import chain
from threading import Lock
from typing import Any
from uuid import UUID

from langchain.callbacks.base import BaseCallbackHandler
from langchain.chains import LLMChain
from langchain.chat_models import ChatOpenAI
from langchain.schema.output import LLMResult

import core.intent_services
from core.llm import LLM, main_persona_prompt
from core.messagebus.message import Message, dig_for_message
from core.util import LOG, flatten_list
from core.util.resource_files import CoreResources
from core.util.time import now_local

EXTENSION_TIME = 10


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
        self._vocabs = {}
        self.llm = LLM()
        # self.bus.on("question:query.response", self.handle_query_response)
        # self.bus.on("common_query.question", self.handle_question)
        # self.bus.on("")

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
                    match = core.intent_services.IntentMatch(
                        "persona", None, {}, self.skill_id
                    )
                break
            self.bus.emit(
                Message(
                    "active_skill_request",
                    {"skill_id": self.skill_id},
                )
            )
        return match

    def is_question_like(self, utterance, lang):
        # skip utterances meant for common play
        if self.voc_match(utterance, "common_play", lang):
            return False
        return True

    def handle_query_response(self, message):
        today = now_local()
        date_str = today.strftime("%B %d, %Y")
        time_str = today.strftime("%I:%M %p")

        class CustomCallback(BaseCallbackHandler):
            def __init__(self, bus, skill_id) -> None:
                # self.outputs = outputs
                self.buffer = ""
                self.bus = bus
                self.skill_id = skill_id
                self.completed = False

            async def on_llm_new_token(
                self,
                token: str,
                *,
                run_id,
                parent_run_id=None,
                **kwargs: Any,
            ) -> None:
                self.buffer += token
                # LOG.info(f"tokens: {self.buffer}")
                if token in ["\n", "."]:  # if token is a newline or a full-stop
                    LOG.info(f"returning string: {self.buffer}")
                    self.speak(self.buffer)
                    self.buffer = ""  # reset the buffer

            async def on_llm_end(
                self,
                response: LLMResult,
                *,
                run_id: UUID,
                parent_run_id: UUID | None = None,
                **kwargs: Any,
            ) -> Any:
                self.bus.emit(Message("core.mic.listen"))

            def speak(self, utterance, expect_response=False, message=None):
                """Speak a sentence.

                Args:
                    utterance (str): sentence system should speak
                """
                # registers the skill as being active
                # self.enclosure.register(self.skill_id)

                message = message or dig_for_message()
                # lang = get_message_lang(message)
                data = {
                    "utterance": utterance,
                    "expect_response": expect_response,
                    "meta": {"skill": self.skill_id},
                }

                m = Message("speak", data)
                m.context["skill_id"] = self.skill_id
                self.bus.emit(m)

        outputs = []
        model = ChatOpenAI(
            temperature=0.7,
            max_tokens=85,
            model="gpt-3.5-turbo",
            streaming=True,
            callbacks=[CustomCallback(self.bus, self.skill_id)],
        )
        gptchain = LLMChain(llm=model, verbose=True, prompt=main_persona_prompt)

        # response = gptchain.predict(
        #     context=context,
        #     query=query,
        #     curr_conv=curr_conv,
        #     rel_mem=rel_mem,
        #     date_str=date_str,
        # )
        # for response in callback.string_generator():
        LOG.info(f"output: {outputs}")
        # return outputs

        # sys.stdout = stdout
        # token_list = stringio.getvalue().split("\x1b[0m")
        # for tokens in token_generator(model):
        #     LOG.info(f"output: {tokens}")

        chat_history = self.llm.chat_history.load_memory_variables({})["chat_history"]
        try:
            gptchain.predict(
                curr_conv=chat_history,
                rel_mem=None,
                date_str=date_str + ", " + time_str,
                query=message,
            )
            # LOG.info(f"persona is handling utterance: {responses}")
            # LOG.info(f"type of output: {responses}")
            # LOG.info(f"predictions: {prediction}")
            # self.speak(prediction)
            # for response in responses:
            # self.speak(response)
            self.answered = True
            return self.answered
        except Exception as e:
            LOG.error("error in llm response: {}".format(e))
            return None
