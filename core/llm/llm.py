# Aim of this module is to create a singular access to llms and ai-kits for core
# processes
import os
from typing import Any
from uuid import UUID

from langchain.callbacks.base import BaseCallbackHandler
from langchain.chains import LLMChain
from langchain.chat_models import ChatOpenAI
from langchain.llms import LlamaCpp
from langchain.memory import ConversationBufferWindowMemory, MongoDBChatMessageHistory
from langchain.schema.output import LLMResult
from pymongo import MongoClient

from core.configuration import Configuration
from core.messagebus.message import Message, dig_for_message
from core.util.log import LOG

config = Configuration.get()


class Singleton(type):
    _instances = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


# TODO: handle listen if response has a question
# NOTE: should this Class handle speech
class CustomCallback(BaseCallbackHandler):
    """
    Custom callback handler for LLM token and response events.
    """

    def __init__(self, bus, interrupted) -> None:
        # self.outputs = outputs
        self.buffer = ""
        self.bus = bus
        self.interrupted = interrupted
        self.completed = False

    #     self.bus.on("core.speech.interruption", self.handle_interruption)

    # def handle_interruption(self):
    #     self.interrupted = True
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
            LOG.info(f"returning string: {self.buffer}")
            if not self.interrupted:
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
class LLM(metaclass=Singleton):
    conn_string = config["microservices"].get("mongo_conn_string")

    def __init__(self, bus):
        self.bus = bus
        os.environ["OPENAI_API_KEY"] = config.get("microservices").get("openai_key")
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
        os.environ["LANGCHAIN_API_KEY"] = config.get("microservices").get(
            "langsmith_key"
        )
        os.environ["LANGCHAIN_PROJECT"] = "jarvis-pa"

        MongoClient(self.conn_string)
        try:
            self.message_history = MongoDBChatMessageHistory(
                connection_string=self.conn_string,
                database_name="jarvis",
                session_id="main",
                collection_name="chat_history",
            )
        except Exception as e:
            LOG.error(f"Error connecting to MongoDB: {e}")
            self.message_history = None
        # TODO: load user from config
        self.chat_history = ConversationBufferWindowMemory(
            memory_key="chat_history",
            chat_memory=self.message_history,
            user_prefix="user",
            ai_prefix="assistant",
            k=3,
        )

    def llm_response(self, **kwargs):
        """
        Use the Language Model to generate and speak a response based
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
        """
        prompt = kwargs.get("prompt")
        context = kwargs.get("context")
        query = kwargs.get("query")
        curr_conv = kwargs.get("curr_conv")
        date_str = kwargs.get("date_str")
        rel_mem = kwargs.get("rel_mem")

        # TODO: make this function stream and not stream output
        if config.get("llm", {}).get("model_type", {}) == "online":
            model = ChatOpenAI(
                temperature=0.7,
                max_tokens=128,
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

        try:
            gptchain = LLMChain(llm=model, verbose=True, prompt=prompt)

            gptchain.predict(
                context=context,
                query=query,
                curr_conv=curr_conv,
                rel_mem=rel_mem,
                date_str=date_str,
            )
        except Exception as e:
            LOG.error("error in llm response: {}".format(e))
