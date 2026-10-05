# Banking System

A small bank written in Python using only the standard library: accounts,
customers, transfers and statements.

Project 2 of a 12 week portfolio. Week 1 used the four OOP principles. This
week adds the five SOLID principles on top, and shows where each one is used.

## Status

Day 5 of 7. Current and savings accounts, customers, safe transfers, monthly
interest and fees, saving to a file, and statements and reports.

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

## Using the bank

```python
from banking import Bank

bank = Bank("Mudiwa Bank")
ronaldo = bank.add_customer("Ronaldo Mudiwa", "ronaldo@example.com")

current = bank.open_account(ronaldo.customer_id, "current", "250", overdraft_limit="200")
savings = bank.open_account(ronaldo.customer_id, "savings", "1000", interest_rate="4.5")

bank.transfer(current.account_number, savings.account_number, "100", "Monthly saving")
bank.accounts_for(ronaldo.customer_id)   # [current, savings]
bank.total_deposits                      # Decimal('1250.00')
```

A transfer either fully happens or doesn't happen at all. The receiving
account is checked before any money leaves, and if delivery still fails, the
money goes straight back with a "Transfer reversed" line in the history.

## Interest and fees

Each account carries two small rule objects: one for interest and one for
fees. Swap a rule and the account follows the new one, with no change to the
account's code.

```python
from banking import FlatMonthlyFee, OverdraftFee, TieredInterest, CombinedFees

current = bank.open_account(ronaldo.customer_id, "current", "0", overdraft_limit="500",
                            fee_policy=CombinedFees(FlatMonthlyFee("3"), OverdraftFee("24")))

savings = bank.open_account(ronaldo.customer_id, "savings", "6000",
                            interest_policy=TieredInterest([("1000", "2"), (None, "5")]))

bank.run_month_end()   # every account applies its own rules
```

| Rule | What it does |
| --- | --- |
| `NoInterest()` | Pays nothing. Default for a current account |
| `FlatRateInterest("4.5")` | One yearly rate on the whole balance. `interest_rate="4.5"` on a savings account is a shortcut for this |
| `TieredInterest(bands)` | Different rates for different slices of the balance, like tax bands |
| `NoFee()` | Charges nothing. Default for every account |
| `FlatMonthlyFee("3")` | The same charge every month |
| `OverdraftFee("24", minimum="2")` | A yearly rate on what's borrowed, only when overdrawn |
| `CombinedFees(a, b)` | Several fee rules added together |

Interest is paid before fees. Month end only runs once per account per month,
so pressing the button twice by mistake does nothing. Fees are taken even if
they push an account past its overdraft, like a real bank. Closed accounts are
skipped.

## Saving and loading

```python
from banking import JSONBankRepository

repository = JSONBankRepository("data/bank.json")
repository.save(bank)          # writes everything
bank = repository.load()       # None if nothing has been saved yet
```

Everything comes back exactly as it was: customers, accounts, every history
line, each account's interest and fee rules, frozen or closed accounts, and
which accounts have already had this month's interest. New account numbers
and customer ids carry on from where they left off.

The balance itself isn't saved. It's worked out again from the history when
loading, and every line is checked as it goes. So if someone edits a number in
the file, loading stops with a `StorageError` instead of quietly creating
money. Saving writes to a temporary file first and swaps it in, so a crash
half way through never leaves a broken file.

Each piece saves itself with `to_dict()` and loads with `from_dict()`. The
storage code never needs to know what's inside an account or a rule. A new
interest or fee rule only needs `@register_policy("name")` above it to be
saved and loaded.

## Statements and reports

```python
from banking import BankReport, Statement, TextFormatter

formatter = TextFormatter()

statement = Statement.for_month(current, 2026, 10)
print(formatter.statement(statement))     # opening balance, every line, closing balance

report = BankReport(bank)
print(formatter.customer_table(report.customer_summaries()))
print(formatter.overdrawn_table(report.overdrawn_accounts()))
print(formatter.month_activity(report.month_activity(2026, 10)))
```

A `Statement` works like the paper one a bank posts you. The opening balance
is the balance just before the first day, so each month opens exactly where
the last one closed. It's a frozen snapshot, so later activity never changes
an old statement.

`BankReport` gives the bank manager's view: each customer's total across their
accounts, totals by account type, overdrawn accounts (worst first), and the
money in, money out, interest and fees for any month.

`BankReport` and `Statement` only work out numbers. `TextFormatter` turns them
into text. Keeping the two apart means the same numbers could feed a web page
or a spreadsheet later without touching the maths.

## Using an account on its own

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
├── bank.py              Customers, accounts and transfers
├── customer.py          A customer's details
├── account_numbers.py   Where new account numbers come from
├── account.py           Abstract base class for every account
├── policies.py          Interest and fee rules
├── storage.py           Saving and loading the bank
├── statements.py        Monthly statements
├── reports.py           Bank-wide reports and turning them into text
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

### SOLID

- **Single responsibility.** `Transaction` only records, `money.py` only
  handles amounts, and accounts don't print anything. Reports work out
  numbers and `TextFormatter` only does the printing. `Customer` only holds
  a person's details. Which accounts they own is the `Bank`'s job.
- **Open/closed.** A new account type is a new subclass, added with
  `bank.register_account_type(StudentAccount)`. A new interest or fee rule is
  a new class too. Neither `Account` nor `Bank` needs editing. Tests do both
  to prove it.
- **Liskov substitution.** Every account type must pass the same set of rules
  in `tests/test_account_rules.py`. Each type may refuse a withdrawal for its
  own reason, but always raises `WithdrawalError` or one of its children, so
  code using any account only catches one error.
- **Interface segregation.** Interest rules and fee rules are two separate,
  tiny interfaces, each with one method. A fee rule never has to pretend to
  know about interest, and the other way round.
- **Dependency inversion.** The `Bank` relies on `AccountNumberGenerator`, an
  abstract class, not on one way of making numbers. Accounts rely on
  `InterestPolicy` and `FeePolicy`, not on any particular rule. Code that saves
  the bank relies on `BankRepository`, so a database could replace the JSON
  file. Accounts don't read the computer's clock either. They're given a
  `clock` function, so tests can set the date.

### Other decisions

- **Money is `Decimal`, never `float`.** Floats can't hold 0.10 exactly.
- **History lines are frozen.** Like a real statement, a line can't be
  edited after it's written.
- **A failed withdrawal changes nothing.** Every check runs before the balance
  moves, so the account is never left half updated.
- **Closed accounts stay on record.** Closing an account doesn't delete it,
  so its history is still there, like a real bank.
- **Rules are objects, not if statements.** Without them, `Account` would
  need a growing chain of "if it's this kind of account, charge this". This is
  called the Strategy pattern.
- **Emails are matched in any case.** `Ronaldo@Mail.com` and
  `ronaldo@mail.com` count as the same customer.

## Tests

```bash
pytest          # 326 tests
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
