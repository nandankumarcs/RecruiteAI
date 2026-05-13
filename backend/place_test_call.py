#!/usr/bin/env python3
"""Place a test call using the API endpoint."""

import asyncio
import httpx

async def place_test_call():
    print("🧪 Placing test call with Sarvam TTS...")
    print("-" * 60)
    
    # First, login to get token
    print("🔐 Logging in...")
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        login_response = await client.post(
            "/api/auth/login",
            json={
                "email": "dinesh.tomar@yopmail.com",
                "password": "Password@123"
            }
        )
        
        if login_response.status_code != 200:
            print(f"❌ Login failed: {login_response.status_code}")
            print(login_response.text)
            return False
        
        token = login_response.json()["access_token"]
        print("✅ Logged in successfully")
        print()
        
        # Get first resume
        print("📄 Fetching resume...")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get jobs first
        jobs_response = await client.get("/api/jobs", headers=headers)
        if jobs_response.status_code != 200:
            print(f"❌ Failed to fetch jobs: {jobs_response.status_code}")
            return False
        
        jobs = jobs_response.json()
        if not jobs:
            print("❌ No jobs found")
            return False
        
        job_id = jobs[0]["id"]
        print(f"✅ Job: {jobs[0]['title']}")
        
        # Get resumes for this job
        resumes_response = await client.get(f"/api/jobs/{job_id}/resumes", headers=headers)
        if resumes_response.status_code != 200:
            print(f"❌ Failed to fetch resumes: {resumes_response.status_code}")
            return False
        
        resumes = resumes_response.json()
        if not resumes:
            print("❌ No resumes found")
            return False
        
        resume_id = resumes[0]["id"]
        print(f"✅ Resume: {resume_id}")
        print()
        
        # Place call
        test_phone = "+917903229509"
        print(f"📱 Calling: {test_phone}")
        print()
        
        call_response = await client.post(
            f"/api/resumes/{resume_id}/calls/start",
            headers=headers,
            json={"phone_number": test_phone}
        )
        
        if call_response.status_code != 201:
            print(f"❌ Failed to place call: {call_response.status_code}")
            print(call_response.text)
            return False
        
        call_data = call_response.json()
        print("✅ Call initiated successfully!")
        print(f"   Provider: {call_data['provider']}")
        print(f"   Call ID: {call_data['call']['id']}")
        print(f"   Status: {call_data['call']['status']}")
        print()
        print("🎧 Listen for Indian-accented English!")
        print("🔊 Expected voice: Sarvam TTS (bulbul:v3, speaker: shubh)")
        print()
        print("📊 Monitor backend logs for:")
        print("   - 'Requesting TTS from sarvam...'")
        print("   - 'Sarvam TTS success: N bytes'")
        print("   - 'TTS complete. Sent N chunks.'")
        print()
        
        return True

if __name__ == "__main__":
    success = asyncio.run(place_test_call())
    exit(0 if success else 1)
