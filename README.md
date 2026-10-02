# Banking System

A small bank written in Python using only the standard library: accounts,
customers, transfers and statements.

Project 2 of a 12 week portfolio. Week 1 used the four OOP principles. This
week adds the five SOLID principles on top, and shows where each one is used.

## Status

Day 1 of 7. Current and savings accounts with deposits, withdrawals, an
overdraft, a monthly withdrawal limit and a full history.

## Getting started

```bash
python -m venv .venv
.venv\Scripts\activate           # macOS or Linux: source .venv/bin/activate
pip install -r requirements.txt  # only needed for the tests

python -m banking                # run the demo
pytest                           # run the tests
```

Needs Python 3.10 or newer. Always run it with `python -m banking`, not by
opening a file directly, because the files import each other as a package.

## Using the accounts

```python
from banking import CurrentAccount, SavingsAccount, WithdrawalError

current = CurrentAccount("10000001", "Ronaldo", "120", overdraft_limit="200")
current.deposit("1850", "Wages")
current.withdraw("2000", "New laptop")   # goes into the overdraft
current.balance                          # Decimal('-30.00')

savings = SavingsAccount("10000002", "Ronaldo", "1000", interest_rate="4.5")
try:
    savings.withdraw("5000")
except WithdrawalError as error:         # works for every account type
    print(error)

for line in current.transactions:
    print(line.summary_line())
```

## How it's built

```
banking/
├── account.py           Abstract base class for every account
├── current_account.py   Everyday account with an overdraft
├── savings_account.py   No overdraft, interest rate, monthly withdrawal limit
├── transaction.py       One line of history, can't be changed once made
├── money.py             Turning text into exact amounts of money
├── enums.py             TransactionType and AccountStatus
└── exceptions.py        All the errors the package can raise
```

**Abstraction.** `Account` says what every account can do (deposit, withdraw,
freeze, close) but leaves one question to each type: how much can be taken
out right now? It can't be created on its own.

**Encapsulation.** The balance has no setter. It only changes through
`deposit()` and `withdraw()`, and each change writes a history line at the
same moment, so the history always adds up to the balance.

**Inheritance.** All the shared work lives in `Account`. `CurrentAccount`
adds an overdraft and `SavingsAccount` adds a monthly limit, and each is
short because of it.

**Polymorphism.** `available_to_withdraw` means "balance plus overdraft" on a
current account and "just the balance" on a savings account. The code that
checks a withdrawal asks the same question of both and never checks the type.

### SOLID so far

- **Single responsibility.** `Transaction` only records, `money.py` only
  handles amounts, and accounts don't print anything.
- **Open/closed.** A new account type is a new subclass. `Account` doesn't
  change.
- **Liskov substitution.** Every account type must pass the same set of rules
  in `tests/test_account_rules.py`. Each type may refuse a withdrawal for its
  own reason, but always raises `WithdrawalError` or one of its children, so
  code using any account only catches one error.
- **Dependency inversion.** Accounts don't read the computer's clock
  themselves. They're given a `clock` function, so tests can set the date.

### Other decisions

- **Money is `Decimal`, never `float`.** Floats can't hold 0.10 exactly.
- **History lines are frozen.** Like a real statement, a line can't be
  edited after it's written.
- **A failed withdrawal changes nothing.** Every check runs before the balance
  moves, so the account is never left half updated.

## Tests

```bash
pytest          # 121 tests
```

## Week plan

| Day | Focus |
| --- | --- |
| 1 | `Account` base class, current and savings accounts, history |
| 2 | Customers, the `Bank`, account numbers and transfers |
| 3 | Monthly interest and fees, using swappable rules |
| 4 | Saving and loading |
| 5 | Statements and reports |
| 6 | Command line interface |
| 7 | Final tests, coverage and README |
