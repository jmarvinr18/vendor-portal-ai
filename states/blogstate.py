from typing import TypedDict
from pydantic import BaseModel, Field, ConfigDict


class Blog(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "type": "object",
            "required": ["title", "content"]
        }
    )

    title: str = Field(..., description="Title of the blog")
    content: str = Field(..., description="Content of the blog")


class BlogState(TypedDict):
    topic: str
    blog: Blog
    current_language: str



