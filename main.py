"""
DeepSeek Agent - FastAPI Web Application
Main entry point for the API server
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

# Load environment variables from .env file (must be before other imports)
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ Loaded environment variables from {env_path.name}")
except ImportError:
    pass  # python-dotenv not installed, will use system env vars

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from uvicorn import Config, Server

from src.agent.core import Agent
from src.utils.config import get_config
from src.utils.logger import setup_logger, get_logger


# Pydantic models for API requests/responses
class ChatRequest(BaseModel):
    """Chat request model"""
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = None
    use_react: bool = Field(default=True, description="Use ReAct planning for complex tasks")
    stream: bool = Field(default=False, description="Enable streaming response")


class ChatResponse(BaseModel):
    """Chat response model"""
    session_id: str
    response: str
    success: bool
    reasoning_trace: Optional[list] = None
    token_usage: dict = {}
    metadata: dict = {}


class StatusResponse(BaseModel):
    """Agent status response"""
    status: dict
    sessions: list = []
    tools: list = []


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    detail: Optional[str] = None


# Global agent instance
agent_instance: Optional[Agent] = None
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler
    
    Manages startup and shutdown events.
    """
    global agent_instance
    
    # Startup
    logger.info("🚀 Starting DeepSeek Agent API Server...")
    
    try:
        # Initialize the agent
        agent_instance = Agent(auto_initialize=False)
        await agent_instance.initialize()
        
        logger.info("✅ Agent ready to serve requests!")
        
        yield  # Application is running
        
    except Exception as e:
        logger.error(f"❌ Failed to start agent: {e}")
        raise RuntimeError(f"Agent initialization failed: {e}")
    
    finally:
        # Shutdown
        logger.info("🛑 Shutting down agent...")
        
        if agent_instance:
            await agent_instance.close()
        
        logger.info("👋 Agent shut down complete")


