"""Apply documented demonstration decisions without editing the source catalog."""

from decimal import Decimal
import re

from timbre.knowledge.policy_loader import UnknownPolicyTopic


def _records(catalog, topic):
    try:
        return catalog.get_store_policy(topic)
    except UnknownPolicyTopic:
        return []


def _money(value):
    return Decimal(value.replace(".", "").replace(",", "."))


def customer_policy(catalog, topic):
    """Return resolved business data with source references, never hidden repairs."""
    resolved, decisions, sources = {}, [], []
    if topic.startswith("store") or topic == "whatsapp":
        records = [*_records(catalog, "store"), *_records(catalog, "whatsapp")]
        text = "\n".join(record["content"] for record in records)
        resolved["contact_channels"] = {
            "phones": list(dict.fromkeys(re.findall(r"\(\d{2}\)\s*\d{4,5}-\d{4}", text))),
            "emails": list(dict.fromkeys(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text))),
        }
        decisions.append("contacts_as_alternatives")
        sources.extend(record["source"] for record in records)
    if topic.startswith("payments"):
        from timbre.tools.payments import PaymentRules, PaymentRulesUnavailable

        try:
            rules = PaymentRules.from_catalog(catalog)
        except PaymentRulesUnavailable:
            pass
        else:
            resolved["installments"] = [
                {"from": low, "to": high, "minimum_installment_brl": minimum}
                for low, high, minimum in rules.tiers]
            resolved["maximum_installments"] = rules.maximum_installments
            resolved["pix_discount_percent"] = rules.pix_percent
            decisions.append("detailed_installment_schedule")
            sources.extend(rules.sources)
    if topic.startswith("shipping"):
        records = _records(catalog, "shipping.local")
        text = " ".join(record["content"] for record in records)
        threshold = re.search(r"acima\s+de\s+R\$\s*([\d.,]+)", text, re.I)
        fee = re.search(r"taxa\s+fixa\s+de\s+R\$\s*([\d.,]+)", text, re.I)
        if threshold and fee:
            resolved["local_shipping"] = {"free_from_brl": _money(threshold[1]),
                                          "fee_below_brl": _money(fee[1])}
            decisions.append("inclusive_free_shipping_threshold")
            sources.extend(record["source"] for record in records)
    if topic.startswith("returns") or topic.startswith("warranty"):
        resolved["preference_exchange_window_starts_at"] = "receipt"
        resolved["exclusions_scope"] = "discretionary_preference_exchange"
        resolved["online_withdrawal_and_defect_requests"] = "assess_under_their_own_sections"
        decisions.append("separate_returns_channels")
    return {"resolved": resolved, "applied_decisions": decisions, "sources": sources}
