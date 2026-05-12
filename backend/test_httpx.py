import asyncio
import httpx

async def test():
    async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
        try:
            res = await client.get('https://consistent-contessa-uncondemnable.ngrok-free.dev/health')
            print(res)
        except Exception as e:
            print(repr(e))

asyncio.run(test())