# Create FastAPI application
app = FastAPI(
    title="DeepSeek Agent API",
    description="""
    🤖 A powerful conversational AI agent powered by DeepSeek with:
    
    - **Memory System**: Short-term and long-term memory for context awareness
    - **Tool Calling**: Built-in tools (search, calculator, code executor, file manager)
    - **ReAct Planning**: Advanced reasoning loop for complex tasks
    - **Streaming Responses**: Real-time token-by-token output
    
    ## Quick Start
    
    Send a POST request to `/api/chat` with your message.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Add CORS middleware
config = get_config().config.server
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and frontend
frontend_path = Path(__file__).parent / "frontend"
if frontend_path.exists():
    # Mount static files
    app.mount("/static", StaticFiles(directory=str(frontend_path / "static")), name="static")
    print(f"✅ Static files mounted from {frontend_path / 'static'}")
    
    @app.get("/", tags=["Root"])
    async def root():
        """Serve b1t-AI frontend"""
        index_path = frontend_path / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {
            "name": "b1t-AI",
            "version": "1.0.0",
            "status": "running" if agent_instance else "initializing",
            "docs": "/docs",
        }



# ==================== API Routes ====================


@app.post("/api/chat", response_model=ChatResponse, tags=["Chat"])
async def chat_endpoint(request: ChatRequest):
    """
    Send a message to the agent and get a response
    
    - **message**: Your message or question (required)
    - **session_id**: Existing session ID (optional, creates new if not provided)
    - **use_react**: Enable ReAct planning for complex tasks (default: true)
    - **stream**: Enable streaming (use /api/chat/stream instead for true SSE)
    """
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        if request.use_react:
            # Use ReAct planner for complex tasks
            result = await agent_instance.process(
                input_text=request.message,
                session_id=request.session_id,
                use_react=True,
            )
        else:
            # Simple chat mode
            result = await agent_instance.chat(
                message=request.message,
                session_id=request.session_id,
            )
        
        return ChatResponse(
            session_id=result.session_id,
            response=result.response,
            success=result.success,
            reasoning_trace=result.reasoning_trace,
            token_usage=result.token_usage,
            metadata=result.metadata,
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/stream", tags=["Chat"])
async def chat_stream_endpoint(request: ChatRequest):
    """
    Stream chat response using Server-Sent Events (SSE)
    
    Returns a streaming response with real-time tokens.
    Use this for better user experience in chat interfaces.
    """
    from fastapi.responses import StreamingResponse
    
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    async def generate():
        try:
            async for chunk in agent_instance.chat_stream(
                message=request.message,
                session_id=request.session_id,
            ):
                yield f"data: {chunk}\n\n"
            
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            error_data = {"error": str(e)}
            yield f"data: {error_data}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/status", response_model=StatusResponse, tags=["System"])
async def status_endpoint():
    """
    Get comprehensive agent status and statistics
    
    Returns:
    - Agent initialization state
    - Uptime and request statistics
    - Memory usage
    - LLM provider stats
    - Available tools list
    - Active sessions
    """
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    return StatusResponse(
        status=agent_instance.get_status(),
        sessions=agent_instance.list_sessions(),
        tools=tool_registry_list(),
    )


@app.get("/api/tools", tags=["Tools"])
async def tools_endpoint():
    """
    List all available tools with their descriptions
    
    Returns information about all registered and enabled tools.
    """
    from src.tools.base import tool_registry
    
    tools_info = tool_registry.list_tools()
    
    return {
        "total_tools": len(tools_info),
        "enabled_count": sum(1 for t in tools_info if t["enabled"]),
        "tools": tools_info,
    }


@app.post("/api/tools/{tool_name}/toggle", tags=["Tools"])
async def toggle_tool_endpoint(tool_name: str, enable: bool = True):
    """
    Enable or disable a specific tool
    
    - **tool_name**: Name of the tool to toggle
    - **enable**: True to enable, False to disable
    """
    from src.tools.base import tool_registry
    
    if enable:
        success = tool_registry.enable_tool(tool_name)
    else:
        success = tool_registry.disable_tool(tool_name)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' not found"
        )
    
    return {
        "success": True,
        "tool": tool_name,
        "enabled": enable,
        "message": f"Tool '{tool_name}' {'enabled' if enable else 'disabled'}",
    }


@app.get("/api/sessions", tags=["Sessions"])
async def sessions_endpoint():
    """
    List all active conversation sessions
    
    Returns session IDs and basic statistics.
    """
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    return {
        "sessions": agent_instance.list_sessions(),
        "active_count": len(agent_instance._sessions),
    }


@app.delete("/api/sessions/{session_id}", tags=["Sessions"])
async def delete_session_endpoint(session_id: str):
    """
    Delete/clear a specific session
    
    - **session_id**: Session ID to clear
    """
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    success = agent_instance.clear_session(session_id)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found"
        )
    
    return {"success": True, "message": f"Session cleared"}


@app.post("/api/reset", tags=["System"])
async def reset_endpoint():
    """
    Reset the agent completely
    
    Clears all memory, sessions, and resets state.
    Use with caution - this cannot be undone!
    """
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    await agent_instance.reset()
    
    return {
        "success": True,
        "message": "Agent reset successfully",
        "new_session_id": agent_instance._current_session_id[:8] + "...",
    }


@app.get("/api/health", tags=["System"])
async def health_endpoint():
    """
    Health check endpoint
    
    Returns simple OK if the service is running.
    Used by load balancers and monitoring systems.
    """
    return {
        "status": "healthy",
        "agent_ready": agent_instance is not None and agent_instance._initialized,
    }


@app.get("/api/usage", tags=["System"])
async def usage_endpoint():
    """
    Get real-time balance and token usage from DeepSeek platform
    
    Returns actual account balance and local token statistics.
    """
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    import httpx
    import os
    from datetime import datetime
    
    api_key = os.getenv('DEEPSEEK_API_KEY')
    api_base = os.getenv('DEEPSEEK_API_BASE', 'https://api.deepseek.com')
    
    stats = {
        "balance": {
            "total_balance": 0.0,
            "topped_up_balance": 0.0,
            "granted_balance": 0.0,
            "currency": "CNY",
        },
        "token_usage": {},
        "api_calls": 0,
        "is_available": False,
        "last_updated": None,
    }
    
    try:
        # 获取真实余额数据（调用 DeepSeek 官方 API）
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{api_base}/user/balance",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                stats["is_available"] = data.get("is_available", False)
                
                # 解析余额信息
                balance_infos = data.get("balance_infos", [])
                for info in balance_infos:
                    if info.get("currency") == "CNY":
                        stats["balance"] = {
                            "total_balance": float(info.get("total_balance", 0)),
                            "topped_up_balance": float(info.get("topped_up_balance", 0)),
                            "granted_balance": float(info.get("granted_balance", 0)),
                            "currency": info.get("currency", "CNY"),
                        }
                        break
                
                logger.info(f"✅ 获取余额成功: ¥{stats['balance']['total_balance']}")
            
            else:
                logger.warning(f"获取余额失败: HTTP {response.status_code}")
        
        # 获取本地 token 使用统计
        if hasattr(agent_instance, "_llm_provider") and hasattr(agent_instance._llm_provider, "stats"):
            llm_stats = agent_instance._llm_provider.stats
            stats["token_usage"] = llm_stats.get("token_usage", {})
            stats["api_calls"] = llm_stats.get("total_calls", 0)
        
        # 更新时间戳
        stats["last_updated"] = datetime.now().isoformat()
        
    except Exception as e:
        logger.error(f"获取使用情况失败: {e}")
        stats["error"] = str(e)
    
    return stats


# ==================== Helper Functions ====================

def tool_registry_list() -> list:
    """Get formatted list of tools from registry"""
    from src.tools.base import tool_registry
    
    return [
        {
            "name": tool.name,
            "description": tool.description,
        }
        for tool in tool_registry.get_all_tools()
    ]


# ==================== Main Entry Point ====================

def run_server(
    host: Optional[str] = None,
    port: Optional[int] = None,
    debug: bool = False,
):
    """
    Run the FastAPI server
    
    Args:
        host: Host to bind to (default from config)
        port: Port to listen to (default from config)
        debug: Enable debug mode
    """
    server_config = get_config().config.server
    
    host = host or server_config.host
    port = port or server_config.port
    
    print(f"\n{'='*60}")
    print(f"🚀 Starting DeepSeek Agent API Server")
    print(f"{'='*60}")
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    print(f"   Debug: {debug}")
    print(f"   Docs: http://{host}:{port}/docs")
    print(f"{'='*60}\n")
    
    uvicorn_config = Config(
        app="main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="debug" if debug else "info",
    )
    
    server = Server(config=uvicorn_config)
    
    try:
        server.run()
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped by user")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="DeepSeek Agent API Server")
    parser.add_argument("--host", type=str, default=None, help="Host to bind to")
    parser.add_argument("--port", type=int, default=None, help="Port to listen to")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    # Setup logging before starting
    setup_logger(log_file="./logs/api.log")
    
    run_server(host=args.host, port=args.port, debug=args.debug)