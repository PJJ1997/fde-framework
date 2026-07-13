# FDE Framework - 简洁版

一个基于 LangGraph 的 ReAct Agent 框架,支持计算器工具。

## 项目结构

```
fde-framework/
├── agents/          # Agent 层
│   └── langgraph/
│       └── react.py # ReAct Agent
├── app/             # 应用层
│   ├── main.py      # FastAPI (25 行)
│   └── routers/
│       └── chat.py  # HTTP 接口
├── llm/             # LLM 层
│   ├── factory.py   # create_llm()
│   └── providers/
│       └── deepseek.py  # DeepSeek (硬编码)
├── tools/           # Tool 层
│   ├── registry/
│   │   └── registry.py
│   └── providers/
│       └── calculation/
│           ├── schemas.py
│           └── tools.py
└── requirements.txt
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置说明

API key 已在 [llm/providers/deepseek.py](file:///d:/python_project/fde-framework/llm/providers/deepseek.py) 中硬编码:

```python
return ChatOpenAI(
    model="deepseek-chat",
    api_key="sk-0077f8cbbeff49bc8c450c1ecb5ac451",
    base_url="https://api.deepseek.com/v1",
    temperature=0.7,
)
```

**如果遇到网络问题**,可能需要配置代理:

```bash
# Windows PowerShell
set HTTP_PROXY=http://your-proxy:port
set HTTPS_PROXY=http://your-proxy:port

# Linux/Mac
export HTTP_PROXY=http://your-proxy:port
export HTTPS_PROXY=http://your-proxy:port
```

### 3. 启动应用

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. 测试接口

**健康检查**:
```bash
curl http://localhost:8000/api/health
```

**聊天**:
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "帮我计算 10 + 5"}'
```

或:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "计算 100 除以 4"}'
```

## API 接口

### POST /api/chat

**请求**:
```json
{
  "text": "帮我计算 10 + 5"
}
```

**响应**:
```json
{
  "response": "计算结果是: 15",
  "input": "帮我计算 10 + 5"
}
```

### GET /api/health

**响应**:
```json
{
  "status": "ok"
}
```

## 支持的工具

- `add`: 加法运算
- `subtract`: 减法运算
- `multiply`: 乘法运算
- `divide`: 除法运算

## 设计原则

1. **简洁**: 没有 middleware、ContextVar、factory 等复杂抽象
2. **直接使用 LangChain**: 直接使用 StructuredTool 和 create_react_agent
3. **极简 Registry**: 只是一个 dict + register/get_tools
4. **清晰的层次**: llm → tools → agents → app

## 示例对话

用户: "帮我计算 10 + 5"
Agent: 调用 add 工具,返回 {"result": 15}
Agent: "计算结果是 15"

用户: "计算 100 除以 4"
Agent: 调用 divide 工具,返回 {"result": 25.0}
Agent: "100 除以 4 等于 25"