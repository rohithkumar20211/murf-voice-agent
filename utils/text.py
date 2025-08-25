import re
from typing import Any, Dict, List
from personas import get_persona_system_prompt, is_greeting, get_persona_greeting


def chunk_text(text: str, limit: int = 3000) -> List[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text]
    sentences = re.split(r"(?<=[\.\!\?])\s+", text)
    chunks: List[str] = []
    current = ""
    for sent in sentences:
        if not current:
            current = sent
        elif len(current) + 1 + len(sent) <= limit:
            current += " " + sent
        else:
            chunks.append(current)
            current = sent
    if current:
        chunks.append(current)
    final: List[str] = []
    for ch in chunks:
        if len(ch) <= limit:
            final.append(ch)
        else:
            for i in range(0, len(ch), limit):
                final.append(ch[i : i + limit])
    return final


def build_prompt_from_history(history: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    
    # Use the ArcNova persona system prompt
    system_preamble = get_persona_system_prompt()
    lines.append(f"System: {system_preamble}")
    
    # Check if this is the first message and it's a greeting
    if len(history) == 1:
        first_msg = history[0]
        if first_msg.get("role") == "user":
            user_content = str(first_msg.get("content", "")).strip()
            if is_greeting(user_content):
                # Return the persona greeting for greetings
                lines.append(f"User: {user_content}")
                lines.append(f"Assistant: {get_persona_greeting()}")
                return "\n".join(lines)
    
    # Build normal conversation history
    for msg in history:
        role = msg.get("role", "user")
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        prefix = "User" if role == "user" else "Assistant"
        lines.append(f"{prefix}: {content}")
    lines.append("Assistant:")
    return "\n".join(lines)

