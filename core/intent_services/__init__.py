"""Intent service, providing intent parsing since forever!"""
import time
from collections import namedtuple
from copy import copy

from core.audio import wait_while_speaking
from core.configuration import Configuration, set_default_lf_lang
from core.dialog import dialog
from core.llm import LLM
from core.messagebus.message import Message
from core.util import flatten_list
from core.util.intent_service_interface import IntentQueryApi, open_intent_envelope
from core.util.log import LOG
from core.util.metrics import Stopwatch
from core.util.parse import normalize

from .adapt_service import AdaptIntent, AdaptService  # noqa: F401
from .fallback_service import FallbackService
from .padatious_service import PadatiousMatcher, PadatiousService
from .qa_service import QAService

# Intent match response tuple containing
# intent_service: Name of the service that matched the intent
# intent_type: intent name (used to call intent handler over the message bus)
# intent_data: data provided by the intent match
# skill_id: the skill this handler belongs to
IntentMatch = namedtuple(
    "IntentMatch", ["intent_service", "intent_type", "intent_data", "skill_id"]
)


def _get_message_lang(message):
    """Get the language from the message or the default language.

    Args:
        message: message to check for language code.

    Returns:
        The languge code from the message or the default language.
    """
    default_lang = Configuration.get().get("lang", "en-us")
    return message.data.get("lang", default_lang).lower()


def _normalize_all_utterances(utterances):
    """Create normalized versions and pair them with the original utterance.

    This will create a list of tuples with the original utterance as the
    first item and if normalizing changes the utterance the normalized version
    will be set as the second item in the tuple, if normalization doesn't
    change anything the tuple will only have the "raw" original utterance.

    Args:
        utterances (list): list of utterances to normalize

    Returns:
        list of tuples, [(original utterance, normalized) ... ]
    """
    # normalize() changes "it's a boy" to "it is a boy", etc.
    norm_utterances = [normalize(u.lower(), remove_articles=False) for u in utterances]

    # Create pairs of original and normalized counterparts for each entry
    # in the input list.
    combined = []
    for utt, norm in zip(utterances, norm_utterances):
        if utt == norm:
            combined.append((utt,))
        else:
            combined.append((utt, norm))

    LOG.debug("Utterances: {}".format(combined))
    return combined


