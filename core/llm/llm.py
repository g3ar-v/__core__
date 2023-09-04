import os
from langchain import LLMChain
from langchain.llms.openai import OpenAI
from langchain.prompts import PromptTemplate
from core.configuration import Configuration
from core.util.log import LOG

model = "gpt-3.5-turbo"


# TODO: Add a query part to the template so the LLM has conext for response
# TODO: use a local llm to produce response
def use_llm(prompt, input):
    """
    Use the Language Model to generate a response based on the given prompt and input.

    Args:
        prompt (PromptTemplate): The prompt template to use for generating the response.
        input (str): The input to provide to the language model.

    Returns:
        str: The generated response from the language model.
    """
    config = Configuration.get()
    os.environ["OPENAI_API_KEY"] = config.get('microservices').get('openai_key')
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
    os.environ["LANGCHAIN_API_KEY"] = config.get('microservices').get('langsmith_key')
    os.environ["LANGCHAIN_PROJECT"] = "jarvis-pa"
    llm = OpenAI(temperature=0.7, max_tokens=100)
    gptchain = LLMChain(llm=llm, verbose=False, prompt=prompt)

    response = gptchain.predict(input=input)
    LOG.info(f"LLM response: {response}")
    return response
