"""Morph LLM tool for applying code edits."""

import httpx
from langchain_core.tools import tool


@tool
async def morph_apply_edit(
    file_content: str,
    edit_instructions: str,
    morph_api_key: str
) -> str:
    """Apply code edits using Morph LLM.
    
    Args:
        file_content: The original code content to edit
        edit_instructions: Instructions for what changes to make
        morph_api_key: API key for Morph LLM
        
    Returns:
        The edited code content
    """
    if not morph_api_key:
        raise ValueError("Morph API key is required")
    
    # Format the message using Morph's required XML format
    message_content = f"""<instruction>{edit_instructions}</instruction>
<code>{file_content}</code>
<update>Apply the changes as instructed</update>"""
    
    payload = {
        "model": "morph-v3-large",
        "messages": [
            {
                "role": "user",
                "content": message_content
            }
        ],
        "stream": False
    }
    
    headers = {
        "Authorization": f"Bearer {morph_api_key}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.morphllm.com/v1/chat/completions",
            json=payload,
            headers=headers
        )
        
        if response.status_code != 200:
            raise Exception(f"Morph API failed: {response.status_code} - {response.text}")
        
        result = response.json()
        
        # Extract the edited code from the response
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        else:
            raise Exception("No edited code returned from Morph API")