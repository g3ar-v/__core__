from langchain_core.output_parsers import JsonOutputParser
from langchain_core.pydantic_v1 import BaseModel, Field


class LLMResponse(BaseModel):
    chat: str = Field(
        description="denotes what is displayed on the chat interface.\
                it should be similar to speech."
    )
    speech: str = Field(
        description="represents what Vasco verbally communicates to the user."
    )
    action: str = Field(
        description="""if Vasco asks a question or if vasco makes
                                a remark that would need a reply, action is "listen" 
                                else if it's just statement it should be "None"."""
    )


parser = JsonOutputParser(pydantic_object=LLMResponse)
