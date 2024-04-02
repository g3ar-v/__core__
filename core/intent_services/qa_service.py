from threading import Lock

import core.intent_services
from core.configuration import Configuration
from core.llm import LLM, main_persona_prompt
from core.messagebus.message import Message
from core.skills import Skill
from core.util import LOG
from core.audio import wait_while_speaking

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
        self.capabilities = Skill()
        self.skill_id = "persona"

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
        match = None
        if self.is_question_like(utterances, lang):
            message.data["lang"] = lang  # only used for speak
            message.data["utterance"] = utterances
            answered = self.handle_query_response(utterances, message)
            if answered:
                match = core.intent_services.IntentMatch("persona", None, None, None)

        return match

    def is_question_like(self, utterance, lang) -> bool:
        # skip utterances meant for common play
        if self.capabilities.voc_match(utterance, "common_play", lang):
            return False
        return True

    def handle_query_response(self, utterance: str, message: dict) -> bool:
        sentence = ""
        system_message = ""
        try:
            # get response from llm when chat is initiated from UI
            if message.data.get("context", {}).get("source", {}) == "ui_backend":
                response = LLM.chat_with_system(
                    query=utterance,
                    prompt=main_persona_prompt,
                    send_to_ui=False,
                )
                self.bus.emit(
                    Message(
                        "core.utterance.response",
                        {"done": True, "message": {"content": response}},
                    )
                )

            else:
                for chunk in LLM.chat_with_system(
                    query=utterance, prompt=main_persona_prompt
                ):
                    LOG.debug(f"chunk in qa service: {chunk}")
                    if "start" in chunk:
                        self.bus.emit(
                            Message(
                                "core.utterance.response",
                                {"content": chunk},
                            )
                        )
                        if chunk["type"] == "code":
                            self.bus.emit(
                                Message(
                                    "core.utterance.response",
                                    {
                                        "content": {
                                            "role": "assistant",
                                            "type": "message",
                                            "content": "```",
                                        }
                                    },
                                )
                            )
                        # self.capabilities.send_to_ui(chunk)
                    if chunk["type"] == "message" and "content" in chunk:
                        sentence += chunk["content"]
                        system_message += chunk[
                            "content"
                        ]  # Continuously add chunk to system message
                        self.bus.emit(
                            Message(
                                "core.utterance.response",
                                {"content": chunk},
                            )
                        )
                        if any([punct in sentence for punct in ".?!\n"]):
                            LLM._speak(sentence)
                            sentence = ""
                    elif chunk["type"] == "code" and "content" in chunk:
                        self.bus.emit(
                            Message(
                                "core.utterance.response",
                                {"content": chunk},
                            )
                        )
                        # self.capabilities.send_to_ui(chunk)

                    if "end" in chunk:
                        LOG.debug("system message: " + sentence)
                        if chunk["type"] == "code":
                            self.bus.emit(
                                Message(
                                    "core.utterance.response",
                                    {
                                        "content": {
                                            "role": "assistant",
                                            "type": "message",
                                            "content": "```",
                                        }
                                    },
                                )
                            )
                        self.bus.emit(
                            Message(
                                "core.utterance.response",
                                {"content": chunk, "done": True},
                            )
                        )

                wait_while_speaking()
                if "?" in system_message:
                    self.bus.emit(Message("core.mic.listen"))

                # NOTE: could there be a better place for this to prevent user
                # utterance appearing twice in persona's llm response prompt
                LLM.chat_memory.add_user_message(utterance)
                LLM.chat_memory.add_ai_message(system_message)
                # self.capabilities.get_response()

            return True
        except Exception as e:
            LOG.error("error in QA response: {}".format(e), exc_info=True)
            return False
