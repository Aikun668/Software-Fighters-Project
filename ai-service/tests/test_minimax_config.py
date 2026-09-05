from app.services.llm_service import OpenAILLM


def test_openai_compatible_client_reads_minimax_defaults(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL_CHAT", raising=False)
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test-token")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://api.minimax.cn/v1")
    monkeypatch.setenv("MINIMAX_MODEL_CHAT", "MiniMax-M3")

    llm = OpenAILLM(use_mock=True)

    assert llm.base_url == "https://api.minimax.cn/v1"
    assert llm.model == "MiniMax-M3"
    assert llm.api_key == "minimax-test-token"
