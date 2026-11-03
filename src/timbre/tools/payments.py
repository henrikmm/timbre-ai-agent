"""Exact, source-linked payment candidates with conservative ambiguity handling."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import re

from timbre.database.values import from_cents, to_cents
from timbre.knowledge.policy_loader import UnknownPolicyTopic


class PaymentRulesUnavailable(ValueError):
    """The local policy does not match the reviewed rule structure."""


def discounted(price: Decimal, percent: Decimal) -> Decimal:
    return (price * (Decimal(1) - percent / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PaymentRules:
    pix_percent: Decimal
    maximum_installments: int
    table_minimum: Decimal
    tiers: tuple[tuple[int, int, Decimal], ...]
    sources: tuple[dict, ...]
    methods: tuple[str, ...]

    @classmethod
    def from_catalog(cls, catalog):
        try:
            records = catalog.get_store_policy("payments")
            by_topic = {record["topic"]: record for record in records}
            promotion = catalog.get_store_policy("promotions.rules")
            table = by_topic["payments"]["content"]
            installments = by_topic["payments.installments"]["content"]
            rules_text = " ".join(record["content"] for record in promotion)
            pix = re.search(r"PIX\s+Pagamento\s+à\s+vista\s+(\d+(?:[,.]\d+)?)%", table)
            credit = re.search(r"Crédito\s+Até\s+(\d+)x\s+sem\s+juros\s+Parcela\s+mínima\s+de\s+R\$\s*([\d.,]+)", table)
            short = re.search(r"até\s+(\d+)x:.*?R\$\s*([\d.,]+)", installments, re.S | re.I)
            tiers = re.findall(r"de\s+(\d+)x\s+a\s+(\d+)x:\s*sem\s+juros,\s*parcela\s+mínima\s+de\s+R\$\s*([\d.,]+)", installments, re.I)
            if (not all((pix, credit, short)) or len(tiers) != 2
                    or "não são cumulativas" not in rules_text
                    or "não se aplica sobre" not in rules_text):
                raise PaymentRulesUnavailable()
            money = lambda value: Decimal(value.replace(".", "").replace(",", "."))
            parsed_tiers = ((1, int(short[1]), money(short[2])),
                            *((int(low), int(high), money(amount)) for low, high, amount in tiers))
            maximum = int(credit[1])
            pix_percent = Decimal(pix[1].replace(",", "."))
            if (not 1 <= maximum <= 24 or parsed_tiers[0][1] + 1 != parsed_tiers[1][0]
                    or parsed_tiers[1][1] + 1 != parsed_tiers[2][0]
                    or parsed_tiers[-1][1] != maximum
                    or not 0 <= pix_percent <= 100 or money(credit[2]) <= 0
                    or any(low > high or amount <= 0 for low, high, amount in parsed_tiers)):
                raise PaymentRulesUnavailable()
            methods = ["pix", "credit_card"]
            if "Cartão de Débito" in table:
                methods.append("debit_card")
            if "Boleto Bancário" in table:
                methods.append("boleto")
            return cls(pix_percent, maximum, money(credit[2]),
                       parsed_tiers, tuple(record["source"] for record in [*records, *promotion]), tuple(methods))
        except (KeyError, TypeError, ValueError, ArithmeticError, UnknownPolicyTopic):
            raise PaymentRulesUnavailable("Payment policy needs manual review before calculation.") from None

    def plan(self, amount: Decimal, count: int) -> dict:
        if count > self.maximum_installments:
            return {"installments": count, "available": False, "reason": "installment_limit_exceeded"}
        cents = to_cents(amount)
        quotient, remainder = divmod(cents, count)
        payments = [from_cents(quotient + (index < remainder)) for index in range(count)]
        tier_minimum = next(minimum for low, high, minimum in self.tiers if low <= count <= high)
        lowest = min(payments)
        if lowest >= max(self.table_minimum, tier_minimum):
            available, reason = True, None
        elif lowest >= min(self.table_minimum, tier_minimum):
            available, reason = False, "policy_confirmation_required"
        else:
            available, reason = False, "minimum_installment_not_met"
        return {"installments": count, "available": available, "reason": reason,
                "total_brl": amount, "installment_amounts_brl": payments,
                "interest_percent": "0", "minimum_policy_amounts_brl": [self.table_minimum, tier_minimum]}


def payment_options(product, promotions, catalog, *, payment_method=None, installments=None):
    rules = PaymentRules.from_catalog(catalog)
    price = product["price_brl"]
    promotional = [dict(promotion, promotional_price_brl=discounted(price, promotion["discount_percent"]),
                        eligibility_confirmed=False) for promotion in promotions]
    pix = {"method": "pix", "total_brl": discounted(price, rules.pix_percent),
           "discount_percent": rules.pix_percent, "discount_base": "list_price",
           "selection_requires_confirmation": bool(promotional)}
    plans = [rules.plan(price, count) for count in range(1, rules.maximum_installments + 1)]
    # Candidate scenarios stay separate. No campaign is selected automatically and
    # no PIX percentage is ever applied to an already discounted campaign price.
    promotion_plans = [{"promotion_id": promotion["promotion_id"],
                        "selection_requires_confirmation": True,
                        "pix_total_brl": promotion["promotional_price_brl"],
                        "pix_additional_discount_percent": "0",
                        "credit_plans": [rules.plan(promotion["promotional_price_brl"], count)
                                         for count in range(1, rules.maximum_installments + 1)]}
                       for promotion in promotional]
    requested = None
    if payment_method is not None or installments is not None:
        method = payment_method or "credit_card"
        if method not in rules.methods:
            requested = {"available": False, "reason": "method_not_supported_by_policy"}
        elif method == "credit_card":
            requested = rules.plan(price, installments or 1)
            if promotional:
                requested = {**requested, "selection_requires_confirmation": True}
        elif installments not in (None, 1):
            requested = {"available": False, "reason": "method_does_not_support_installments"}
        else:
            requested = {"available": True, "method": method,
                         "total_brl": pix["total_brl"] if method == "pix" else price,
                         "selection_requires_confirmation": bool(promotional)}
    return {"product_id": product["product_id"], "product_name": product["name"],
            "list_price_brl": price, "available": True, "pix": pix,
            "quote_status": "snapshot_calculation_only", "live_quote_confirmed": False,
            "checkout_supported": False,
            "full_payment_methods": list(rules.methods),
            "credit_plans": plans, "promotional_candidates": promotional,
            "promotional_payment_candidates": promotion_plans, "requested_option": requested,
            "discounts_stack": False,
            "limitations": ["Snapshot prices and campaign flags are not live quotes.",
                            "Campaign dates, audience, priority, and list-price opt-out are unconfirmed.",
                            "Plans satisfying both conflicting minima are confirmed; disputed plans require staff confirmation.",
                            "Short-plan exception wording and mixed payments require staff confirmation."],
            "policy_sources": list(rules.sources)}
