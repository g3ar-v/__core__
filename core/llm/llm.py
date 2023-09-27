# Aim of this module is to create a singular access to llms and ai-kits for core
# processes
import os
from langchain import LLMChain
from langchain.llms.openai import OpenAI
from langchain.memory import MongoDBChatMessageHistory
from core.configuration import Configuration
from core.util.log import LOG
from pymongo import MongoClient

model = "gpt-3.5-turbo"
config = Configuration.get()


class LLM:
    conn_string = config["microservices"].get("mongo_conn_string")

    def __init__(self):
        os.environ["OPENAI_API_KEY"] = config.get("microservices").get("openai_key")
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
        os.environ["LANGCHAIN_API_KEY"] = config.get("microservices").get(
            "langsmith_key"
        )
        os.environ["LANGCHAIN_PROJECT"] = "jarvis-pa"
        self.model = OpenAI(temperature=1, max_tokens=100)
        MongoClient(self.conn_string)
        self.message_history = MongoDBChatMessageHistory(
            connection_string=self.conn_string,
            database_name="jarvis",
            session_id="main",
            collection_name="chat_history",
        )

        # self.collection = client[db_name][collection_name]

    # TODO: use a local llm to produce response

    @staticmethod
    def use_llm(**kwargs):
        """
        Use the Language Model to generate a response based on the given prompt and input.

        Args:
            **kwargs: Keyword arguments for prompt, context, and query.
            NOTE: the prompt template used in the function call determines what goes in the
            predict function
            prompt (PromptTemplate): The prompt template to use for generating the response.
            context (str): The context data to use for the language model.
            query (str): The question for llm to generate response

        Returns:
            str: The generated response from the language model.
        """
        prompt = kwargs.get("prompt")
        context = kwargs.get("context")
        query = kwargs.get("query")

        llm = OpenAI(temperature=1, max_tokens=100)
        gptchain = LLMChain(llm=llm, verbose=True, prompt=prompt)

        response = gptchain.predict(context=context, query=query)
        LOG.info(f"LLM response: {response}")
        return response
