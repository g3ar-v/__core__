from langchain_core.output_parsers import JsonOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field


class LLMResponse(BaseModel):
    speech: str = Field(
        description="represents what Vasco verbally communicates to the user."
    )
    chat: str = Field(
        description="""represents what Vasco visually communicates to the user. It
        should be similar if not thesame to the speech response in its underlying intent
        just highly detailed in content when necessary"""
    )
    action: str = Field(
        description="""if Vasco asks a question or if Vasco makes a remark that would
        need a reply, action is "listen" else if it's just a statement it should be
        "None"."""
    )


parser = JsonOutputParser(pydantic_object=LLMResponse)
