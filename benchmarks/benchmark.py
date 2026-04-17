import asyncio
import time

import httpx


async def run_benchmark(
    url: str = "http://localhost:8080/api/v1/chat",
    message: str = "Объясни кратко, что такое асинхронность в Python и зачем нужен asyncio.",
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> dict:
    start_time = time.time()
    first_token_time = None
    tokens = []
    token_times = []

    payload = {"message": message, "temperature": temperature, "max_tokens": max_tokens}
    headers = {"Accept": "text/event-stream"}

    timeout = httpx.Timeout(120.0, connect=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST", url, json=payload, headers=headers
        ) as response:
            response.raise_for_status()
            buffer = ""

            async for chunk in response.aiter_bytes():
                buffer += chunk.decode("utf-8", errors="ignore")

                while "\n\n" in buffer:
                    event_block, buffer = buffer.split("\n\n", 1)
                    if not event_block.strip():
                        continue

                    event_type = "message"
                    data = None

                    for line in event_block.strip().split("\n"):
                        if line.startswith("event: "):
                            event_type = line.split("event: ", 1)[1].strip()
                        elif line.startswith("data: "):
                            data = line.split("data: ", 1)[1].strip()

                    if event_type == "message" and data:
                        now = time.time()
                        if first_token_time is None:
                            first_token_time = now

                        tokens.append(data)
                        token_times.append(now)

                    elif event_type in ("done", "error"):
                        break

    total_time = time.time() - start_time
    total_tokens = len(tokens)
    ttft = first_token_time - start_time if first_token_time else 0.0

    if len(token_times) > 1:
        generation_time = token_times[-1] - token_times[0]
        tokens_per_sec = (
            (total_tokens - 1) / generation_time
            if generation_time > 0
            else total_tokens / total_time
        )
    else:
        tokens_per_sec = total_tokens / total_time if total_time > 0 else 0.0

    full_text = "".join(tokens)
    return {
        "ttft": round(ttft, 2),
        "total_tokens": total_tokens,
        "tokens_per_sec": round(tokens_per_sec, 1),
        "total_time": round(total_time, 2),
        "preview": full_text[:120] + "..." if len(full_text) > 120 else full_text,
    }


async def main():
    print("Запуск бенчмарка...\n")

    print("Тестовый запуск...")
    await run_benchmark(message="Привет!")
    await asyncio.sleep(1)

    print("Основной замер:")
    metrics = await run_benchmark()

    print(f"TTFT: {metrics['ttft']} сек")
    print(f"Токенов: {metrics['total_tokens']}")
    print(f"Скорость: {metrics['tokens_per_sec']} ток/сек")
    print(f"Всего времени: {metrics['total_time']} сек")
    print(f"Начало ответа: {metrics['preview']}\n")

    print("-" * 40)
    print(
        f"""| Метрика | Значение |
|---------|----------|
| TTFT | `{metrics['ttft']} сек` |
| Скорость генерации | `{metrics['tokens_per_sec']} токенов/сек` |
| Всего токенов | `{metrics['total_tokens']}` |
| Общее время | `{metrics['total_time']} сек` |
| Пиковое RAM | `` *(замерено через `docker stats`)* |"""
    )
    print("-" * 40)


if __name__ == "__main__":
    asyncio.run(main())
