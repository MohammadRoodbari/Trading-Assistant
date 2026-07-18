import asyncio

from deepeval import evaluate
from deepeval.test_case import LLMTestCase, ToolCall, SingleTurnParams
from deepeval.metrics import ToolCorrectnessMetric, GEval
from evals.test_orchestrator import run_orchestrator
from deepeval.models import GPTModel
from deepeval.dataset import Golden, EvaluationDataset
from config.settings import settings

MODEL = GPTModel(model=settings.LLM_MODEL,
                 temperature=0,
                   base_url=settings.BASE_URL,
                   api_key=settings.API_KEY)



goldens = [
    Golden(
        input="مس فملی در حال حاظر سهم ارزنده ای است ؟",
        additional_metadata={
            "expected_agents": ["domestic_market_agent", "news_agent"],
            "forbidden_agents": ["foreign_market_agent"],
            "expected_market": "DOMESTIC",
        },
    ),

    Golden(
        input="قیمت جهانی طلا در بازار جهانی الان چطوره؟ تحلیل تکنیکال بده",
        additional_metadata={
            "expected_agents": ["foreign_market_agent", "news_agent"],
            "forbidden_agents": ["domestic_market_agent"],
            "expected_market": "FOREIGN",
        },
    ),

    Golden(
        input="قیمت انس نقره رو تحلیل کن - در یک هفته گذشته قیمت ها به چه صورت بوده",
        additional_metadata={
            "expected_agents": ["foreign_market_agent", "news_agent"],
            "forbidden_agents": ["domestic_market_agent"],
            "expected_market": "FOREIGN",
        },
    ),

    Golden(
        input="Just give me the RSI, MACD and moving averages on BTC/USD, no news or sentiment needed.",
        additional_metadata={
            "expected_agents": ["foreign_market_agent"],
            "forbidden_agents": ["news_agent", "domestic_market_agent"],
            "expected_market": "FOREIGN",
        },
    ),

    Golden(
        input="سهام اپل رو تحلیل کن، وضعیتش چطوره برای خرید؟",
        additional_metadata={
            "expected_agents": ["foreign_market_agent", "news_agent"],
            "forbidden_agents": ["domestic_market_agent"],
            "expected_market": "FOREIGN",
        },
    ),

    Golden(
        input="امروز ورود پول داشتیم برای صندوق های طلا؟",
        additional_metadata={
            "expected_agents": ["domestic_market_agent", "news_agent"],
            "forbidden_agents": ["foreign_market_agent"],
            "expected_market": "DOMESTIC",
        },
    ),

    Golden(
        input="بر اساس اندیکاتورهای لحظه‌ای، همین الان باید اتریوم رو بخرم یا بفروشم؟",
        additional_metadata={
            "expected_agents": ["foreign_market_agent", "news_agent"],
            "weighting_scheme": "technical-weighted",
        },
    ),

    Golden(
        input="نظرت درباره وضعیت بازار چیه؟ باید چیکار کنم؟",
        additional_metadata={
            "expected_behavior": "clarifying_question",
            "forbidden_agents": ["foreign_market_agent", "domestic_market_agent", "news_agent"],
        },
    ),

    Golden(
        input="در بازار داخلی، آیا اخبار اخیر روی قیمت سکه امامی تاثیر منفی گذاشته؟",
        additional_metadata={
            "expected_agents": ["domestic_market_agent", "news_agent"],
            "forbidden_agents": ["foreign_market_agent"],
            "news_query_must_contain": ["بازار داخلی", "سکه امامی"],
        },
    ),

    Golden(
        input="بر اساس اطلاعات تا تاریخ ۱۴۰۳/۰۲/۱۵ (2024-05-04)، وضعیت نفت رو تحلیل کن",
        additional_metadata={
            "expected_agents": ["foreign_market_agent", "news_agent"],
            "expected_as_of_date": "2024-05-04",
            "as_of_must_match_across_agents": True,
        },
    ),
]

dataset = EvaluationDataset(goldens=goldens)


# ---- metrics ----
reasoning_depth = GEval(
    name="DetailedReasoningQuality",
    model=MODEL,
    criteria=(
        "detailed_reasoning must name and summarize every called sub-agent with "
        "concrete evidence, compare their scores, justify the weighting scheme "
        "from the input wording, and connect it to the final verdict. It must not "
        "duplicate rationale."
    ),
    evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
    threshold=0.75,
)

hallucination_metric = GEval(
    name="Hallucination",
    model=MODEL,
    criteria="""
    The final response must not introduce any factual information
    that is absent from the outputs of the called sub-agents.

    Every market fact, event, numerical value, technical indicator,
    or news claim must be supported by at least one sub-agent output.

    Reasoning and synthesis are allowed,
    but inventing new facts is not.
    """,
    evaluation_params=[
        SingleTurnParams.INPUT,
        SingleTurnParams.ACTUAL_OUTPUT,
    ],
    threshold=0.9,
)

routing_metric = ToolCorrectnessMetric(threshold=1.0, model=MODEL)


async def golden_to_test_case(golden: Golden) -> LLMTestCase:
    """Run the orchestrator on a golden's input and attach expected_tools
    so ToolCorrectnessMetric can score it."""
    out = await run_orchestrator(golden.input)
    expected = golden.additional_metadata.get("expected_agents", [])

    return LLMTestCase(
        input=golden.input,
        actual_output=out["signal"].model_dump_json(),
        tools_called=[ToolCall(name=c["name"]) for c in out["tool_calls"]],
        expected_tools=[ToolCall(name=a) for a in expected],
        additional_metadata=golden.additional_metadata,
    )

async def main():
    test_cases = []
    for golden in dataset.goldens:
        tc = await golden_to_test_case(golden)
        test_cases.append(tc)

    dataset.test_cases = test_cases

    evaluate(
        test_cases=dataset.test_cases,
        metrics=[routing_metric, reasoning_depth, hallucination_metric],
    )


if __name__ == "__main__":
    asyncio.run(main())