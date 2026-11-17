"""LLM module wrapping the Anthropic SDK."""

import time
from typing import Generator

import anthropic

from . import config
from .errors import LlmApiError, MissingApiKeyError

# Initialize logging
from . import logging_config

logging_config.setup_logging()
logger = logging_config.get_logger("llm")


def _check_api_key() -> None:
    """Raise MissingApiKeyError if the API key is not configured."""
    if not config.ANTHROPIC_API_KEY:
        logger.error("API key not configured")
        raise MissingApiKeyError(
            user_message="The Anthropic API key is not configured. Set the ANTHROPIC_API_KEY environment variable.",
        )


def _get_model_id(model_key: str | None = None) -> str:
    """Resolve a model key to an Anthropic model ID."""
    if model_key is None:
        model_key = config.LLM_MODEL_KEY
    return config.LLM_MODELS.get(model_key, config.LLM_MODEL)


def _map_anthropic_error(exc: Exception, elapsed_ms: int) -> LlmApiError:
    """Map an Anthropic SDK exception to a user-friendly LlmApiError."""
    # Auth errors (401, 403)
    if isinstance(exc, anthropic.AuthenticationError):
        logger.error("API authentication failed", error=str(exc), latency_ms=elapsed_ms)
        return LlmApiError(
            user_message="API key is invalid or expired. Please check your ANTHROPIC_API_KEY.",
            detail=str(exc),
        )

    # Rate limit (429)
    if isinstance(exc, anthropic.RateLimitError):
        logger.error("API rate limit exceeded", error=str(exc), latency_ms=elapsed_ms)
        return LlmApiError(
            user_message="Rate limit exceeded. Please wait a moment before asking another question.",
            detail=str(exc),
        )

    # API status errors (4xx, 5xx)
    if isinstance(exc, anthropic.APIStatusError):
        status = getattr(exc, "status_code", 0)
        logger.error("API status error", status_code=status, error=str(exc), latency_ms=elapsed_ms)
        if status >= 500:
            return LlmApiError(
                user_message="The AI service is temporarily unavailable. Please try again later.",
                detail=str(exc),
            )
        return LlmApiError(
            user_message=f"API error (HTTP {status}): {exc.message if hasattr(exc, 'message') else str(exc)}",
            detail=str(exc),
        )

    # Network / connection errors
    if isinstance(exc, anthropic.APIConnectionError):
        logger.error("API connection failed", error=str(exc), latency_ms=elapsed_ms)
        return LlmApiError(
            user_message="Unable to connect to the AI service. Please check your network and try again.",
            detail=str(exc),
        )

    # Fallback for any other Anthropic error
    logger.error("Unexpected API error", error=str(exc), latency_ms=elapsed_ms)
    return LlmApiError(
        user_message="An error occurred while communicating with the AI service. Please try again.",
        detail=str(exc),
    )


def ask(prompt: str, model_key: str | None = None) -> str:
    """Send a prompt to Claude and return the response.

    Args:
        prompt: The prompt text to send to the model.
        model_key: Optional model key to override the default model.

    Returns:
        The model's response text.

    Raises:
        MissingApiKeyError: If ANTHROPIC_API_KEY is not set.
        LlmApiError: If the API call fails.
    """
    _check_api_key()
    model_id = _get_model_id(model_key)

    logger.info("API call started", model=model_id, prompt_length=len(prompt))
    start_time = time.monotonic()

    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        message = client.messages.create(
            model=model_id,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        response_text = message.content[0].text if hasattr(message.content[0], "text") else str(message.content[0])
        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens

        logger.info(
            "API call complete",
            model=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=elapsed_ms,
        )

        return response_text

    except anthropic.APIError as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        raise _map_anthropic_error(e, elapsed_ms) from e
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.error("API call failed", error=str(e), latency_ms=elapsed_ms)
        raise LlmApiError(
            user_message="An unexpected error occurred. Please try again.",
            detail=str(e),
        ) from e


def ask_stream(prompt: str, system: str | None = None, model_key: str | None = None) -> Generator[dict, None, None]:
    """Send a prompt to Claude and yield response chunks as they arrive.

    Each yielded item is a dict:
      - {"type": "text", "content": "..."} during streaming
      - {"type": "usage", "input_tokens": N, "output_tokens": N, "model": "...", "model_key": "..."} at end

    Raises:
        MissingApiKeyError: If ANTHROPIC_API_KEY is not set.
        LlmApiError: If the API call fails.
    """
    _check_api_key()
    model_id = _get_model_id(model_key)
    actual_model_key = model_key if model_key else config.LLM_MODEL_KEY

    logger.info("API stream started", model=model_id, prompt_length=len(prompt))
    start_time = time.monotonic()

    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        stream_kwargs = {
            "model": model_id,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            stream_kwargs["system"] = system

        with client.messages.stream(**stream_kwargs) as stream:
            for text in stream.text_stream:
                yield {"type": "text", "content": text}

            # Get final message to extract usage (inside the with block)
            final_message = stream.get_final_message()

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        yield {
            "type": "usage",
            "input_tokens": final_message.usage.input_tokens,
            "output_tokens": final_message.usage.output_tokens,
            "model": model_id,
            "model_key": actual_model_key,
        }

        logger.info(
            "API stream complete",
            model=model_id,
            input_tokens=final_message.usage.input_tokens,
            output_tokens=final_message.usage.output_tokens,
            latency_ms=elapsed_ms,
        )

    except anthropic.APIError as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        raise _map_anthropic_error(e, elapsed_ms) from e
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.error("API stream failed", error=str(e), latency_ms=elapsed_ms)
        raise LlmApiError(
            user_message="An unexpected error occurred during streaming. Please try again.",
            detail=str(e),
        ) from e