class IntentService:
    """Intent service. parses utterances using a variety of systems.

    The intent service also provides the internal API for registering and
    querying the intent service.
    """

    def __init__(self, bus):
        # Dictionary for translating a skill id to a name
        self.bus = bus
        self.llm = LLM(bus)

        self.intent_api = IntentQueryApi()
        self.skill_names = {}
        config = Configuration.get()
        self.adapt_service = AdaptService(config.get("context", {}))
        try:
            self.padatious_service = PadatiousService(bus, config["padatious"])
        except Exception as err:
            LOG.exception(
                "Failed to create padatious handlers " "({})".format(repr(err))
            )
        self.persona = QAService(bus)
        self.fallback = FallbackService(bus)

        self.bus.on("register_vocab", self.handle_register_vocab)
        self.bus.on("register_intent", self.handle_register_intent)
        self.bus.on("recognizer_loop:utterance", self.handle_utterance)
        self.bus.on("detach_intent", self.handle_detach_intent)
        self.bus.on("detach_skill", self.handle_detach_skill)
        # Context related handlers
        self.bus.on("add_context", self.handle_add_context)
        self.bus.on("remove_context", self.handle_remove_context)
        self.bus.on("clear_context", self.handle_clear_context)

        # Converse method
        self.bus.on("core.speech.recognition.unknown", self.reset_converse)
        self.bus.on("core.skills.loaded", self.update_skill_name_dict)
        self.bus.on("intent.service.response.latency", self.handle_response_latency)

        def add_active_skill_handler(message):
            skill_id = message.data["skill_id"]
            self.add_active_skill(skill_id)
            LOG.debug("Adding active skill: " + skill_id)

        def remove_active_skill_handler(message):
            skill_id = message.data["skill_id"]
            self.remove_active_skill(skill_id)
            LOG.debug("Removing active skill: " + skill_id)

        self.bus.on("active_skill_request", add_active_skill_handler)
        self.bus.on("remove_active_skill", remove_active_skill_handler)

        self.active_skills = []  # [skill_id , timestamp]
        # HACK: set to 0.5 for qa to not loop for a long time and let padatious handle
        # intent
        self.converse_timeout = 5  # minutes to prune active_skills

        # Intents API
        self.registered_vocab = []
        self.bus.on("intent.service.intent.get", self.handle_get_intent)
        self.bus.on("intent.service.skills.get", self.handle_get_skills)
        self.bus.on("intent.service.active_skills.get", self.handle_get_active_skills)
        self.bus.on("intent.service.adapt.get", self.handle_get_adapt)
        self.bus.on("intent.service.adapt.manifest.get", self.handle_adapt_manifest)
        self.bus.on(
            "intent.service.adapt.vocab.manifest.get", self.handle_vocab_manifest
        )
        self.bus.on("intent.service.padatious.get", self.handle_get_padatious)
        self.bus.on(
            "intent.service.padatious.manifest.get", self.handle_padatious_manifest
        )
        self.bus.on(
            "intent.service.padatious.entities.manifest.get",
            self.handle_entity_manifest,
        )

    @property
    def registered_intents(self):
        return [parser.__dict__ for parser in self.adapt_service.engine.intent_parsers]

    def handle_response_latency(self, event):
        """Core is taking too long to process information"""
        LOG.info("Info taking too long")
        data = {"utterance": dialog.get("taking_too_long")}
        context = {"client_name": "intent_service", "source": "audio"}
        self.bus.emit(Message("speak", data, context))
        wait_while_speaking()

    def update_skill_name_dict(self, message):
        """Messagebus handler, updates dict of id to skill name conversions."""
        self.skill_names[message.data["id"]] = message.data["name"]

    def get_skill_name(self, skill_id):
        """Get skill name from skill ID.

        Args:
            skill_id: a skill id as encoded in Intent handlers.

        Returns:
            (str) Skill name or the skill id if the skill wasn't found
        """
        return self.skill_names.get(skill_id, skill_id)

    def reset_converse(self, message):
        """Let skills know there was a problem with speech recognition"""
        lang = _get_message_lang(message)
        set_default_lf_lang(lang)
        for skill in copy(self.active_skills):
            self.do_converse(None, skill[0], lang, message)

    def do_converse(self, utterances, skill_id, lang, message):
        """Call skill and ask if they want to process the utterance.

        Args:
            utterances (list of tuples): utterances paired with normalized
                                         versions.
            skill_id: skill to query.
            lang (str): current language
            message (Message): message containing interaction info.
        """
        converse_msg = message.reply(
            "skill.converse.request",
            {"skill_id": skill_id, "utterances": utterances, "lang": lang},
        )
        result = self.bus.wait_for_response(converse_msg, "skill.converse.response")
        if result and "error" in result.data:
            self.handle_converse_error(result)
            ret = False
        elif result is not None:
            ret = result.data.get("result", False)
        else:
            ret = False
        return ret

    def handle_converse_error(self, message):
        """Handle error in converse system.

        Args:
            message (Message): info about the error.
        """
        skill_id = message.data["skill_id"]
        error_msg = message.data["error"]
        LOG.error("{}: {}".format(skill_id, error_msg))
        if message.data["error"] == "skill id does not exist":
            self.remove_active_skill(skill_id)

    def remove_active_skill(self, skill_id):
        """Remove a skill from being targetable by converse.

        Args:
            skill_id (str): skill to remove
        """
        for skill in self.active_skills:
            if skill[0] == skill_id:
                self.active_skills.remove(skill)

    def add_active_skill(self, skill_id):
        """Add a skill or update the position of an active skill.

        The skill is added to the front of the list, if it's already in the
        list it's removed so there is only a single entry of it.

        Args:
            skill_id (str): identifier of skill to be added.
        """
        # search the list for an existing entry that already contains it
        # and remove that reference
        if skill_id != "":
            self.remove_active_skill(skill_id)
            # add skill with timestamp to start of skill_list
            self.active_skills.insert(0, [skill_id, time.time()])
        else:
            LOG.warning("Skill ID was empty, won't add to list of " "active skills.")

    def handle_utterance(self, message):
        """Main entrypoint for handling user utterances

        Monitor the messagebus for 'recognizer_loop:utterance', typically
        generated by a spoken interaction but potentially also from a CLI
        or other method of injecting a 'user utterance' into the system.

        Utterances then work through this sequence to be handled:
        1) Active skills attempt to handle using converse()
        2) Padatious high match intents (conf > 0.95)
        3) Adapt intent handlers
        4) Question and Answer Services
        5) High Priority Fallbacks
        6) Padatious near match intents (conf > 0.8)
        7) General Fallbacks
        8) Padatious loose match intents (conf > 0.5)
        9) Catch all fallbacks including Unknown intent handler

        If all these fail the complete_intent_failure message will be sent
        and a generic info of the failure will be spoken.

        Args:
            message (Message): The messagebus data
        """
        try:
            lang = _get_message_lang(message)
            set_default_lf_lang(lang)

            utterances = message.data.get("utterances", [])
            combined = _normalize_all_utterances(utterances)
            # NOTE: ideally where user_message is to be sent to DB, but due to unrefined
            # form of the utternace, should all utterances be sent to database?

            stopwatch = Stopwatch()

            # Create matchers
            padatious_matcher = PadatiousMatcher(self.padatious_service)

            # List of functions to use to match the utterance with intent.
            # These are listed in priority order.
            match_funcs = [
                self._converse,
                padatious_matcher.match_high,
                self.adapt_service.match_intent,
                self.persona.match,
                self.fallback.high_prio,
                padatious_matcher.match_medium,
                self.fallback.medium_prio,
                padatious_matcher.match_low,
                self.fallback.low_prio,
            ]

            match = None
            with stopwatch:
                # Loop through the matching functions until a match is found.
                for match_func in match_funcs:
                    match = match_func(combined, lang, message)
                    if match:
                        break
            if match:
                if match.skill_id:
                    self.add_active_skill(match.skill_id)
                    # If the service didn't report back the skill_id it
                    # takes on the responsibility of making the skill "active"

                # Launch skill if not handled by the match function
                if match.intent_type:
                    reply = message.reply(match.intent_type, match.intent_data)
                    # Add back original list of utterances for intent handlers
                    # match.intent_data only includes the utterance with the
                    # highest confidence.
                    reply.data["utterances"] = utterances
                    self.bus.emit(reply)
                # NOTE: should prevent user utterance from already being in chat_history
                if self.llm.message_history:
                    self.llm.message_history.add_user_message(flatten_list(combined)[0])
            else:
                # Nothing was able to handle the intent
                # Ask politely for forgiveness for failing in this vital task
                self.send_complete_intent_failure(message)
        except Exception as err:
            LOG.exception(err)

    def _converse(self, utterances, lang, message):
        """Give active skills a chance at the utterance

        Args:
            utterances (list):  list of utterances
            lang (string):      4 letter ISO language code
            message (Message):  message to use to generate reply

        Returns:
            IntentMatch if handled otherwise None.
        """
        utterances = [item for tup in utterances for item in tup]
        # check for conversation time-out
        self.active_skills = [
            skill
            for skill in self.active_skills
            if time.time() - skill[1] <= self.converse_timeout * 60
        ]
        LOG.debug(
            f"skills to handle conversation: {self.intent_api.get_active_skills()}"
        )

        # check if any skill wants to handle utterance
        for skill in copy(self.active_skills):
            if self.do_converse(utterances, skill[0], lang, message):
                # update timestamp, or there will be a timeout where
                # intent stops conversing whether its being used or not
                return IntentMatch("Converse", None, None, skill[0])
        return None

    def send_complete_intent_failure(self, message):
        """Send a message that no skill could handle the utterance.

        Args:
            message (Message): original message to forward from
        """
        self.bus.emit(message.forward("complete_intent_failure"))

    def handle_register_vocab(self, message):
        """Register adapt vocabulary.

        Args:
            message (Message): message containing vocab info
        """
        # TODO: 22.02 Remove backwards compatibility
        if _is_old_style_keyword_message(message):
            LOG.warning(
                "Deprecated: Registering keywords with old message. "
                "This will be removed in v22.02."
            )
            _update_keyword_message(message)

        entity_value = message.data.get("entity_value")
        entity_type = message.data.get("entity_type")
        regex_str = message.data.get("regex")
        alias_of = message.data.get("alias_of")
        self.adapt_service.register_vocabulary(
            entity_value, entity_type, alias_of, regex_str
        )
        self.registered_vocab.append(message.data)

    def handle_register_intent(self, message):
        """Register adapt intent.

        Args:
            message (Message): message containing intent info
        """
        intent = open_intent_envelope(message)
        self.adapt_service.register_intent(intent)

    def handle_detach_intent(self, message):
        """Remover adapt intent.

        Args:
            message (Message): message containing intent info
        """
        intent_name = message.data.get("intent_name")
        self.adapt_service.detach_intent(intent_name)

    def handle_detach_skill(self, message):
        """Remove all intents registered for a specific skill.

        Args:
            message (Message): message containing intent info
        """
        skill_id = message.data.get("skill_id")
        self.adapt_service.detach_skill(skill_id)

    def handle_add_context(self, message):
        """Add context

        Args:
            message: data contains the 'context' item to add
                     optionally can include 'word' to be injected as
                     an alias for the context item.
        """
        entity = {"confidence": 1.0}
        context = message.data.get("context")
        word = message.data.get("word") or ""
        origin = message.data.get("origin") or ""
        # if not a string type try creating a string from it
        if not isinstance(word, str):
            word = str(word)
        entity["data"] = [(word, context)]
        entity["match"] = word
        entity["key"] = word
        entity["origin"] = origin
        self.adapt_service.context_manager.inject_context(entity)

    def handle_remove_context(self, message):
        """Remove specific context

        Args:
            message: data contains the 'context' item to remove
        """
        context = message.data.get("context")
        if context:
            self.adapt_service.context_manager.remove_context(context)

    def handle_clear_context(self, _):
        """Clears all keywords from context"""
        self.adapt_service.context_manager.clear_context()

    def handle_get_intent(self, message):
        """Get intent from either adapt or padatious.

        Args:
            message (Message): message containing utterance
        """
        utterance = message.data["utterance"]
        lang = message.data.get("lang", "en-us")
        combined = _normalize_all_utterances([utterance])

        # Create matchers
        padatious_matcher = PadatiousMatcher(self.padatious_service)

        # List of functions to use to match the utterance with intent.
        # These are listed in priority order.
        # TODO once we have a mechanism for checking if a fallback will
        #  trigger without actually triggering it, those should be added here
        match_funcs = [
            padatious_matcher.match_high,
            self.adapt_service.match_intent,
            # self.fallback.high_prio,
            padatious_matcher.match_medium,
            # self.fallback.medium_prio,
            padatious_matcher.match_low,
            # self.fallback.low_prio
        ]
        # Loop through the matching functions until a match is found.
        for match_func in match_funcs:
            match = match_func(combined, lang, message)
            if match:
                if match.intent_type:
                    intent_data = match.intent_data
                    intent_data["intent_name"] = match.intent_type
                    intent_data["intent_service"] = match.intent_service
                    intent_data["skill_id"] = match.skill_id
                    intent_data["handler"] = match_func.__name__
                    self.bus.emit(
                        message.reply(
                            "intent.service.intent.reply", {"intent": intent_data}
                        )
                    )
                return

        # signal intent failure
        self.bus.emit(message.reply("intent.service.intent.reply", {"intent": None}))

    def handle_get_skills(self, message):
        """Send registered skills to caller.

        Argument:
            message: query message to reply to.
        """
        self.bus.emit(
            message.reply("intent.service.skills.reply", {"skills": self.skill_names})
        )

    def handle_get_active_skills(self, message):
        """Send active skills to caller.

        Argument:
            message: query message to reply to.
        """
        self.bus.emit(
            message.reply(
                "intent.service.active_skills.reply", {"skills": self.active_skills}
            )
        )

    def handle_get_adapt(self, message):
        """handler getting the adapt response for an utterance.

        Args:
            message (Message): message containing utterance
        """
        utterance = message.data["utterance"]
        lang = message.data.get("lang", "en-us")
        combined = _normalize_all_utterances([utterance])
        intent = self.adapt_service.match_intent(combined, lang)
        intent_data = intent.intent_data if intent else None
        self.bus.emit(
            message.reply("intent.service.adapt.reply", {"intent": intent_data})
        )

    def handle_adapt_manifest(self, message):
        """Send adapt intent manifest to caller.

        Argument:
            message: query message to reply to.
        """
        self.bus.emit(
            message.reply(
                "intent.service.adapt.manifest", {"intents": self.registered_intents}
            )
        )

    def handle_vocab_manifest(self, message):
        """Send adapt vocabulary manifest to caller.

        Argument:
            message: query message to reply to.
        """
        self.bus.emit(
            message.reply(
                "intent.service.adapt.vocab.manifest", {"vocab": self.registered_vocab}
            )
        )

    def handle_get_padatious(self, message):
        """messagebus handler for perfoming padatious parsing.

        Args:
            message (Message): message triggering the method
        """
        utterance = message.data["utterance"]
        norm = message.data.get("norm_utt", utterance)
        intent = self.padatious_service.calc_intent(utterance)
        if not intent and norm != utterance:
            intent = self.padatious_service.calc_intent(norm)
        if intent:
            intent = intent.__dict__
        self.bus.emit(
            message.reply("intent.service.padatious.reply", {"intent": intent})
        )

    def handle_padatious_manifest(self, message):
        """Messagebus handler returning the registered padatious intents.

        Args:
            message (Message): message triggering the method
        """
        self.bus.emit(
            message.reply(
                "intent.service.padatious.manifest",
                {"intents": self.padatious_service.registered_intents},
            )
        )

    def handle_entity_manifest(self, message):
        """Messagebus handler returning the registered padatious entities.

        Args:
            message (Message): message triggering the method
        """
        self.bus.emit(
            message.reply(
                "intent.service.padatious.entities.manifest",
                {"entities": self.padatious_service.registered_entities},
            )
        )


def _is_old_style_keyword_message(message):
    """Simple check that the message is not using the updated format.

    TODO: Remove in v22.02

    Args:
        message (Message): Message object to check

    Returns:
        (bool) True if this is an old messagem, else False"""
    return "entity_value" not in message.data and "start" in message.data


def _update_keyword_message(message):
    """Make old style keyword registration message compatible.

    Copies old keys in message data to new names.

    Args:
        message (Message): Message to update
    """
    message.data["entity_value"] = message.data["start"]
    message.data["entity_type"] = message.data["end"]
