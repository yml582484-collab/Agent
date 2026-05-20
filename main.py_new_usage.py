@app.get("/api/usage", tags=["System"])
async def usage_endpoint():
    """
    Get API usage and balance information from DeepSeek platform
    
    Returns real-time balance and token usage statistics.
    """
    if not agent_instance:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    import httpx
    import os
    from dotenv import load_dotenv
    from pathlib import Path
    
    # 加载环境变量
    load_dotenv(Path(__file__).parent / '.env')
    
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
        # 1. 获取真实余额数据（调用 DeepSeek 官方 API）
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
        
        # 2. 获取本地 token 使用统计
        if hasattr(agent_instance, "_llm_provider") and hasattr(agent_instance._llm_provider, "stats"):
            llm_stats = agent_instance._llm_provider.stats
            stats["token_usage"] = llm_stats.get("token_usage", {})
            stats["api_calls"] = llm_stats.get("total_calls", 0)
        
        # 更新时间戳
        from datetime import datetime
        stats["last_updated"] = datetime.now().isoformat()
        
    except Exception as e:
        logger.error(f"获取使用情况失败: {e}")
        stats["error"] = str(e)
    
    return stats