"""Shared static status labels; customer response text is never rewritten."""

from timbre.observability import RequestMetrics


def response_error(metrics: RequestMetrics | None, *, include_history_note=True) -> str:
    if metrics is None or metrics.status == "interrupted":
        message = "Response interrupted. Please try again."
    elif metrics.error_category == "timeout":
        message = "The response timed out. Please try again."
    else:
        message = "The response could not be completed. Please try again."
    partial = metrics is None or metrics.partial_output
    return (("Incomplete response. " if partial else "") + message
            + (" This attempt was not saved to conversation history." if include_history_note else ""))
