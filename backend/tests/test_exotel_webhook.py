from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_exotel_voice_webhook():
    resume_id = "810e1cff-d82a-4029-9472-81da8dc9a8cd"
    response = client.post(f"/v/{resume_id}.xml")
    assert response.status_code == 200
    payload = response.json()
    assert payload["url"].endswith(f"/ws/exotel-media/voice/{resume_id}")
    assert payload["url"].startswith(("ws://", "wss://"))

if __name__ == "__main__":
    test_exotel_voice_webhook()
