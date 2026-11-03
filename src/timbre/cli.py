"""Terminal presentation; conversation state and instrumentation live elsewhere."""

import argparse
import json
import sys
from typing import TextIO

from timbre.config import ConfigurationError, load_config
from timbre.conversation import Conversation
from timbre.llm.openrouter import OpenRouterClient


HELP = """/help              Exibir comandos
/mode              Exibir modo e modelo atuais
/mode standard     Selecionar o modo padrão
/mode fast         Selecionar o modo rápido
/clear             Limpar o histórico (mantém as estatísticas da sessão)
/stats             Exibir métricas da sessão, sem conteúdo da conversa
/debug on          Show sanitized execution traces after each turn
/debug off         Hide automatic execution traces
/trace             Show the latest turn's structured execution trace
/exit              Encerrar"""


def _number(value, suffix="", precision=3):
    return "indisponível" if value is None else f"{value:.{precision}f}{suffix}"


def run_chat(conversation: Conversation, *, input_fn=input, output: TextIO | None = None) -> None:
    output = sys.stdout if output is None else output

    def say(text):
        print(text, file=output, flush=True)

    def show_mode():
        say(f"Modo: {conversation.mode} | Modelo solicitado: {conversation.config.modes[conversation.mode].model}")

    def show_trace():
        events = conversation.get_trace()
        if not events:
            say("No execution trace is available yet.")
        for event in events:
            say(json.dumps(event.to_dict(), ensure_ascii=True, allow_nan=False))

    debug = False
    say("Timbre | Empório da Música\nDigite /help para ver os comandos.")
    show_mode()
    while True:
        try:
            text = input_fn("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            say("\nSessão encerrada.")
            return
        if not text:
            continue
        if text.startswith("/"):
            parts = text.split()
            if parts == ["/exit"]:
                say("Até mais!")
                return
            if parts == ["/help"]:
                say(HELP)
            elif parts[0] == "/mode" and len(parts) in (1, 2):
                if len(parts) == 2:
                    try:
                        conversation.set_mode(parts[1])
                    except ValueError:
                        say("Use /mode standard ou /mode fast.")
                        continue
                    say("Histórico preservado. A troca de modelo pode mudar a interpretação do contexto.")
                show_mode()
            elif parts == ["/clear"]:
                conversation.clear()
                say("Histórico limpo. As instruções do Timbre foram preservadas.")
            elif parts == ["/stats"]:
                stats = conversation.observer.summary()
                say(f"Requisições: {stats['requests']} | Concluídas: {stats['successful_requests']}"
                    f" | Timeouts: {stats['timeouts']} | Streams incompletos: {stats['incomplete_streams']}")
                say(f"TTFT mediano: {_number(stats['median_ttft_seconds'], ' s')}"
                    f" | Latência mediana: {_number(stats['median_total_latency_seconds'], ' s')}"
                    f" | P95: {_number(stats['p95_total_latency_seconds'], ' s')}")
                say(f"Custo observado: {_number(stats['observed_cost_usd'], ' USD', 6)}"
                    f" ({stats['cost_known_requests']}/{stats['requests']} requisições com custo informado)")
                say(f"Cost coverage: {stats['cost_known_model_calls']}/{stats['model_calls']} model calls;"
                    " partial observations are a subtotal.")
                say(f"Tokens informados (entrada/saída): {stats['input_tokens']} / {stats['output_tokens']}"
                    f" | Vazão: {_number(stats['mean_output_tokens_per_second'], ' tokens/s')}")
                say(f"Fallbacks de modelo: {stats['fallback_occurrences']}"
                    f" | Provedores informados: {', '.join(stats['providers']) or 'indisponível'}")
                say(f"Model calls: {stats['model_calls']} | Tool calls: {stats['tool_calls']}"
                    f" | Tool failures: {stats['tool_failures']} | Authorization denials: {stats['authorization_denials']}")
            elif parts in (["/debug", "on"], ["/debug", "off"]):
                debug = parts[1] == "on"
                say(f"Debug {'on' if debug else 'off'}.")
            elif parts == ["/trace"]:
                show_trace()
            else:
                say("Comando inválido. Digite /help.")
            continue
        print("Timbre: ", end="", file=output, flush=True)
        result = conversation.send(text, on_text=lambda chunk: print(chunk, end="", file=output, flush=True))
        say("")
        metrics = result.metrics
        if debug:
            show_trace()
        if metrics.status != "success":
            if metrics.status == "interrupted":
                say("Resposta interrompida. A tentativa não foi salva no histórico.")
            elif metrics.error_category == "timeout":
                say("O tempo de espera terminou. A tentativa não foi salva no histórico.")
            else:
                say("Não consegui concluir a resposta. A tentativa não foi salva no histórico. Você pode tentar novamente.")
        if metrics.fallback_used:
            say(f"Aviso: o modelo alternativo {metrics.actual_model} respondeu a esta tentativa.")
        elif metrics.actual_model is None:
            say("Aviso: o serviço não informou o modelo efetivamente usado.")
        if conversation.observer.persistence_failed:
            say("Aviso: não foi possível gravar as métricas locais; /stats mantém os dados desta sessão.")


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
