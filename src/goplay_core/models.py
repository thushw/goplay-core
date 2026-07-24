import anthropic

def get_active_haiku_model(client: anthropic.Anthropic) -> str:
    """Queries Anthropic API dynamically for the best available low-cost model."""
    try:
        page = client.models.list()
        available_ids = [m.id for m in page.data]
        haiku_models = [m_id for m_id in available_ids if "haiku" in m_id.lower()]

        if haiku_models:
            haiku_models.sort(reverse=True)
            return haiku_models[0]
            
        return available_ids[0]
    except Exception:
        return "claude-3-haiku-20240307"
