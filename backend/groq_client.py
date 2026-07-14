from dotenv import load_dotenv
from groq import Groq
import os
from typing import List

load_dotenv()   # <-- this line is important

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
def groq_chat(prompt: str, model: str | None = None, system: str | None = None) -> str:
    """Send a chat completion request to Groq and return the assistant's reply.

    Args:
        prompt: User message
        model: Optional override of the model name (defaults to GROQ_MODEL env or a maintained default)
        system: Optional system prompt for steering responses
    """
    # Pick model from env or fall back to a maintained default
    model = model or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=512,
    )
    return response.choices[0].message.content.strip()


def groq_embed(texts: List[str], model: str | None = None) -> list[list[float]]:
    """Create embeddings for a list of texts. Requires a valid GROQ embedding model.
    Falls back to an empty list on error.
    """
    try:
        model = model or os.getenv("GROQ_EMBED_MODEL", "text-embedding-3-small")
        resp = client.embeddings.create(model=model, input=texts)
        # openai-like shape
        if hasattr(resp, "data"):
            return [d.embedding for d in resp.data]
        return []
    except Exception:
        return []
