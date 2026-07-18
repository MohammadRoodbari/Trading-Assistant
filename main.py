import asyncio
from phoenix.otel import register
from openinference.instrumentation.langchain import LangChainInstrumentor
from agents.orchestrator import build_orchestrator_agent


def setup_tracing():
    tracer_provider = register(
        project_name="financial-orchestrator",
        endpoint="http://127.0.0.1:6006/v1/traces",  # local Phoenix instance
    )
    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
    return tracer_provider


setup_tracing()

async def main():
    agent = await build_orchestrator_agent()
    result = await agent.ainvoke(
        {"messages": [("user", "سهام فملی در حال حاظر سهم ارزنده ای است ؟")]}
    )
    print(result)

asyncio.run(main())
