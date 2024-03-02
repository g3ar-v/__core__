# Aim of this module is to create a singular access to llms and ai-kits for core
# processes
import os
from typing import Any

from langchain.chains import LLMChain
from langchain.memory import ChatMessageHistory, ConversationBufferWindowMemory
from langchain_community.llms import Ollama
from langchain_openai import ChatOpenAI

from core.api import SystemApi
from core.configuration import Configuration
from core.messagebus.message import Message, dig_for_message
from core.util.log import LOG
from core.util.network_utils import connected_to_the_internet
from core.util.time import now_local


class LLM:
    """
    The LLM class is a static class that manages the language model for the system.
    It sets up the necessary environment variables, connects to the MongoDB database,
    and initializes the chat history and vector search (relevant memory).

    Attributes:
        bus: The message bus for the system.
        connection_string: The connection string for the MongoDB database.
        message_history: The MongoDBChatMessageHistory object for storing chat history.
        chat_history: The ConversationBufferWindowMemory object for storing recent
        chat history
        vector_search: The MongoDBAtlasVectorSearch object for performing vector
        searches.
    """

    config = Configuration.get()
    bus = None
    api = SystemApi()
    connection_string = config["microservices"].get("mongo_conn_string")
    chat_memory = ChatMessageHistory()
    together_api_key = config.get("microservices").get("together_api_key")
    user_name = config["user_preference"].get("user_name")
    system_name = config["system_name"]

    @staticmethod
    def initialize(bus):
        LLM.bus = bus
        os.environ["OPENAI_API_KEY"] = LLM.config.get("microservices").get("openai_key")
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
        os.environ["LANGCHAIN_API_KEY"] = LLM.config.get("microservices").get(
            "langsmith_key"
        )
        os.environ["LANGCHAIN_PROJECT"] = "jarvis-pa"

    @staticmethod
    def _load_model():  # -> ChatOpenAI | Any:
        if (
            LLM.config.get("llm", {}).get("model_type", {}) == "online"
            and connected_to_the_internet()
        ):
            return ChatOpenAI(
                temperature=1.5,
                max_tokens=1256,
                model="gpt-3.5-turbo-0125",
                streaming=False,
            )
        else:
            return Ollama(model="mistral:7b-instruct")

    @staticmethod
    def clear_chat_history():
        LLM.chat_history.clear()

    @staticmethod
    def set_chat_memory(chat_memory):
        LLM.chat_memory = chat_memory

    @staticmethod
    def chat_with_system(**kwargs):
        """
        Use a Language Model to generate and speak a response based
        on the given prompt and relevant arguments.

        Args:
            **kwargs: Keyword arguments for prompt, context, and query.
        """
        prompt = kwargs.get("prompt")
        context = kwargs.get("context")
        query = kwargs.get("query")
        send_to_ui = kwargs.get("send_to_ui", True)
        parser = kwargs.get("parser")

        relevant_memory = None
        chat_history = ConversationBufferWindowMemory(
            chat_memory=LLM.chat_memory,
            human_prefix=LLM.user_name,
            ai_prefix=LLM.system_name,
            k=4,  # if this is a lot then context window is exceeded
        )
        current_conversation = chat_history.load_memory_variables({})["history"]

        try:
            today = now_local()
            date_now = today.strftime("%Y-%m-%d %H:%M %p")

            model = LLM._load_model()

            gptchain = LLMChain(
                llm=model, verbose=False, prompt=prompt, output_parser=parser
            )

            response = gptchain.predict(
                context=context,
                query=query,
                curr_conv=current_conversation,
                rel_mem=relevant_memory,
                date_str=date_now,
            )
            LOG.info(f"Response from LLM: {response}")

            stt_response = response.get("speech", "Apologies, I can't respond to that")
            chat_response = response.get("chat", stt_response)
            action_response = response.get("action", "")

            if chat_history:
                LLM.chat_memory.add_ai_message(chat_response)

            if send_to_ui:
                try:
                    LLM.api.send_ai_utterance(chat_response)
                except Exception as e:
                    LOG.error(f"couldn't send data: {e}")

            LLM.speak(
                stt_response,
                True if action_response and "listen" in action_response else False,
            )
            return chat_response

        except Exception as e:
            LOG.error("error in llm response: {}".format(e))

    @staticmethod
    def get_llm_response(**kwargs):
        prompt = kwargs.get("prompt", "")
        context = kwargs.get("context", "")
        send_to_ui: bool = kwargs.get("send_to_ui", True)
        speak = kwargs.get("speak", False)

        # USE LOCAL MODEL FOR TITLE GENERATION
        model = LLM._load_model("offline")

        gptchain = LLMChain(llm=model, verbose=False, prompt=prompt)

        try:
            response = gptchain.predict(
                context=context,
                # ge LOG.info("system_message: " + system_message)
            )
        except Exception as e:
            LOG.error(f"error in llm response: {e}")

        LOG.info(f"Response from LLM: {response}")
        if send_to_ui:
            try:
                LLM.api.send_ai_utterance(response)
            except Exception as e:
                LOG.error(f"couldn't send data: {e}")
        if speak:
            LLM._speak(response)
        return response

    @staticmethod
    def _speak(utterance, expect_response=False, message=None):
        """Speak a sentence.

        Args:
            utterance (str): sentence system should speak
        """

        message = message or dig_for_message()
        data = {
            "utterance": utterance,
            "expect_response": expect_response,
        }

        m = Message("speak", data)
        LLM.bus.emit(m)
