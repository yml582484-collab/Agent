"""
DeepSeek Agent - Example Usage Demonstrations
Shows how to use the agent in different scenarios
"""
import asyncio
import sys
from pathlib import Path

# Add src to path for direct imports
sys.path.insert(0, str(Path(__file__).parent / "src"))


async def example_basic_chat():
    """
    Example 1: Basic Chat Interaction
    Simple conversation with the agent
    """
    print("\n" + "="*60)
    print("📝 Example 1: Basic Chat")
    print("="*60)
    
    from src.agent.core import Agent
    
    # Create and initialize agent
    agent = Agent(auto_initialize=False)
    
    try:
        await agent.initialize()
        
        # Simple chat
        response = await agent.chat("你好！请介绍一下你自己。")
        
        print(f"\n🤖 Agent Response:")
        print(f"{response.response}")
        print(f"\n📊 Stats:")
        print(f"  - Success: {response.success}")
        print(f"  - Tokens used: {response.token_usage.get('total_tokens', 'N/A')}")
        
    finally:
        await agent.close()


async def example_react_planning():
    """
    Example 2: Complex Task with ReAct Planning
    Agent uses tools to complete a multi-step task
    """
    print("\n" + "="*60)
    print("🧠 Example 2: ReAct Planning (Complex Task)")
    print("="*60)
    
    from src.agent.core import Agent
    
    agent = Agent(auto_initialize=False)
    
    try:
        await agent.initialize()
        
        # Complex query that requires tool usage
        print("\n❓ User Query: '帮我计算一下 (234 * 567) + 890 的结果'")
        print("   (Agent will use calculator tool)\n")
        
        response = await agent.process(
            input_text="帮我计算一下 (234 * 567) + 890 的结果",
            use_react=True,  # Enable ReAct planning
        )
        
        print(f"\n🤖 Final Answer:")
        print(f"{response.response}")
        
        if response.reasoning_trace:
            print(f"\n🔍 Reasoning Process ({len(response.reasoning_trace)} steps):")
            for i, step in enumerate(response.reasoning_trace, 1):
                print(f"  Step {i}: {step.get('thought', 'N/A')[:100]}...")
                if step.get('action'):
                    print(f"          → Action: Used tool '{step['action']}'")
        
    finally:
        await agent.close()


async def example_streaming():
    """
    Example 3: Streaming Response
    Real-time token-by-token output
    """
    print("\n" + "="*60)
    print("🌊 Example 3: Streaming Response")
    print("="*60)
    
    from src.agent.core import Agent
    
    agent = Agent(auto_initialize=False)
    
    try:
        await agent.initialize()
        
        print("\n🤖 Streaming response:")
        print("-" * 40)
        
        full_response = []
        async for chunk in agent.chat_stream("请用三句话描述人工智能的发展历程。"):
            print(chunk, end='', flush=True)
            full_response.append(chunk)
        
        print("\n" + "-" * 40)
        print(f"\n✅ Complete! Total characters: {len(''.join(full_response))}")
        
    finally:
        await agent.close()


async def example_memory_system():
    """
    Example 4: Memory System Demonstration
    Shows how short-term and long-term memory work
    """
    print("\n" + "="*60)
    print("🧠 Example 4: Memory System")
    print("="*60)
    
    from src.agent.core import Agent
    
    agent = Agent(auto_initialize=False)
    
    try:
        await agent.initialize()
        
        # First conversation - establish context
        print("\n💬 Conversation 1:")
        r1 = await agent.chat("我叫小明，我喜欢Python编程。")
        print(f"User: 我叫小明，我喜欢Python编程。")
        print(f"Agent: {r1.response[:100]}...")
        
        # Second conversation - test memory retention
        print("\n💬 Conversation 2 (testing memory):")
        r2 = await agent.chat("你还记得我的名字吗？我喜欢什么编程语言？")
        print(f"User: 你还记得我的名字吗？我喜欢什么编程语言？")
        print(f"Agent: {r2.response[:200]}...")
        
        # Check memory status
        status = agent.get_status()
        print(f"\n📊 Memory Status:")
        print(f"  Short-term conversations: {status['memory']['short_term_conversations']}")
        print(f"  Long-term memories: {status['memory']['long_term_memories']}")
        
    finally:
        await agent.close()


