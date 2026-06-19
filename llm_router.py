import json, os, requests, sys
CONFIG_FILE = "config.json"
def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)
CONFIG = load_config()
def enforce_privacy():
    if CONFIG['privacy']['data_residency'] == 'local' and CONFIG['llm']['provider'] != 'ollama':
        raise SystemExit("Privacy Error: data_residency='local' but provider is not Ollama.")
def ask_llm(prompt_text):
    enforce_privacy()
    resp = requests.post(f"{CONFIG['llm']['api_base']}/api/generate", 
                         json={'model': CONFIG['llm']['model'], 'prompt': prompt_text, 'stream': False})
    return resp.json()['response']
import logging

logger = logging.getLogger("phoenixforge.llm_router")

def ask_llm_json(prompt_part, context_text):
    full_prompt = f"Task: {prompt_part}\nText: {context_text[:3000]}\nReturn ONLY valid JSON."
    raw = ask_llm(full_prompt).strip().strip('```json').strip('```').strip()
    try:
        data = json.loads(raw)
        # Whitelist allowed keys to mitigate untrusted schema injection
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object")
        allowed_keys = {'ux_risks', 'market_risks', 'cost_risks', 'fixes',
                        'heatmap', 'graveyard', 'pipeline', 'status'}
        for key in data.keys():
            if key not in allowed_keys:
                raise ValueError(f"Unexpected key: {key}")
        return data
    except Exception as e:
        logger.error(f"Failed to parse or validate LLM JSON output: {e}. Raw: {raw[:200]}")
        return {"error": "parse_failed", "message": str(e), "raw": raw[:100]}
