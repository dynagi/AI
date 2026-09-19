from app.providers.aa_sandbox import AASandboxProvider
from app.providers.base import FinancialDataProvider
from app.providers.csv_provider import CsvProvider
from app.providers.demo_bank import DemoBankProvider
from app.providers.manual import ManualProvider

_REGISTRY: dict[str, FinancialDataProvider] = {
    "demo_bank": DemoBankProvider(),
    "aa_sandbox": AASandboxProvider(),
    "manual": ManualProvider(),
    "csv": CsvProvider(),
}


def get_provider(provider_id: str) -> FinancialDataProvider:
    try:
        return _REGISTRY[provider_id]
    except KeyError:
        raise ValueError(f"Unknown financial data provider: {provider_id}")
