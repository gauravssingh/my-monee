"""Password strategy engine and issuer adapters for credit card statement unlocking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class AccountProfile:
    name: str = ""
    email: str = ""
    dob: str | date | datetime | None = None
    card_last4: str = ""
    pan: str = ""
    custom_password: str = ""
    issuer: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], card_last4: str = "", issuer: str = "") -> AccountProfile:
        return cls(
            name=str(data.get("name") or "").strip(),
            email=str(data.get("email") or "").strip(),
            dob=data.get("dob"),
            card_last4=str(data.get("card_last4") or card_last4 or "").strip(),
            pan=str(data.get("pan") or "").strip().upper(),
            custom_password=str(data.get("custom_password") or "").strip(),
            issuer=str(data.get("issuer") or issuer or "").strip(),
            extra=data.get("extra") or {},
        )

    def get_first_name_4(self) -> str:
        """Extract first 4 alphabetic characters from the name (stripping spaces, dots, and special chars)."""
        cleaned = re.sub(r"[^a-zA-Z]", "", self.name)
        if not cleaned and self.name:
            cleaned = re.sub(r"\s+", "", self.name)
        return cleaned[:4]

    def get_dob_parts(self) -> tuple[str, str, str]:
        """Return (DD, MM, YYYY) as zero-padded strings if available."""
        if not self.dob:
            return "", "", ""

        if isinstance(self.dob, (date, datetime)):
            return f"{self.dob.day:02d}", f"{self.dob.month:02d}", f"{self.dob.year:04d}"

        dob_str = str(self.dob).strip()
        # Try YYYY-MM-DD
        m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", dob_str)
        if m:
            yyyy, mm, dd = m.groups()
            return f"{int(dd):02d}", f"{int(mm):02d}", f"{int(yyyy):04d}"

        # Try DD-MM-YYYY or DD/MM/YYYY
        m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", dob_str)
        if m:
            dd, mm, yyyy = m.groups()
            return f"{int(dd):02d}", f"{int(mm):02d}", f"{int(yyyy):04d}"

        # Try DDMMYYYY
        m = re.match(r"^(\d{2})(\d{2})(\d{4})$", dob_str)
        if m:
            dd, mm, yyyy = m.groups()
            return dd, mm, yyyy

        # Try DDMM (no year)
        m = re.match(r"^(\d{2})(\d{2})$", dob_str)
        if m:
            dd, mm = m.groups()
            return dd, mm, ""

        return "", "", ""


class PasswordStrategy:
    """Base password generation strategy."""

    strategy_id: str = "BASE"

    def generate_candidates(self, profile: AccountProfile) -> list[str]:
        raise NotImplementedError


class Name4DobDDMMStrategy(PasswordStrategy):
    strategy_id = "NAME4_DDMM"

    def generate_candidates(self, profile: AccountProfile) -> list[str]:
        name4 = profile.get_first_name_4()
        dd, mm, _ = profile.get_dob_parts()
        if not name4 or not dd or not mm:
            return []
        ddmm = f"{dd}{mm}"
        return [
            f"{name4.lower()}{ddmm}",
            f"{name4.upper()}{ddmm}",
            f"{name4.capitalize()}{ddmm}",
        ]


class Name4DobDDMMYYYYStrategy(PasswordStrategy):
    strategy_id = "NAME4_DDMMYYYY"

    def generate_candidates(self, profile: AccountProfile) -> list[str]:
        name4 = profile.get_first_name_4()
        dd, mm, yyyy = profile.get_dob_parts()
        if not name4 or not dd or not mm or not yyyy:
            return []
        ddmmyyyy = f"{dd}{mm}{yyyy}"
        return [
            f"{name4.lower()}{ddmmyyyy}",
            f"{name4.upper()}{ddmmyyyy}",
            f"{name4.capitalize()}{ddmmyyyy}",
        ]


class Name4Card4Strategy(PasswordStrategy):
    strategy_id = "NAME4_CARD4"

    def generate_candidates(self, profile: AccountProfile) -> list[str]:
        name4 = profile.get_first_name_4()
        card4 = profile.card_last4
        if not name4 or not card4:
            return []
        return [
            f"{name4.lower()}{card4}",
            f"{name4.upper()}{card4}",
            f"{name4.capitalize()}{card4}",
        ]


class Card4DobDDMMStrategy(PasswordStrategy):
    strategy_id = "CARD4_DOB"

    def generate_candidates(self, profile: AccountProfile) -> list[str]:
        card4 = profile.card_last4
        dd, mm, _ = profile.get_dob_parts()
        if not card4 or not dd or not mm:
            return []
        return [f"{card4}{dd}{mm}"]


class DobDDMMYYYYStrategy(PasswordStrategy):
    strategy_id = "DOB_DDMMYYYY"

    def generate_candidates(self, profile: AccountProfile) -> list[str]:
        dd, mm, yyyy = profile.get_dob_parts()
        if not dd or not mm or not yyyy:
            return []
        return [f"{dd}{mm}{yyyy}"]


class DobDDMMStrategy(PasswordStrategy):
    strategy_id = "DOB_DDMM"

    def generate_candidates(self, profile: AccountProfile) -> list[str]:
        dd, mm, _ = profile.get_dob_parts()
        if not dd or not mm:
            return []
        return [f"{dd}{mm}"]


class PanDobDDMMStrategy(PasswordStrategy):
    strategy_id = "PAN_DOB"

    def generate_candidates(self, profile: AccountProfile) -> list[str]:
        pan = profile.pan
        dd, mm, _ = profile.get_dob_parts()
        if not pan or not dd or not mm:
            return []
        pan4 = pan[:4]
        return [
            f"{pan4.upper()}{dd}{mm}",
            f"{pan4.lower()}{dd}{mm}",
        ]


class CustomPasswordStrategy(PasswordStrategy):
    strategy_id = "CUSTOM"

    def generate_candidates(self, profile: AccountProfile) -> list[str]:
        if profile.custom_password:
            return [profile.custom_password]
        return []


ALL_STRATEGIES: dict[str, PasswordStrategy] = {
    "NAME4_DDMM": Name4DobDDMMStrategy(),
    "NAME4_DDMMYYYY": Name4DobDDMMYYYYStrategy(),
    "NAME4_CARD4": Name4Card4Strategy(),
    "CARD4_DOB": Card4DobDDMMStrategy(),
    "DOB_DDMMYYYY": DobDDMMYYYYStrategy(),
    "DOB_DDMM": DobDDMMStrategy(),
    "PAN_DOB": PanDobDDMMStrategy(),
    "CUSTOM": CustomPasswordStrategy(),
}


# --- Issuer Adapters ---


class BaseIssuerAdapter:
    issuer_name: str = "GENERIC"
    supported_strategies: list[str] = [
        "NAME4_DDMM",
        "NAME4_DDMMYYYY",
        "NAME4_CARD4",
        "CARD4_DOB",
        "DOB_DDMMYYYY",
        "DOB_DDMM",
        "PAN_DOB",
        "CUSTOM",
    ]

    def candidate_strategy_order(self, preferred_strategy: str | None = None) -> list[str]:
        order = list(self.supported_strategies)
        if preferred_strategy and preferred_strategy in order:
            order.remove(preferred_strategy)
            order.insert(0, preferred_strategy)
        elif preferred_strategy and preferred_strategy in ALL_STRATEGIES:
            order.insert(0, preferred_strategy)
        return order

    def password_candidates(
        self, profile: AccountProfile, preferred_strategy: str | None = None
    ) -> list[tuple[str, str]]:
        """Return list of (candidate_password, strategy_id) tuples, deduplicated."""
        strategies = self.candidate_strategy_order(preferred_strategy)
        results: list[tuple[str, str]] = []
        seen: set[str] = set()

        for strat_id in strategies:
            strat = ALL_STRATEGIES.get(strat_id)
            if not strat:
                continue
            candidates = strat.generate_candidates(profile)
            for pwd in candidates:
                if pwd and pwd not in seen:
                    seen.add(pwd)
                    results.append((pwd, strat_id))

        return results


class HDFCStatementAdapter(BaseIssuerAdapter):
    """HDFC typically uses First 4 letters of name (case varies) + DOB in DDMM or DDMMYYYY."""

    issuer_name = "HDFC"
    supported_strategies = [
        "NAME4_DDMM",
        "NAME4_DDMMYYYY",
        "NAME4_CARD4",
        "CUSTOM",
        "DOB_DDMMYYYY",
    ]


class ICICIStatementAdapter(BaseIssuerAdapter):
    """ICICI typically uses First 4 letters of name in lowercase + DDMM."""

    issuer_name = "ICICI"
    supported_strategies = [
        "NAME4_DDMM",
        "NAME4_DDMMYYYY",
        "CUSTOM",
        "DOB_DDMMYYYY",
    ]


class AxisStatementAdapter(BaseIssuerAdapter):
    """Axis Bank typically uses First 4 letters of name uppercase + last 4 of card, or DDMM."""

    issuer_name = "AXIS"
    supported_strategies = [
        "NAME4_CARD4",
        "NAME4_DDMM",
        "CARD4_DOB",
        "NAME4_DDMMYYYY",
        "CUSTOM",
    ]


class SBIStatementAdapter(BaseIssuerAdapter):
    """SBI Card typically uses DDMMYYYY + last 4 card, or DDMM + last 4 card."""

    issuer_name = "SBI"
    supported_strategies = [
        "DOB_DDMMYYYY",
        "NAME4_DDMM",
        "CARD4_DOB",
        "NAME4_CARD4",
        "CUSTOM",
    ]


class ScapiaStatementAdapter(BaseIssuerAdapter):
    """Federal / Scapia cards use custom password configured by user (with DOB fallback)."""

    issuer_name = "SCAPIA"
    supported_strategies = [
        "CUSTOM",
        "DOB_DDMMYYYY",
        "NAME4_DDMM",
        "NAME4_CARD4",
    ]


class FederalBankStatementAdapter(BaseIssuerAdapter):
    issuer_name = "FEDERAL"
    supported_strategies = [
        "DOB_DDMMYYYY",
        "NAME4_DDMM",
        "NAME4_CARD4",
        "CUSTOM",
    ]


class AmexStatementAdapter(BaseIssuerAdapter):
    issuer_name = "AMEX"
    supported_strategies = [
        "DOB_DDMMYYYY",
        "NAME4_CARD4",
        "NAME4_DDMM",
        "CUSTOM",
    ]


class GenericStatementAdapter(BaseIssuerAdapter):
    issuer_name = "GENERIC"


ISSUER_ADAPTERS: dict[str, BaseIssuerAdapter] = {
    "HDFC": HDFCStatementAdapter(),
    "ICICI": ICICIStatementAdapter(),
    "AXIS": AxisStatementAdapter(),
    "SBI": SBIStatementAdapter(),
    "SBICARD": SBIStatementAdapter(),
    "SCAPIA": ScapiaStatementAdapter(),
    "FEDERAL": FederalBankStatementAdapter(),
    "FEDERALBANK": FederalBankStatementAdapter(),
    "AMEX": AmexStatementAdapter(),
    "AMERICANEXPRESS": AmexStatementAdapter(),
    "GENERIC": GenericStatementAdapter(),
}


def get_statement_adapter(issuer: str | None) -> BaseIssuerAdapter:
    if not issuer:
        return GenericStatementAdapter()
    key = re.sub(r"[^A-Za-z0-9]", "", issuer).upper()
    return ISSUER_ADAPTERS.get(key, GenericStatementAdapter())


def generate_candidate_passwords(
    profile: AccountProfile,
    issuer: str | None = None,
    preferred_strategy: str | None = None,
) -> list[tuple[str, str]]:
    adapter = get_statement_adapter(issuer or profile.issuer)
    return adapter.password_candidates(profile, preferred_strategy=preferred_strategy)
