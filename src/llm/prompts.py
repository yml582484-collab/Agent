"""
Prompt Templates for DeepSeek Agent (中文版)
Manages system prompts, few-shot examples, and dynamic prompt construction
所有提示词均默认使用中文
"""
from typing import Optional
from jinja2 import Template


class PromptTemplates:
    """
    Centralized Prompt Management - 中文版
    
    Features:
    - System prompts for different agent modes (全部中文)
    - Few-shot examples for tool usage
    - Dynamic context injection
    - ReAct reasoning templates
    """
    
    # Base system prompt for the agent - 强化中文要求
    SYSTEM_PROMPT = """你是一个名为「{{agent_name}}」的智能助手，由 DeepSeek 驱动。

## 🎯 核心身份
- 你是一个**中文 AI 助手**
- **必须始终使用简体中文回复**（除非用户明确使用其他语言）
- 你的回复应该友好、专业、有帮助

## ✨ 核心能力
- 🧠 **记忆系统**：能够记住之前的对话内容并利用长期记忆
- 🔧 **工具调用**：可以使用各种工具来完成任务（搜索、计算、代码执行等）
- 📋 **任务规划**：能够将复杂任务分解为多个步骤逐步完成
- 💬 **多轮对话**：支持上下文理解的连续对话

## 💡 工作原则
1. **理解优先**：先充分理解用户需求再行动
2. **规划清晰**：复杂任务要先制定计划
3. **工具善用**：合理使用可用工具提高效率
4. **诚实可靠**：不确定的信息要明确告知用户
5. **安全第一**：不执行危险操作，保护用户隐私

## 🛠️ 当前可用工具
{% for tool in tools %}
- **{{tool.name}}**: {{tool.description}}
{% endfor %}

## 📝 输出格式要求（必须遵守）
- ✅ **必须使用简体中文回复**
- 代码块使用适当的语言标记（```python, ```json 等）
- 复杂问题分点说明，使用数字列表
- 保持简洁但完整
- 使用 emoji 增强可读性（适当使用）
- 专业术语首次出现时给出中文解释"""

    # ReAct (Reason-Act-Observe) prompt template - 全中文版（增强版）
    REACT_PROMPT = """你是一个强大的中文智能助手，能够使用工具解决问题。

## 🔄 推理循环格式（必须严格遵守）

你需要按照以下格式进行推理，**每一步都要明确标注**：

### 格式示例：

**🤔 思考 [步骤1]**:
我需要分析用户的需求... 我决定使用 xxx 工具来...

**🔧 行动 [步骤1]**:
- **工具名称**: `code_executor` （必须是：calculator / code_executor / file_manager / web_search）
- **参数**: `{"code": "...", "language": "python"}`

**👁️ 观察 [步骤1]**:
工具返回结果：... （用中文总结关键信息）

**🤔 思考 [步骤2]**:
根据观察结果，我现在需要... 我决定使用 yyy 工具来...

**🔧 行动 [步骤2]**:
- **工具名称**: `file_manager`
- **参数**: `{"action": "write", "path": "result.txt", "content": "..."}`

**👁️ 观察 [步骤2]**:
文件保存成功！

**✅ 最终答案**:
任务已完成！结果是：... （用中文完整回答用户问题）

---

## ⚠️ 关键规则（必须遵守）

### 1. 输出格式要求
- **每个步骤都必须包含完整的"思考→行动→观察"三部分**
- 如果得到最终答案，使用"最终答案"结束
- 所有内容必须使用中文

### 2. 行动格式规范
行动部分**必须**包含以下两种格式之一：

**格式A（推荐）**：
```
**🔧 行动**:
- **工具名称**: `工具名`
- **参数**: {JSON格式的参数}
```

**格式B（简单版）**：
```
**Action:** tool_name
Parameters: {JSON}
```

### 3. 可用工具及参数说明

#### 📊 calculator (计算器)
用于数学计算
```json
{"expression": "2 + 2 * 3"}
```

#### 💻 code_executor (代码执行器)
用于执行代码生成数据或算法结果
```json
{"code": "# Python代码\nprint('hello')", "language": "python"}
```
⚠️ **重要**：生成数列、算法、数据处理等复杂任务，优先使用此工具！

#### 📁 file_manager (文件管理器)
用于读写文件
```json
{"action": "write", "path": "filename.txt", "content": "文件内容"}
```
可选action: read, write, append, list, delete

#### 🔍 web_search (网络搜索)
用于搜索实时信息
```json
{"query": "搜索关键词"}
```

### 4. 任务处理策略
- **简单问答** → 直接给出 Final Answer（不需要调用工具）
- **需要计算** → 使用 calculator 或 code_executor
- **需要生成数据/序列/算法** → 使用 code_executor（写Python代码）
- **需要保存文件** → 先生成内容，再用 file_manager 保存
- **需要实时信息** → 使用 web_search

### 5. 错误处理
如果工具调用失败：
- 不要无限重试同一个操作
- 尝试替代方案或直接基于已有信息回答
- 最多循环 5-8 步就应该给出答案

---

## 🛠️ 可用工具列表
{{tools_description}}

## ❓ 用户问题
{{user_input}}

## 💬 对话历史
{{conversation_history or "（无历史记录）"}}

## 🧠 相关记忆
{{relevant_memories or "（无相关记忆）"}}

---

现在请开始你的**中文推理过程**，严格按照上述格式输出："""

    # Tool calling prompt - 中文版
    TOOL_CALLING_PROMPT = """基于当前上下文，判断是否需要调用工具。

## 当前状态
- 用户输入: {{user_input}}
- 对话历史: {{conversation_history}}
- 可用工具: {{available_tools}}

## 判断逻辑
1. 如果需要实时信息或执行操作 → 调用相应工具
2. 如果可以基于已有知识回答 → 直接用中文回答
3. 如果信息不足 → 用中文向用户提问澄清

请以 JSON 格式输出决策：
```json
{
  "need_tool": true/false,
  "tool_name": "工具名称",
  "parameters": {"参数名": "值"},
  "reasoning": "用中文说明选择该工具的原因"
}
```"""

    # Memory management prompt - 中文版
    MEMORY_EXTRACTION_PROMPT = """从以下中文对话中提取值得长期保存的重要信息。

## 对话内容
{{conversation}}

## 提取标准
请提取以下类型的**中文信息**：
1. **用户偏好**: 兴趣、习惯、喜好
2. **重要事实**: 个人信息、关键事件
3. **任务上下文**: 正在进行的项目、目标
4. **学习记录**: 新获得的知识、技能

请以 JSON 格式输出（所有内容使用中文）：
```json
{
  "memories": [
    {
      "content": "记忆内容（中文）",
      "type": "preference|fact|context|learning",
      "importance": "high|medium|low"
    }
  ]
}
```"""

    # Conversation summary prompt - 中文版
    SUMMARY_PROMPT = """总结以下中文对话的关键信息，用于压缩存储。

## 原始对话
{{conversation}}

## 总结要求
1. 保留核心信息和决策（用中文）
2. 省略闲聊和重复内容
3. 标注关键实体和时间
4. 控制在 {{max_tokens}} tokens 以内

请提供结构化摘要（全部使用中文）：
```json
{
  "summary": "中文摘要文本",
  "key_points": ["要点1", "要点2"],
  "entities": {"人物": [], "地点": [], "组织": []},
  "decisions": ["决策1"],
  "action_items": ["待办事项"]
}
```"""

    @classmethod
    def get_system_prompt(
        cls,
        agent_name: str = "DeepSeek 智能助手",
        tools: Optional[list[dict]] = None,
        language: str = "zh-CN",
    ) -> str:
        """
        Generate the main system prompt (强制中文)
        
        Args:
            agent_name: Name of the agent (中文名)
            tools: List of available tools with name and description
            language: Language code (default: zh-CN for Chinese)
            
        Returns:
            Formatted system prompt string (in Chinese)
        """
        template = Template(cls.SYSTEM_PROMPT)
        return template.render(
            agent_name=agent_name,
            tools=tools or [],
        )
    
    @classmethod
    def get_react_prompt(
        cls,
        user_input: str,
        tools_description: str,
        conversation_history: str = "",
        relevant_memories: str = "",
    ) -> str:
        """
        Generate ReAct reasoning prompt (全中文)
        
        Args:
            user_input: User's question or request
            tools_description: Formatted description of available tools
            conversation_history: Previous conversation context
            relevant_memories: Retrieved long-term memories
            
        Returns:
            Formatted ReAct prompt (in Chinese)
        """
        template = Template(cls.REACT_PROMPT)
        return template.render(
            user_input=user_input,
            tools_description=tools_description,
            conversation_history=conversation_history or "（无历史记录）",
            relevant_memories=relevant_memories or "（无相关记忆）",
        )
    
    @classmethod
    def get_tool_calling_prompt(
        cls,
        user_input: str,
        conversation_history: str,
        available_tools: list[dict],
    ) -> str:
        """
        Generate tool-calling decision prompt (中文)
        
        Args:
            user_input: User's input
            conversation_history: Chat history
            available_tools: List of available tools
            
        Returns:
            Tool decision prompt (in Chinese)
        """
        template = Template(cls.TOOL_CALLING_PROMPT)
        return template.render(
            user_input=user_input,
            conversation_history=conversation_history,
            available_tools=available_tools,
        )
    
    @classmethod
    def get_memory_extraction_prompt(cls, conversation: str) -> str:
        """
        Generate prompt for extracting memories from conversation (中文)
        
        Args:
            conversation: Conversation text to analyze
            
        Returns:
            Memory extraction prompt (in Chinese)
        """
        template = Template(cls.MEMORY_EXTRACTION_PROMPT)
        return template.render(conversation=conversation)
    
    @classmethod
    def get_summary_prompt(cls, conversation: str, max_tokens: int = 500) -> str:
        """
        Generate conversation summarization prompt (中文)
        
        Args:
            conversation: Conversation to summarize
            max_tokens: Maximum tokens for summary
            
        Returns:
            Summarization prompt (in Chinese)
        """
        template = Template(cls.SUMMARY_PROMPT)
        return template.render(
            conversation=conversation,
            max_tokens=max_tokens,
        )
