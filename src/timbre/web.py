"""Session-scoped presentation state; the existing engine alone owns model history."""

from dataclasses import dataclass, field
import os
from typing import Callable

from timbre.config import ConfigurationError, load_config
from timbre.conversation import Conversation, TurnResult
from timbre.llm.openrouter import OpenRouterClient
from timbre.observability import TraceEvent


@dataclass
class DisplayTurn:
    prompt: str
    text: str = ""
    result: TurnResult | None = None


@dataclass
class WebSession:
    conversation: Conversation
    view: str = "customer"
    turns: list[DisplayTurn] = field(default_factory=list)
    pending: str | None = None
    busy: bool = False

    def queue(self, text: str) -> None:
        if self.busy or self.pending is not None:
            raise RuntimeError("A response is already pending.")
        if text.strip():
            self.pending = text.strip()

    def execute(self, on_text: Callable[[str], None],
                on_event: Callable[[TraceEvent], None] | None = None) -> DisplayTurn:
        if self.pending is None or self.busy:
            raise RuntimeError("No pending customer message.")
        turn = DisplayTurn(self.pending)
        # Consume before calling the backend: a rerun can never resubmit this request.
        self.pending = None
        self.turns.append(turn)
        self.turns = self.turns[-self.conversation.config.history_turn_limit * 2:]
        self.busy = True

        def display(chunk: str) -> None:
            turn.text += chunk
            on_text(turn.text)

        try:
            turn.result = self.conversation.send(turn.prompt, on_text=display, on_event=on_event)
            turn.text = turn.result.text
        finally:
            self.busy = False
        return turn

    def clear(self) -> None:
        self.conversation.clear()
        self.turns.clear()
        self.pending = None


def create_session() -> WebSession:
    """Initialize without inference; config paths/credentials stay outside widgets."""
    config = load_config(os.environ.get("TIMBRE_CONFIG"))
    view = os.environ.get("TIMBRE_WEB_VIEW", "customer").strip().lower()
    if view not in ("customer", "developer"):
        raise ConfigurationError("TIMBRE_WEB_VIEW must be customer or developer.")
    client = OpenRouterClient.from_environment(config, os.environ.get("TIMBRE_ENV_FILE", ".env"))
    return WebSession(Conversation(client, config), view=view)
