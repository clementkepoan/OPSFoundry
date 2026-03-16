from typing import Any

from core.config.settings import Settings


class LangChainWorkflowEngine:
    """Thin runtime wrapper for model access and workflow execution hooks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_ready(self) -> bool:
        return bool(self.settings.deepseek_api_key)

    def describe_runtime(self) -> dict[str, Any]:
        return {
            "provider": "deepseek",
            "model": self.settings.deepseek_model,
            "base_url": self.settings.deepseek_base_url,
            "configured": self.is_ready(),
        }

    def build_llm(self) -> Any:
        if not self.is_ready():
            raise RuntimeError("DEEPSEEK_API_KEY is not configured.")

        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=self.settings.deepseek_api_key,
            base_url=self.settings.deepseek_base_url,
            model=self.settings.deepseek_model,
            temperature=0,
        )

    async def explain_workflow(self, workflow_name: str, workflow_steps: list[str]) -> dict[str, str]:
        """Day 1 scaffold for future workflow-level reasoning and status narration."""
        if not self.is_ready():
            return {
                "workflow_name": workflow_name,
                "summary": "DeepSeek is not configured; runtime explanation is unavailable.",
            }

        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You explain workflow pipelines in concise operational language.",
                ),
                (
                    "human",
                    "Workflow: {workflow_name}\nSteps: {workflow_steps}",
                ),
            ]
        )
        chain = prompt | self.build_llm()
        response = await chain.ainvoke(
            {
                "workflow_name": workflow_name,
                "workflow_steps": ", ".join(workflow_steps),
            }
        )
        return {"workflow_name": workflow_name, "summary": response.content}