async def example_tool_usage():
    """
    Example 5: Direct Tool Usage
    Using tools without going through the agent
    """
    print("\n" + "="*60)
    print("🔧 Example 5: Direct Tool Usage")
    print("="*60)
    
    from src.tools.calculator import CalculatorTool
    from src.tools.file_manager import FileManagerTool
    
    # Calculator example
    print("\n🔢 Calculator Tool:")
    calc = CalculatorTool()
    
    result = await calc.execute(expression="2 ** 16")
    print(f"  Expression: 2^16")
    print(f"  Result: {result['result']}")
    print(f"  Success: {result['success']}")
    
    # File manager example (in workspace directory)
    print("\n📁 File Manager Tool:")
    file_mgr = FileManagerTool()
    
    write_result = await file_mgr.execute(
        action="write",
        path="demo.txt",
        content="Hello from DeepSeek Agent!",
    )
    print(f"  Write: {write_result.get('message', 'Failed')}")
    
    read_result = await file_mgr.execute(
        action="read",
        path="demo.txt",
    )
    print(f"  Read: {read_result.get('content', 'Failed')}")


async def example_session_management():
    """
    Example 6: Session Management
    Multiple independent conversation sessions
    """
    print("\n" + "="*60)
    print("📂 Example 6: Session Management")
    print("="*60)
    
    from src.agent.core import Agent
    
    agent = Agent(auto_initialize=False)
    
    try:
        await agent.initialize()
        
        # Session 1 - English conversation
        print("\n🇺🇸 Session 1 (English):")
        r1 = await agent.chat("Hello! What's your name?", session_id=None)
        session1_id = r1.session_id
        print(f"  Session ID: {session1_id[:8]}...")
        print(f"  Response: {r1.response[:80]}...")
        
        # Session 2 - Chinese conversation (independent context)
        print("\n🇨🇳 Session 2 (Chinese):")
        r2 = await agent.chat("你好！你会做什么？", session_id=None)
        session2_id = r2.session_id
        print(f"  Session ID: {session2_id[:8]}...")
        print(f"  Response: {r2.response[:80]}...")
        
        # List all sessions
        sessions = agent.list_sessions()
        print(f"\n📋 Active Sessions: {len(sessions)}")
        for s in sessions:
            print(f"  - {s['session_id']}: {s['message_count']} messages")
        
        # Clear one session
        print(f"\n🗑️ Clearing Session 1...")
        agent.clear_session(session1_id)
        
        sessions_after = agent.list_sessions()
        print(f"Remaining sessions: {len(sessions_after)}")
        
    finally:
        await agent.close()


async def example_api_server():
    """
    Example 7: Starting API Server
    How to run the FastAPI server
    """
    print("\n" + "="*60)
    print("🌐 Example 7: API Server Information")
    print("="*60)
    
    print("""
To start the API server, run:

    python main.py

Or with custom options:

    python main.py --host 127.0.0.1 --port 8080 --debug

Available endpoints:

  GET  /              → API information
  POST /api/chat      → Send message to agent
  POST /api/chat/stream → Stream response (SSE)
  GET  /api/status    → Agent status and statistics
  GET  /api/tools     → List available tools
  GET  /api/sessions  → List active sessions
  POST /api/reset     → Reset agent state
  GET  /api/health    → Health check

Interactive API documentation:

  Swagger UI: http://localhost:8000/docs
  ReDoc:      http://localhost:8000/redoc

Example curl commands:

  # Chat request
  curl -X POST http://localhost:8000/api/chat \\
    -H "Content-Type: application/json" \\
    -d '{"message": "Hello!", "use_react": false}'

  # Get status
  curl http://localhost:8000/api/status | python -m json.tool
""")


# ==================== Main ====================

async def main():
    """Run all examples"""
    print("\n" + "🚀"*20)
    print("\n🤖 DeepSeek Agent - Usage Examples")
    print("🚀"*20 + "\n")
    
    examples = [
        ("Basic Chat", example_basic_chat),
        ("ReAct Planning", example_react_planning),
        ("Streaming", example_streaming),
        ("Memory System", example_memory_system),
        ("Direct Tools", example_tool_usage),
        ("Session Management", example_session_management),
        ("API Server Info", example_api_server),
    ]
    
    print("Available examples:\n")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")
    
    print("\n" + "-"*60)
    print("Running selected examples...\n")
    
    # Run a subset of examples (comment/uncomment as needed)
    await example_basic_chat()
    await example_tool_usage()
    await example_api_server_info()
    
    # These require actual DeepSeek API key:
    # await example_basic_chat()
    # await example_react_planning()
    # await example_streaming()
    # await example_memory_system()
    # await example_session_management()
    
    print("\n" + "="*60)
    print("✅ All examples completed!")
    print("="*60 + "\n")


async def example_api_server_info():
    """Just show API info without starting server"""
    await example_api_server()


if __name__ == "__main__":
    # Run examples
    asyncio.run(main())
