# Trading-Assistant
A multi-agent market analysis system powered by LangChain/LangGraph. An Orchestrator agent routes user queries to specialized agents and combines their insights into a single structured response.

## Architecture

```
                        ┌──────────────────┐
                        │   Orchestrator    │
                        │  (routes + fuses) │
                        └─────────┬─────────┘
              ┌────────────────────┼────────────────────┐
              │                    │                     │
     ┌────────▼────────┐ ┌─────────▼─────────┐ ┌─────────▼─────────┐
     │   news_agent     │ │ foreign_market_    │ │ domestic_market_  │
     │                  │ │ agent              │ │ agent              │
     │  search_news      │ │  TradingView tools  │ │  TSETMC tools       │
     └────────┬─────────┘ └─────────┬─────────┘ └─────────┬─────────┘
              │                     │                     │
     ┌────────▼────────┐ ┌─────────▼─────────┐ ┌─────────▼─────────┐
     │  websearch_mcp   │ │  tradingview_mcp   │ │   tsetmc_mcp       │
     └──────────────────┘ └────────────────────┘ └────────────────────┘
```


### Sub-agents

| Agent | Data source (MCP) | Purpose |
|---|---|---|
| `news_agent` | `websearch_mcp` (`search_news`) | Qualitative / event sentiment |
| `foreign_market_agent` | `tradingview_mcp` | Global technical/quant analysis |
| `domestic_market_agent` | `tsetmc_mcp` | Tehran Stock Exchange analysis |

## Installation

1. Clone the repository:

```bash
git clone https://github.com/MohammadRoodbari/Trading-Assistant
cd Trading-Assistant
```

2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Prerequisites

- Docker (for MCP servers and Phoenix)
- Python 3.10+
- Environment variables for your LLM provider set in `config/settings.py` / `.env` 

## 1. Start the MCP servers

The three sub-agents each depend on an MCP server (`tradingview_mcp`, `tsetmc_mcp`, `websearch_mcp`):

```bash
docker compose up -d
```

## 2. Run the orchestrator agent

`main.py`:

```python
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
```

Run it with:

```bash
python main.py
```

`setup_tracing()` must run before the agent is invoked so every LangChain call is captured by OpenInference and shipped to Phoenix.

## 3. Tracing with Phoenix

Start a local Phoenix instance (only needed once, it persists via the container):

```bash
docker run --name phoenix -p 6006:6006 -p 4317:4317 -itd arizephoenix/phoenix:latest
```

- UI: [http://127.0.0.1:6006](http://127.0.0.1:6006)
- OTLP traces endpoint: `http://127.0.0.1:6006/v1/traces`
- Traces appear under the `financial-orchestrator` project, showing the full call graph: Orchestrator → sub-agent → MCP tool call, with routing decisions, fused scores, and latency per hop.

## 4. Evaluation

Evaluation uses [DeepEval](https://github.com/confident-ai/deepeval) with three metrics run against a golden dataset of routing scenarios.

### Metrics

| Metric | Type | Threshold | Checks |
|---|---|---|---|
| `routing_metric` | `ToolCorrectnessMetric` | 1.0 | The exact set of sub-agents called matches `expected_agents` — no extra, no missing calls |
| `reasoning_depth` | `GEval` | 0.75 | `detailed_reasoning` names and substantiates every called sub-agent, compares scores, justifies the weighting scheme from the question's actual wording, and connects it to the verdict — and is never a duplicate of `rationale` |
| `hallucination_metric` | `GEval` | 0.90 | No fact, number, indicator, or news claim in the output is missing support from at least one sub-agent's actual output |

