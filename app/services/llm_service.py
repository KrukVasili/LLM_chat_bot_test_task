from __future__ import annotations

import asyncio
from typing import AsyncGenerator, Optional

import structlog
from llama_cpp import Llama

from app.core.config import ChatSettings, LLMSettings

log = structlog.get_logger()


class LLMService:

    _instance: Optional["LLMService"] = None

    def __init__(self, llm_config: LLMSettings, chat_config: ChatSettings) -> None:
        self.llm_config = llm_config
        self.chat_config = chat_config
        self._model: Optional[Llama] = None
        self._inference_lock = asyncio.Lock()

    @classmethod
    async def create(
        cls, llm_config: LLMSettings, chat_config: ChatSettings
    ) -> "LLMService":
        """Фабричный метод для асинхронной инициализации."""
        service = cls(llm_config, chat_config)
        await service._load_model()
        return service

    async def _load_model(self) -> None:
        """Загружает модель в память. Вызывается один раз при старте."""
        model_path = self.llm_config.model_path
        if not self.llm_config.model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path.resolve()}")

        # Блокирующий вызов - выполняем в отдельном потоке
        def _load() -> Llama:
            return Llama(
                model_path=str(model_path),
                n_ctx=self.llm_config.context_window,
                n_gpu_layers=self.llm_config.n_gpu_layers,
                verbose=False,
            )

        log.info("Loading LLM model...")
        self._model = await asyncio.to_thread(_load)
        log.info("LLM model loaded successfully")

    async def stream_response(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        if self._model is None:
            raise RuntimeError("Model not initialized")

        async with self._inference_lock:
            queue: asyncio.Queue[str | None] = asyncio.Queue()

            def _generate_sync() -> None:
                try:
                    for chunk in self._model(
                        prompt=prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stop=["<|im_end|>"],
                        stream=True,
                        echo=False,
                    ):
                        delta = chunk["choices"][0]["text"]
                        if delta:
                            queue.put_nowait(delta)
                except Exception as e:
                    log.error("Stream generation failed", error=str(e), exc_info=True)
                    queue.put_nowait(f"[ERROR] {e}")
                finally:
                    queue.put_nowait(None)

            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _generate_sync)

            while True:
                token = await queue.get()
                if token is None:
                    break
                yield token

    @staticmethod
    def format_prompt(
        history: list[dict[str, str]],
        new_message: str,
        system_prompt: str = "Ты полезный ассистент. Отвечай кратко, по делу, на русском языке. Сохраняй контекст диалога.",
    ) -> str:
        """Формирует промпт в формате ChatML (оптимально для Qwen2.5)."""
        prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        for msg in history:
            prompt += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"
        prompt += f"<|im_start|>user\n{new_message}<|im_end|>\n<|im_start|>assistant\n"
        return prompt

    async def close(self) -> None:
        """Освобождает ресурсы модели."""
        if self._model:
            self._model = None
            log.info("LLM model resources released")
