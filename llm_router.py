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
def ask_llm_json(prompt_part, context_text):
    full_prompt = f"Task: {prompt_part}\nText: {context_text[:3000]}\nReturn ONLY valid JSON."
    raw = ask_llm(full_prompt).strip().strip('```json').strip('```').strip()
    try: return json.loads(raw)
    except: return {"error": "parse_failed", "raw": raw[:100]}
