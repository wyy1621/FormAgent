import os
from langchain_openai import ChatOpenAI
from typing import List, Any
from langchain_core.messages import BaseMessage, HumanMessage

class DebugChatModel(ChatOpenAI):
    """
    A wrapper around ChatOpenAI that prints the complete prompt before invoking the model.
    """
    # 使用一个类变量来跟踪最近处理的问题，避免重复打印
    _last_printed_hash = None
    
    async def ainvoke(self, input: List[BaseMessage], **kwargs) -> Any:
        """Print the complete prompt before sending to model"""
        # 生成一个简单的消息内容哈希，用于检测重复调用
        import hashlib
        msg_hash = hashlib.md5(str([str(msg.content)[:50] for msg in input]).encode()).hexdigest()[:8]
        
        # 只打印不同的请求
        if msg_hash != self._last_printed_hash:
            self._last_printed_hash = msg_hash
            
            # 打印完整的提示内容
            print(f"\n===== 发送给大模型的完整提示 (ID: {msg_hash}) =====")
            for i, msg in enumerate(input):
                msg_type = type(msg).__name__
                
                # 对于系统消息，可能包含长的表格数据，只显示部分
                if msg_type == "SystemMessage":
                    content = msg.content
                    if len(content) > 500:
                        content = content[:250] + "\n...[内容太长，省略中间部分]...\n" + content[-250:]
                    print(f"[{i}] 系统消息:\n{content}\n")
                # 对于用户消息，完整显示
                elif msg_type == "HumanMessage":
                    print(f"[{i}] 用户消息:\n{msg.content}\n")
                # 对于AI消息，可能很长，只显示部分
                elif msg_type == "AIMessage":
                    content = msg.content
                    if len(content) > 300:
                        content = content[:150] + "\n...[内容太长，省略中间部分]...\n" + content[-150:]
                    print(f"[{i}] AI消息:\n{content}\n")
                else:
                    print(f"[{i}] {msg_type}: {str(msg)[:100]}...")
            print(f"===== 完整提示结束 (ID: {msg_hash}) =====\n")
        
        # 调用原始方法
        return await super().ainvoke(input, **kwargs)

def get_llm(type: str, temperature: float = 0.0):
    """
    Get an LLM instance based on the specified type.
    
    Args:
        type (str): The type of LLM to use (PREFILL_LLM, QUESTIONS_LLM, ANSWER_JUDGE_LLM, etc.)
        temperature (float, optional): The temperature for the model. Defaults to 0.0.
        
    Returns:
        An instance of ChatOpenAI
    """
    model_name = os.getenv(type)
    if model_name is None:
        raise ValueError(f"Model name not found for {type}")

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    return DebugChatModel(model=model_name, temperature=temperature)

def clean_llm_response(text):
    """
    Remove <think> and </think> tags from text and strip whitespace/newlines.
    This is specific to the Qwen3 model:
    https://qwenlm.github.io/blog/qwen3/#advanced-usages
    Even when using "/no_think" in the prompt, the model still returns the think tags.
    
    Args:
        text (str): Input string containing think tags
        
    Returns:
        str: Cleaned string with think tags removed and whitespace stripped
    """
    # Find the positions of the tags
    start = text.find('<think>')
    end = text.find('</think>')
    
    if start != -1 and end != -1:
        # Remove everything from <think> to </think> including the tags
        cleaned = text[:start] + text[end + 8:]  # 8 = len('</think>')
    else:
        cleaned = text
    
    # Strip leading/trailing whitespace and newlines
    return cleaned.strip()
