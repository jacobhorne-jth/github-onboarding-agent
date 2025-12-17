import requests

class HFInferenceLLM:
    def __init__(self, token: str, model: str):
        self.token = token
        self.model = model

    def generate(self, prompt: str, max_new_tokens: int = 350) -> str:
        url = f"https://api-inference.huggingface.co/models/{self.model}"
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_new_tokens,
                "temperature": 0.2,
                "return_full_text": False,
            },
        }

        r = requests.post(url, headers=headers, json=payload, timeout=120)

        # Handle common HF failure modes gracefully
        if r.status_code in (401, 403):
            return f"(HF Inference auth error {r.status_code}) Check HF_API_TOKEN permissions."
        if r.status_code == 404:
            return "(HF Inference error 404) Model not found. Try a different HF_LLM_MODEL."
        if r.status_code == 410:
            return "(HF Inference error 410) Model not available on this Inference API. Try HF_LLM_MODEL=google/flan-t5-large."
        if r.status_code == 503:
            return "(HF Inference is loading the model) Try again in ~30 seconds."
        if not r.ok:
            return f"(HF Inference error {r.status_code}) {r.text[:300]}"

        data = r.json()
        if isinstance(data, list) and data and isinstance(data[0], dict) and "generated_text" in data[0]:
            return data[0]["generated_text"].strip()

        return str(data).strip()
