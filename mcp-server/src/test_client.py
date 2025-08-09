import asyncio
import json
from fastmcp import Client
from main import mcp
from pydantic import BaseModel, AnyUrl


def json_serializer(obj):
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, AnyUrl):
        return str(obj) 
    return json.dumps(obj, indent=4)

client = Client(mcp)

async def main():
    async with client:
        await client.ping()
        
        tools = await client.list_tools()
        resources = await client.list_resources()
        resource_templates = await client.list_resource_templates()
        prompts = await client.list_prompts()
        
        with open("tools.json", "w") as f:
            json.dump(tools, f, indent=4, default=json_serializer)
        with open("resources.json", "w") as f:
            json.dump(resources, f, indent=4, default=json_serializer)
        with open("prompts.json", "w") as f:
            json.dump(prompts, f, indent=4, default=json_serializer)
        with open("resource_templates.json", "w") as f:
            json.dump(resource_templates, f, indent=4, default=json_serializer)

asyncio.run(main())