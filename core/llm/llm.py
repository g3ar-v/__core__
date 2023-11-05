# Aim of this module is to create a singular access to llms and ai-kits for core
# processes
import os
from typing import Any

from langchain.chains import LLMChain
from langchain.chat_models import ChatOpenAI
from langchain.llms import LlamaCpp
from langchain.memory import ConversationBufferWindowMemory, MongoDBChatMessageHistory
from pymongo import MongoClient

from core.configuration import Configuration
from core.util.log import LOG

config = Configuration.get()


class Singleton(type):
    _instances = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class LLM(metaclass=Singleton):
    conn_string = config["microservices"].get("mongo_conn_string")

    def __init__(self):
        os.environ["OPENAI_API_KEY"] = config.get("microservices").get("openai_key")
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
        os.environ["LANGCHAIN_API_KEY"] = config.get("microservices").get(
            "langsmith_key"
        )
        os.environ["LANGCHAIN_PROJECT"] = "jarvis-pa"
        # select LLM for CORE system
        if config.get("llm").get("model_type") == "local":
            self.model = LlamaCpp(
                model_path=config.get("llm").get("local").get("model_dir"),
                n_gpu_layers=1,
                n_batch=512,
                n_ctx=2048,
                f16_kv=True,
                verbose=True,
            )
        else:
            # NOTE: is it possible to access the OpenAI arguments here? to control how
            # tokens are generated for various conversations.
            self.model = ChatOpenAI(
                temperature=0.7,
                max_tokens=85,
                model="gpt-3.5-turbo",
                streaming=False,
            )
        MongoClient(self.conn_string)
        self.message_history = MongoDBChatMessageHistory(
            connection_string=self.conn_string,
            database_name="jarvis",
            session_id="main",
            collection_name="chat_history",
        )
        # TODO: load user from config
        self.chat_history = ConversationBufferWindowMemory(
            memory_key="chat_history",
            chat_memory=self.message_history,
            user_prefix="Victor",
            ai_prefix="Jarvis",
            k=3,
        )
        # self.message_history.clear()

        # self.collection = client[db_name][collection_name]

    def use_llm(self, **kwargs):
        """
        Use the Language Model to generate a response based
        on the given prompt and input.

        Args:
            **kwargs: Keyword arguments for prompt, context, and query.
            NOTE: the prompt template used in the function call
            determines what goes in the predict function
            prompt (PromptTemplate): The prompt template to use
            for generating the response.
            context (str): The context data to use for the language model.
            query (str): The question for llm to generate response

        Returns:
            str: The generated response from the language model.
        """
        prompt = kwargs.get("prompt")
        context = kwargs.get("context")
        query = kwargs.get("query")
        curr_conv = kwargs.get("curr_conv")
        date_str = kwargs.get("date_str")
        rel_mem = kwargs.get("rel_mem")

        gptchain = LLMChain(llm=self.model, verbose=True, prompt=prompt)

        response = gptchain.predict(
            context=context,
            query=query,
            curr_conv=curr_conv,
            rel_mem=rel_mem,
            date_str=date_str,
        )

        LOG.info(f"LLM response: {response}")
        return response
