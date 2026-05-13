"""
Check the latest call details from the database
"""
import asyncio
import json
from sqlalchemy import desc, select
from app.database import async_session_factory
from app.models.call import Call
from app.models.call_message import CallMessage


async def check_latest_call():
    async with async_session_factory() as session:
        # Get the latest call
        result = await session.execute(
            select(Call).order_by(desc(Call.created_at)).limit(1)
        )
        latest_call = result.scalar_one_or_none()
        
        if not latest_call:
            print('No calls found in database')
            return
        
        print(f'=== LATEST CALL DETAILS ===')
        print(f'Call ID: {latest_call.id}')
        print(f'Status: {latest_call.status}')
        print(f'Duration: {latest_call.duration_seconds}s')
        print(f'Created: {latest_call.created_at}')
        print(f'Started: {latest_call.started_at}')
        print(f'Ended: {latest_call.ended_at}')
        print(f'Phone: {latest_call.phone_number}')
        print(f'Provider: {latest_call.provider}')
        print(f'Voice Runtime: {latest_call.voice_runtime}')
        print(f'Job ID: {latest_call.job_id}')
        print(f'Resume ID: {latest_call.resume_id}')
        
        # Get messages
        messages_result = await session.execute(
            select(CallMessage)
            .filter(CallMessage.call_id == latest_call.id)
            .order_by(CallMessage.sequence_number)
        )
        messages = messages_result.scalars().all()
        
        print(f'\n=== MESSAGES ({len(messages)} total) ===')
        for msg in messages:
            print(f'\n[#{msg.sequence_number}] {msg.role.upper()} at {msg.created_at}:')
            content_preview = msg.content[:100] + '...' if len(msg.content) > 100 else msg.content
            print(f'  Content: {content_preview}')
        
        # Cost breakdown
        if latest_call.cost_breakdown:
            print(f'\n=== COST BREAKDOWN ===')
            print(json.dumps(latest_call.cost_breakdown, indent=2))
            
            # Calculate total from breakdown
            if 'estimated_total_usd' in latest_call.cost_breakdown:
                print(f'\nEstimated Total Cost: ${latest_call.cost_breakdown["estimated_total_usd"]:.4f}')
        
        # Latency metrics
        if latest_call.latency_metrics:
            print(f'\n=== LATENCY METRICS ===')
            print(json.dumps(latest_call.latency_metrics, indent=2))


if __name__ == '__main__':
    asyncio.run(check_latest_call())
