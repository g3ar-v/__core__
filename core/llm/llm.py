# Aim of this module is to create a singular access to llms and ai-kits for core
# processes
import os

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
    def _load_model(model_type: str):  # -> ChatOpenAI | Any:
        # if (
        #     LLM.config.get("llm", {}).get("model_type", {}) == "online"
        #     and connected_to_the_internet()
        # ):
        if model_type.lower() == "online" and connected_to_the_internet():
            return ChatOpenAI(
                temperature=1.0,
                max_tokens=826,
                model="gpt-3.5-turbo-0613",
                streaming=True,
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
        chat_history = ConversationBufferWindowMemory(
            chat_memory=LLM.chat_memory,
            human_prefix=LLM.user_name,
            ai_prefix=LLM.system_name,
            k=8,  # if this is a lot then context window is exceeded
        )
        current_conversation = chat_history.load_memory_variables({})["history"]

        def run_text_llm(prompt, query, current_conversation, context=None):
            inside_code_block = False
            accumulated_block = ""

            today = now_local()
            date_now = today.strftime("%Y-%m-%d %H:%M %p")

            model = LLM._load_model("online")
            gptchain = MyChain(llm=model, verbose=True, prompt=prompt)

            for chunk in gptchain.stream(
                {
                    "query": query,
                    "current_conversation": current_conversation,
                    "date_str": date_now,
                }
            ):
                if chunk.content == "":
                    continue

                # LOG.info(f"Response from LLM: {chunk.content}")

                accumulated_block += chunk.content

                if accumulated_block.endswith("`"):
                    # We might be writing "```" one token at a time.
                    continue

                #  Did we just enter a code block?
                if "```" in accumulated_block and not inside_code_block:
                    inside_code_block = True
                    accumulated_block = accumulated_block.split("```")[1]

                #  Did we just exit a code block?
                if inside_code_block and "```" in accumulated_block:
                    return

                # If we're in a code block,
                if inside_code_block:
                    yield {
                        "role": "assistant",
                        "type": "code",
                        "content": chunk.content,
                    }

                if not inside_code_block:
                    yield {
                        "role": "assistant",
                        "type": "message",
                        "content": chunk.content,
                    }

        try:
            last_flag_base = None
            messages = ""

            for chunk in run_text_llm(prompt, query, current_conversation):
                if chunk["content"] == "":
                    continue

                LOG.debug(f"Chunk: {chunk}")
                # LOG.info(f"last flag base: {last_flag_base}")

                if (
                    last_flag_base
                    and "role" in chunk
                    and "type" in chunk
                    and last_flag_base["role"] == chunk["role"]
                    and last_flag_base["type"] == chunk["type"]
                ):
                    messages += chunk["content"]
                else:
                    # NOTE: this could be the reason for the "double concatenated"
                    # messages being yielded in streaming response
                    # if last_flag_base:
                    #     yield {**last_flag_base, "content": messages}

                    last_flag_base = {"role": chunk["role"], "type": chunk["type"]}
                    yield {**last_flag_base, "start": True}

                # Yield the chunk itself
                yield chunk

            # Yield a final end flag
            if last_flag_base:
                yield {**last_flag_base, "end": True}

        except Exception as e:
            LOG.error("Error occurred during LLM response: {}".format(e), exc_info=True)

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
            )
        except Exception as e:
            LOG.error(f"error in llm response: {e}")

        LOG.info(f"Response from LLM: {response}")
        if send_to_ui:
            payload = {"role": "assistant", "type": "message", "content": response}
            LLM.bus.emit(Message("core.utterance.response", {"content": payload}))
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


class MyChain(LLMChain):
    def stream(
        self,
        input,
        config=None,
        run_manager=None,
        **kwargs,
    ):
        prompts, stop = self.prep_prompts([input], run_manager=run_manager)
        yield from self.llm.stream(input=prompts[0], config=config, **kwargs)
