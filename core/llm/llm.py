# Aim of this module is to create a singular access to llms and ai-kits for core
# processes
import os
import re
from typing import Any
from uuid import UUID

from langchain.callbacks.base import BaseCallbackHandler
from langchain.chains import LLMChain
from langchain.chat_models import ChatOpenAI
from langchain.embeddings import OpenAIEmbeddings

# from langchain_community.llms import LlamaCpp
from langchain_community.llms import Ollama

from langchain.memory import ConversationBufferWindowMemory, MongoDBChatMessageHistory
from langchain.schema.output import LLMResult
from langchain.vectorstores import MongoDBAtlasVectorSearch
from pymongo import MongoClient
from core.api import SystemApi
from core.configuration import Configuration
from core.messagebus.message import Message, dig_for_message
from core.util.log import LOG
from core.util.time import now_local
from core.util.network_utils import is_connected

config = Configuration.get()


class Singleton(type):
    _instances = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class LLM(metaclass=Singleton):
    """
    The LLM class is a singleton that manages the language model for the system.
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

    def __init__(self, bus):
        self.bus = bus
        self.api = SystemApi()
        self.connection_string = config["microservices"].get("mongo_conn_string")
        os.environ["OPENAI_API_KEY"] = config.get("microservices").get("openai_key")
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
        os.environ["LANGCHAIN_API_KEY"] = config.get("microservices").get(
            "langsmith_key"
        )
        os.environ["LANGCHAIN_PROJECT"] = "jarvis-pa"

        try:
            # TODO: backup when online mongodb fails
            MongoClient(self.connection_string)

            self.message_history = MongoDBChatMessageHistory(
                connection_string=self.connection_string,
                database_name="jarvis",
                session_id="main",
                collection_name="chat_history",
            )
        except Exception as e:
            LOG.error(f"Error connecting to MongoDB: {e}")
            self.message_history = None

        user_name = config["user_preference"].get("user_name")
        system_name = config["system_name"]
        if self.message_history:
            self.chat_history = ConversationBufferWindowMemory(
                # for controlling the conversation length used for RAG
                memory_key="chat_history",
                chat_memory=self.message_history,
                human_prefix=user_name,
                ai_prefix=system_name,
                k=3,  # if this is a lot then context window is exceeded
            )
            # self.message_history.clear()
            # self.chat_history.clear()

            # create vectorstore access
            self.vector_search = MongoDBAtlasVectorSearch.from_connection_string(
                self.connection_string,
                "jarvis.chat_history",
                OpenAIEmbeddings(disallowed_special=()),
                index_name="default",
            )
        else:
            self.chat_history = ConversationBufferWindowMemory(
                memory_key="chat_history",
                human_prefix=user_name,
                ai_prefix=system_name,
                k=3,  # if this is a lot then context window is exceeded
            )

    def set_model(self):
        if config.get("llm", {}).get("model_type", {}) == "online" and is_connected():
            self.model = ChatOpenAI(
                temperature=1,
                max_tokens=256,
                model="gpt-3.5-turbo",
                streaming=False,
            )
        else:
            # model_name = config.get("llm", {}).get("model_type", {})
            self.model = Ollama(model="mistral:7b-instruct")

    def llm_response(self, **kwargs):
        """
        Use a Language Model to generate and speak a response based
        on the given prompt and input.

        Args:
            **kwargs: Keyword arguments for prompt, context, and query.
            NOTE: the prompt template used in the function call
            determines what goes in the predict function
            prompt (PromptTemplate): The prompt template to use
            for generating the response.
            context (str): The context data to use for the language model.
            query (str): The question for llm to generate response
            curr_conv (str): chat history
            date_str (str): the time of getting the response


        Returns:
            str: The generated response from the language model.
            stream: returns tokens
        """
        prompt = kwargs.get("prompt")
        context = kwargs.get("context")
        query = kwargs.get("query")

        relevant_memory = None
        current_conversation = self.chat_history.load_memory_variables({})[
            "chat_history"
        ]
        # NOTE: a use case for using the function without a query

        # try:
        #     if query:
        #         documents = self.vector_search.similarity_search(query, k=2)
        #         relevant_memory = documents[0].page_content
        # except Exception as e:
        #     LOG.info("relvant memory error: {}".format(e))
        #     relevant_memory = None

        try:
            today = now_local()
            date_now = today.strftime("%Y-%m-%d %H:%M %p")

            self.set_model()
            gptchain = LLMChain(llm=self.model, verbose=True, prompt=prompt)

            response = gptchain.predict(
                context=context,
                query=query,
                curr_conv=current_conversation,
                rel_mem=relevant_memory,
                date_str=date_now,
            )
            # monkey patch llm response
            response = re.sub(
                r"(Vasco:|vasco:)",
                "",
                response,
            )

            if self.message_history:
                self.message_history.add_ai_message(response)

            self.api.send_ai_utterance(response)
            return response

        except Exception as e:
            LOG.error("error in llm response: {}".format(e))


# TODO: handle listen if response has a question
# NOTE: how can I handle listen when it is needed?
class CustomCallback(BaseCallbackHandler):
    """
    Custom callback handler for LLM token and response events.
    """

    def __init__(self, bus) -> None:
        # self.outputs = outputs
        self.buffer = ""
        self.bus = bus
        self.interrupted = False
        self.completed = False
        self.bus.on("llm.speech.interruption", self.handle_interruption)

    def handle_interruption(self, message):
        self.interrupted = True

    #     self.bus.emit("core.audio.speech.stop")

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
        if token in ["\n", ".", "?", "!"]:  # if token is a newline or a full-stop
            # LOG.info(f"returning string: {self.buffer}")
            if not self.interrupted:
                # remove llm prefixes from response token
                # NOTE: affects responses with bullet points
                if ":" in self.buffer:
                    LOG.info("removing `:` in llm response")
                    self.buffer = re.sub(
                        r"(Vasco|vasco:)",
                        "",
                        self.buffer,
                    )
                self.speak(self.buffer)
            else:
                LOG.info("not speaking because speech has been interrupted")
            self.buffer = ""  # reset the buffer

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        # wait_while_speaking()
        # self.bus.emit(Message("core.mic.listen"))
        self.interrupted = False

    def speak(self, utterance, expect_response=False, message=None):
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
        self.bus.emit(m)

    # TODO: handle interruption while language model is streaming
