"""Local Streamlit chat over Timbre's shared transactional conversation engine."""

import json
import os

import streamlit as st

from timbre.config import ConfigurationError
from timbre.presentation import response_error
from timbre.web import create_session
from timbre.knowledge.policy_loader import PolicyCatalog, PolicyFileMissing, InvalidPolicyCatalog


CSS = """
<style>
.stApp { background: #101214; }
.block-container { max-width: 1080px; padding-top: 2.2rem; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stChatMessage"] { border: 1px solid #30363c; border-radius: 14px;
  padding: 1.15rem; margin-bottom: .85rem; background: #191d21; }
[data-testid="stChatMessageAvatarAssistant"] { background: #12665d; }
[data-testid="stChatMessageAvatarCustom"] { background: #29343a; }
[data-testid="stMetricValue"] { font-size: 1.35rem; }
.timbre-brand { font-size: 1.75rem; font-weight: 750; letter-spacing: .06em; }
.timbre-brand span { color: #12bfa5; margin-right: .6rem; }
.timbre-subtitle { color: #a4adb5; font-size: .85rem; margin-top: .15rem; }
</style>
"""

EVENT_LABELS = {
    "request_started": "Interaction started",
    "llm_request_started": "LLM request started",
    "llm_request_completed": "LLM request completed",
    "tool_call_requested": "Tool selected",
    "arguments_validated": "Arguments validated",
    "tool_execution_started": "Tool execution started",
    "data_source_accessed": "Data source consulted",
    "tool_execution_completed": "Tool execution completed",
    "tool_result_returned": "Tool result returned",
    "final_answer_generated": "Final response generated",
    "request_completed": "Interaction completed",
    "request_failed": "Interaction failed",
}

TOOL_LABELS = {
    "search_products": ("Search catalog", "products"),
    "get_product_details": ("Read product details", "products"),
    "get_store_policy": ("Consult store policy", "policy sections"),
    "get_active_promotions": ("Check promotions", "promotions"),
    "calculate_payment_options": ("Calculate payment options", "calculations"),
    "get_my_order_status": ("Check order status", "orders"),
}


def activity_label(event):
    if event.event_type == "llm_request_started":
        return "Consulting the assistant…"
    if event.event_type == "request_completed":
        return "Response complete"
    if event.event_type == "request_failed":
        return "Response interrupted"
    if event.tool_name:
        return TOOL_LABELS.get(event.tool_name, ("Check request", "results"))[0]
    if event.event_type == "final_answer_generated":
        return "Answer prepared"
    return "Processing request…"


def render_activity(events):
    """Summarize observed calls and returns without exposing tool result bodies."""
    calls = {}
    for event in events:
        if event.tool_call_id:
            calls.setdefault(event.tool_call_id, []).append(event)
    if not calls:
        st.caption("Consulting the assistant…" if not events or events[-1].event_type not in
                   ("request_completed", "request_failed") else "No tool calls.")
    for group in calls.values():
        event = group[-1]
        title, unit = TOOL_LABELS.get(event.tool_name, ("Check request", "results"))
        returned = next((item for item in reversed(group) if item.event_type == "tool_result_returned"), None)
        execution = next((item for item in group if item.event_type == "tool_execution_completed"), None)
        with st.container(border=True):
            if returned is None:
                st.markdown(f"**{title}** · In progress")
            elif returned.status in ("success", "empty"):
                st.markdown(f"**{title}** · Complete")
                shown_unit = unit.removesuffix("s") if returned.result_count == 1 else unit
                st.caption(f"{number(returned.result_count)} {shown_unit} returned")
            else:
                st.markdown(f"**{title}** · {returned.status.replace('_', ' ').capitalize()}")
            source = next((item.source for item in group if item.source), None)
            if source or execution:
                st.caption(f"Source: {source or 'N/A'} · Duration: "
                           f"{duration(execution.duration_seconds) if execution else 'N/A'}")


def number(value, suffix="", precision=0):
    return "N/A" if value is None else f"{value:,.{precision}f}{suffix}"


def duration(value):
    return "N/A" if value is None else number(value * 1000, " ms")


def chat_markdown(text):
    # BRL currency is literal text, not an inline KaTeX delimiter.
    st.markdown(text.replace("R$", "R\\$"))


def keep_selection(key, fallback):
    if st.session_state[key] is None:
        st.session_state[key] = fallback


