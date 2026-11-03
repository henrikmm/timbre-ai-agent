"""Terminal presentation; conversation state and instrumentation live elsewhere."""

import argparse
import json
import sys
from typing import TextIO

from timbre.config import ConfigurationError, load_config
from timbre.conversation import Conversation
from timbre.llm.openrouter import OpenRouterClient
from timbre.presentation import response_error


HELP = """/help              Show available commands
/mode              Show current mode and model
/mode standard     Select Standard mode
/mode fast         Select Fast mode
/clear             Clear history (keep session statistics)
/stats             Show session metrics without conversation content
/debug on          Show sanitized execution traces after each turn
/debug off         Hide automatic execution traces
/trace             Show the latest turn's structured execution trace
/exit              Exit"""


def _number(value, suffix="", precision=3):
    return "N/A" if value is None else f"{value:.{precision}f}{suffix}"


def run_chat(conversation: Conversation, *, input_fn=input, output: TextIO | None = None) -> None:
    output = sys.stdout if output is None else output

    def say(text):
        print(text, file=output, flush=True)

    def show_mode():
        say(f"Mode: {conversation.mode} | Requested model: {conversation.config.modes[conversation.mode].model}")

    def show_trace():
        events = conversation.get_trace()
        if not events:
            say("No execution trace is available yet.")
        for event in events:
            say(json.dumps(event.to_dict(), ensure_ascii=True, allow_nan=False))

    debug = False
    say("Timbre | Empório da Música\nType /help to see available commands.")
    show_mode()
    while True:
        try:
            text = input_fn("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            say("\nSession ended.")
            return
        if not text:
            continue
        if text.startswith("/"):
            parts = text.split()
            if parts == ["/exit"]:
                say("Goodbye!")
                return
            if parts == ["/help"]:
                say(HELP)
            elif parts[0] == "/mode" and len(parts) in (1, 2):
                if len(parts) == 2:
                    try:
                        conversation.set_mode(parts[1])
                    except ValueError:
                        say("Use /mode standard or /mode fast.")
                        continue
                    say("History preserved. Switching models may affect context interpretation.")
                show_mode()
            elif parts == ["/clear"]:
                conversation.clear()
                say("History cleared. Timbre instructions were preserved.")
            elif parts == ["/stats"]:
                stats = conversation.observer.summary()
                say(f"Requests: {stats['requests']} | Completed: {stats['successful_requests']}"
                    f" | Timeouts: {stats['timeouts']} | Incomplete streams: {stats['incomplete_streams']}")
                say(f"Median TTFT: {_number(stats['median_ttft_seconds'], ' s')}"
                    f" | Median latency: {_number(stats['median_total_latency_seconds'], ' s')}"
                    f" | P95: {_number(stats['p95_total_latency_seconds'], ' s')}")
                say(f"Observed cost: {_number(stats['observed_cost_usd'], ' USD', 6)}"
                    f" ({stats['cost_known_requests']}/{stats['requests']} requests with reported cost)")
                say(f"Cost coverage: {stats['cost_known_model_calls']}/{stats['model_calls']} model calls;"
                    " partial observations are a subtotal.")
                say(f"Reported tokens (input/output): {_number(stats['input_tokens'], precision=0)} / {_number(stats['output_tokens'], precision=0)}"
                    f" | Throughput: {_number(stats['mean_output_tokens_per_second'], ' tokens/s')}")
                say(f"Model fallbacks: {stats['fallback_occurrences']}"
                    f" | Reported providers: {', '.join(stats['providers']) or 'N/A'}")
                say(f"Model calls: {stats['model_calls']} | Tool calls: {stats['tool_calls']}"
                    f" | Tool failures: {stats['tool_failures']} | Authorization denials: {stats['authorization_denials']}")
            elif parts in (["/debug", "on"], ["/debug", "off"]):
                debug = parts[1] == "on"
                say(f"Debug {'on' if debug else 'off'}.")
            elif parts == ["/trace"]:
                show_trace()
            else:
                say("Invalid command. Type /help.")
            continue
        print("Timbre: ", end="", file=output, flush=True)
        result = conversation.send(text, on_text=lambda chunk: print(chunk, end="", file=output, flush=True))
        say("")
        metrics = result.metrics
        if debug:
            show_trace()
        if metrics.status != "success":
            say(response_error(metrics))
        if metrics.fallback_used:
            say(f"Notice: fallback model {metrics.actual_model} responded to this attempt.")
        elif metrics.actual_model is None:
            say("Notice: the service did not report the actual model.")
        if conversation.observer.persistence_failed:
            say("Notice: local metrics could not be saved; /stats retains this session data.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run Timbre's conversational CLI (live requests require a private key).")
    parser.add_argument("--config", help="Path to a complete non-secret TOML configuration")
    parser.add_argument("--env-file", default=".env", help="Explicit private dotenv path (default: .env)")
    arguments = parser.parse_args(argv)
    try:
        config = load_config(arguments.config)
        with OpenRouterClient.from_environment(config, arguments.env_file) as client:
            run_chat(Conversation(client, config))
    except ConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0
