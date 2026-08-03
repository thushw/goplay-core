import re

import anthropic


def _model_sort_key(model_id: str):
    """Sort key that orders models by major/minor version, then date.

    Handles IDs like 'claude-3-haiku-20240307' (minor defaults to 0) and
    'claude-3-5-haiku-20241022'.
    """
    match = re.match(
        r"claude-(\d+)(?:-(\d+))?-[a-z]+-(\d{8})", model_id.lower()
    )
    if not match:
        return (0, 0, 0)
    major = int(match.group(1))
    minor = int(match.group(2)) if match.group(2) else 0
    date = int(match.group(3))
    return (major, minor, date)


def get_active_haiku_model(client: anthropic.Anthropic) -> str:
    """Queries Anthropic API dynamically for the best available low-cost model."""
    try:
        page = client.models.list()
        available_ids = [m.id for m in page.data]
        haiku_models = [m_id for m_id in available_ids if "haiku" in m_id.lower()]

        if haiku_models:
            haiku_models.sort(key=_model_sort_key, reverse=True)
            return haiku_models[0]
            
        return available_ids[0]
    except Exception:
        return "claude-3-haiku-20240307"