def render_trace(result):
    metrics = result.metrics
    with st.container(border=True):
        st.markdown("#### Developer trace")
        st.caption(f"Turn {result.turn_id} · {metrics.status}")
        columns = st.columns(4)
        for column, label, value in zip(columns,
                ("End-to-end", "LLM calls", "Tool calls", "Cost (USD)"),
                (duration(metrics.overall_latency_seconds), number(metrics.model_call_count),
                 number(metrics.tool_call_count), number(metrics.cost_usd, precision=6))):
            column.metric(label, value)
        st.caption("End-to-end includes tool execution and metadata lookups. "
                   "Event durations measure individual operations; nested times overlap.")
        st.text(f"Requested model: {metrics.requested_model}\n"
                f"Actual models: {', '.join(metrics.actual_models or []) or 'N/A'}\n"
                f"Providers: {', '.join(metrics.providers or []) or 'N/A'}")
        st.caption(f"First visible text: {duration(metrics.ttft_seconds)} · "
                   f"Answer available: {duration(metrics.total_latency_seconds)} · "
                   f"Tool execution: {duration(metrics.tool_execution_seconds)}")
        st.caption(f"Input tokens: {number(metrics.input_tokens)} · "
                   f"Output tokens: {number(metrics.output_tokens)} · "
                   f"Total tokens: {number(metrics.total_tokens)}")
        if metrics.cost_usd is None:
            st.caption(f"Observed cost subtotal (USD): {number(metrics.observed_cost_usd, precision=6)} · "
                       f"Cost coverage: {metrics.cost_known_model_calls}/{metrics.model_call_count} model calls")
        st.caption(f"Model fallback: {metrics.fallback_used if metrics.fallback_used is not None else 'N/A'} · "
                   f"Provider fallback: {metrics.provider_fallback_used if metrics.provider_fallback_used is not None else 'N/A'} · "
                   f"Error: {metrics.error_category or 'None'} · Finish reason: {metrics.finish_reason or 'N/A'}")
        if not result.events:
            st.info("No execution events are available for this turn.")
        with st.container(height=360, border=False):
            for index, event in enumerate(result.events, 1):
                label = EVENT_LABELS.get(event.event_type, event.event_type.replace("_", " ").capitalize())
                with st.expander(f"{index:02d} · {label}{' · ' + event.tool_name if event.tool_name else ''} · {event.status or 'N/A'} · {duration(event.duration_seconds)}"):
                    # Only the backend's sanitized typed events enter this view.
                    details = {"Timestamp": event.timestamp, "Tool": event.tool_name,
                               "Source": event.source, "Result count": event.result_count,
                               "Error": event.error_category, "Finish reason": event.finish_reason,
                               "HTTP status": event.http_status}
                    for name, value in details.items():
                        if value is not None:
                            st.text(f"{name}: {value}")
                    if event.sanitized_arguments is not None:
                        st.text("Sanitized arguments")
                        st.code(json.dumps(event.sanitized_arguments, ensure_ascii=True, indent=2), language="json")


def render_turn(turn, developer):
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown("**You**")
        chat_markdown(turn.prompt)
    with st.chat_message("assistant", avatar=":material/graphic_eq:"):
        st.markdown("**Timbre**")
        if developer and turn.result is not None:
            render_activity(turn.result.events)
        if turn.text:
            chat_markdown(turn.text)
        if turn.result is None or turn.result.metrics.status != "success":
            st.warning(response_error(turn.result.metrics if turn.result else None,
                                      include_history_note=developer))
    if developer and turn.result is not None:
        render_trace(turn.result)


def main():
    st.set_page_config(page_title="Timbre · Empório da Música", page_icon="🎵", layout="centered")
    st.html(CSS)
    if "timbre_session" not in st.session_state:
        try:
            st.session_state.timbre_session = create_session()
        except ConfigurationError as error:
            st.title("Timbre")
            if os.environ.get("TIMBRE_WEB_VIEW") == "developer":
                st.error(str(error))
                st.info("Configure the local environment, then reload this page. See README for setup.")
            else:
                st.error("Timbre is temporarily unavailable. Please try again shortly.")
            st.stop()
    session = st.session_state.timbre_session
    conversation = session.conversation
    developer = session.view == "developer"
    disabled = session.pending is not None or session.busy
    st.session_state.setdefault("model_mode", conversation.mode)
    brand, model, reset = st.columns([3, 2, 1.2], vertical_alignment="center")
    with brand:
        st.html('<div class="timbre-brand"><span>≋</span>TIMBRE</div>'
                '<div class="timbre-subtitle">Empório da Música</div>')
    with model:
        mode = st.segmented_control("Response", ["standard", "fast"], key="model_mode",
                                    format_func=str.title, selection_mode="single", disabled=disabled,
                                    on_change=keep_selection, args=("model_mode", conversation.mode))
        if mode is None:
            mode = conversation.mode
        if mode != conversation.mode:
            conversation.set_mode(mode)
    if reset.button("New chat", disabled=disabled, use_container_width=True):
        session.clear()
        st.rerun()
    if developer:
        st.caption(f"Developer workspace · Requested model: {conversation.config.modes[conversation.mode].model}")
    st.divider()
    try:
        if PolicyCatalog(conversation.config.tools.policies_path).document["name"].startswith("synthetic"):
            st.caption("Synthetic portfolio demo · fictional products and policies")
    except (PolicyFileMissing, InvalidPolicyCatalog):
        pass
    if not session.turns and session.pending is None:
        st.markdown("### Find your next sound.")
        st.write("Ask about instruments, availability, payment options, or store policies.")
    for turn in session.turns:
        render_turn(turn, developer)
    # Update the pinned input before a blocking send so stale controls cannot submit.
    prompt = st.chat_input("Ask about an instrument…", disabled=disabled)
    if session.pending is not None:
        with st.chat_message("user", avatar=":material/person:"):
            st.markdown("**You**")
            chat_markdown(session.pending)
        with st.chat_message("assistant", avatar=":material/graphic_eq:"):
            st.markdown("**Timbre**")
            if developer:
                progress = st.status("Processing request…", expanded=True)
                with progress:
                    activity = st.empty()
                slot = st.empty()
                events = []

                def on_event(event):
                    events.append(event)
                    progress.update(label=activity_label(event), state=("complete" if
                        event.event_type == "request_completed" else "error" if
                        event.event_type == "request_failed" else "running"))
                    with activity.container():
                        render_activity(events)

                session.execute(lambda text: slot.markdown(text.replace("R$", "R\\$")), on_event=on_event)
            else:
                slot = st.empty()
                with st.spinner("Thinking…"):
                    session.execute(lambda text: slot.markdown(text.replace("R$", "R\\$")))
        st.rerun()
    if session.turns:
        last = session.turns[-1]
        if last.result is None or last.result.metrics.status != "success":
            if st.button("Retry last message", disabled=disabled):
                session.queue(last.prompt)
                st.rerun()
    if developer and conversation.observer.persistence_failed:
        st.warning("Local metrics could not be saved. Session diagnostics remain available.")
    if prompt:
        session.queue(prompt)
        st.rerun()


if __name__ == "__main__":
    main()
