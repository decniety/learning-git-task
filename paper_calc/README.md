# paper_calc

Kalkulator wyniku portfela **PAPER** (symulacja, bez zleceń i bez sieci). Python 3.11+, wyłącznie biblioteka standardowa. Funkcja `calculate` jest czysta: nie trzyma stanu globalnego i nie modyfikuje wejścia. Przy dowolnym błędzie nie zwraca częściowego raportu.

Transakcje muszą być podane w kolejności chronologicznej. `calculate` przetwarza je dokładnie w podanej kolejności.

## Użycie

```python
from decimal import Decimal

from paper_calc import Transaction, calculate

raport = calculate(
    [
        Transaction(
            id="t1",
            ticker="aapl",
            side="buy",
            quantity="2",
            price="10.00",
            fee="0.50",
        ),
    ],
    current_prices={"AAPL": Decimal("12.00")},
    starting_cash=Decimal("2000.00"),
)

print(raport.cash)                   # 1979.50
print(raport.positions[0].avg_cost)  # 10.2500
print(raport.unrealized_pnl)         # 3.50
print(raport.total_equity)           # 2003.50
```

`starting_cash` domyślnie wynosi `Decimal("2000.00")` i musi być >= 0. Kwoty można podać też jako `int` albo `str`. `float` jest odrzucany.

## Zasady

1. Pieniądze i ilości istnieją tylko jako `Decimal`. Konstruktor transakcji oraz `starting_cash` i użyte ceny bieżące odrzucają `float` (`TypeError`, dotyczy też `bool`) i przyjmują `Decimal`, `int` albo `str`.
2. `quantity > 0`, `price > 0`, `fee >= 0`. `NaN` i nieskończoność są odrzucane (`ValidationError`). Strona to dokładnie `buy` albo `sell`. Ticker po `strip().upper()` musi pasować do `^[A-Z][A-Z0-9.\-]{0,9}$` i w tej postaci jest zapisywany.
3. Ten sam `id` i ta sama treść (po normalizacji tickera i porównaniu `Decimal`) jest pomijany. Ten sam `id` z inną treścią podnosi `DuplicateTransactionError`.
4. Koszt średni ważony. Kupno: koszt = ilość × cena + prowizja, doliczany do bazy, `avg_cost = baza / ilość`. Sprzedaż: wynik zrealizowany += ilość × (cena − średnia) − prowizja, baza maleje proporcjonalnie, średnia się nie zmienia. Pozycja zamknięta do zera znika z raportu, a jej baza jest zerowana.
5. Brak shortu i brak ujemnej gotówki. `starting_cash` < 0 podnosi `ValidationError` jeszcze przed przetwarzaniem transakcji; zero jest dozwolone. Sprzedaż ponad posiadaną ilość podnosi `InsufficientPositionError`. Kupno droższe niż dostępna gotówka (ilość × cena + prowizja) oraz sprzedaż, po której gotówka (gotówka + ilość × cena − prowizja) spadłaby poniżej zera, podnoszą `InsufficientCashError`.
6. Brak ceny dla otwartej pozycji podnosi `MissingPriceError`. Klucze cen są normalizowane tak jak tickery. Ceny tickerów bez pozycji są ignorowane. Cena użyta do wyceny musi być skończona i dodatnia. Sprzeczne ceny tego samego tickera podnoszą `ValidationError`.
7. `total_equity = gotówka + suma market_value`. Przed zaokrągleniem wyjścia zachodzi `total_equity = starting_cash + realized_pnl + unrealized_pnl`.
8. Wyniki pieniężne są zaokrąglane do `0.01` dopiero na wyjściu (`ROUND_HALF_UP`). `avg_cost` do `0.0001`. Ilość nie jest zaokrąglana. Obliczenia pośrednie idą w lokalnym kontekście `decimal` o precyzji 28 i nie zmieniają kontekstu globalnego. Pozycje w raporcie są krotką posortowaną po tickerze.

Wyjątki: `ValidationError`, `InsufficientCashError`, `InsufficientPositionError`, `DuplicateTransactionError`, `MissingPriceError` (wspólna baza: `PaperCalcError`).

## Testy

Z katalogu głównego repozytorium:

```bash
pytest
```
