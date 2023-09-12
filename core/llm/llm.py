# Aim of this module is to create a singular access to llms in core
import os
from langchain import LLMChain
from langchain.llms.openai import OpenAI
from core.configuration import Configuration
from core.util.log import LOG

model = "gpt-3.5-turbo"


# TODO: Add a query part to the template so the LLM has conext for response
# TODO: use a local llm to produce response
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
    config = Configuration.get()
    os.environ["OPENAI_API_KEY"] = config.get("microservices").get("openai_key")
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
    os.environ["LANGCHAIN_API_KEY"] = config.get("microservices").get("langsmith_key")
    os.environ["LANGCHAIN_PROJECT"] = "jarvis-pa"
    llm = OpenAI(temperature=1, max_tokens=100)
    gptchain = LLMChain(llm=llm, verbose=True, prompt=prompt)

    response = gptchain.predict(context=context, query=query)
    LOG.info(f"LLM response: {response}")
    return response
