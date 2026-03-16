from pydantic import BaseModel


class AccountRecord(BaseModel):
    account_code: str
    account_name: str
    account_type: str


CHART_OF_ACCOUNTS = [
    AccountRecord(account_code="6100", account_name="Office Supplies", account_type="expense"),
    AccountRecord(account_code="6200", account_name="Travel Expense", account_type="expense"),
    AccountRecord(account_code="2100", account_name="Accounts Payable", account_type="liability"),
]


def lookup_chart_of_accounts(query: str) -> list[AccountRecord]:
    normalized_query = query.lower().strip()
    return [
        account
        for account in CHART_OF_ACCOUNTS
        if normalized_query in account.account_code.lower()
        or normalized_query in account.account_name.lower()
    ]
