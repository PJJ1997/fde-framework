# LLM 环境变量配置迁移设计

## 目标

将 Azure OpenAI、DeepSeek 和 LangSmith 的运行配置从源码迁移到项目根目录的 `.env`，避免真实密钥继续出现在代码和示例文档中，并为缺失配置提供清晰错误。

## 范围

本次迁移包含：

- 默认 LLM Provider
- Azure OpenAI endpoint、API key、deployment、API version
- DeepSeek API key、model、base URL
- LLM temperature
- LangSmith tracing 开关、API key 和 project
- README 中已经暴露的密钥示例

不包含 Git 历史清理和云端密钥轮换操作。由于现有密钥已经出现在工作区和可能的 Git 历史中，迁移完成后仍必须在 Azure OpenAI、DeepSeek 和 LangSmith 后台吊销旧密钥并创建新密钥。

## 配置文件

项目根目录新增本地 `.env`，包含实际运行值：

```dotenv
LLM_PROVIDER=azure_openai
LLM_TEMPERATURE=0.7

DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOYMENT=
AZURE_OPENAI_API_VERSION=2025-04-01-preview

LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=fde-framework
```

`.env` 已被 `.gitignore` 忽略，不允许提交。

同时新增可提交的 `.env.example`。它包含相同字段、非敏感默认值和占位符，但不包含任何真实密钥。

## 加载架构

新增集中的配置加载模块，负责：

1. 使用 `python-dotenv` 从项目根目录加载 `.env`。
2. 默认不覆盖进程已经设置的环境变量，使部署平台、CI 和命令行注入的配置优先于 `.env`。
3. 提供读取必填配置的辅助函数；变量缺失或为空时抛出包含变量名的 `ValueError`。
4. 提供 temperature 的浮点数转换；非法值产生明确错误。

`llm/factory.py` 在创建模型前确保配置已加载，并在调用方没有显式传入 provider 时读取 `LLM_PROVIDER`。默认值保持为 `azure_openai`。

Azure OpenAI 和 DeepSeek Provider 仅通过配置模块读取参数，不再包含真实密钥或环境特定 endpoint。

LangSmith tracing 模块在第一次检查 `LANGSMITH_*` 变量前调用同一配置加载入口，从而保证直接启动 FastAPI 时也能读取 `.env`。

## 配置优先级

从高到低：

1. `create_llm(provider=...)` 显式参数
2. 进程环境变量
3. 项目根目录 `.env`
4. 代码中的非敏感默认值

API key、Azure endpoint 和 Azure deployment 没有代码默认值，缺失时必须报错。

## 错误处理

- 选择未知 Provider：保留 `ValueError`，并列出支持的 Provider。
- 必填变量缺失：模型创建时抛出 `ValueError`，错误信息包含缺失变量名。
- `LLM_TEMPERATURE` 不是合法数字：抛出 `ValueError`，错误信息包含变量名和非法值。
- LangSmith 未配置 API key：保持现有行为，关闭 tracing 并输出提示，不阻止应用启动。

## 测试

新增或扩展单元测试，验证：

- 未显式指定 Provider 时读取 `LLM_PROVIDER`。
- 显式 Provider 参数优先于环境变量。
- Azure OpenAI 构造参数来自环境变量。
- DeepSeek 构造参数来自环境变量。
- 必填变量缺失时产生明确错误。
- `.env` 加载不覆盖进程环境变量。
- LangSmith 能看到 `.env` 加载后的配置。

测试不得读取或断言真实密钥；使用临时环境变量和 mock。

## 安全要求

- `.env` 必须保持在 `.gitignore` 中。
- `.env.example` 只能包含占位符。
- README 不出现真实密钥。
- 日志和异常不得输出 API key。
- 迁移完成后轮换所有已经暴露的 API key。
