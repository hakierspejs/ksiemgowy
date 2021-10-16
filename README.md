# Ksiemgowy

To projekt sprawdzający maila pod kontem wiadomości z mBanku o nowych
przelewach.  Kiedy przyjdzie przelew, ksiemgowy zapisuje go w wewnętrznej bazie
danych i aktualizuje stronę główną Hakierspejsu. Wysyła także powiadomienia o
otrzymanych przelewach oraz przypomnienia w przypadku zalegania ze składkami.

## Architektura

Przy projektowaniu Ksiemgowego przyjęto następujące założenia:

1. projekt będzie działał na prywatnym komputerze Jacka
1. projekt będzie obsługiwał max. trzycyfrową ilość członków z max. trzycyfrową ilością przelewów miesięcznie,
("zwykły desktop" / tania VMka)
1. docelowo projekt będzie przeniesiony pod kontrolę zarządu organizacji, ale dobrze byłoby nie przekazywać im loginu i hasła do mojego starego e-maila, z tego powodu:
    * potrzebna jest obsługa zewnętrznej bazy danych
    * projekt powinien być podzielony na moduły z możliwością uruchomienia więcej niż jednej instancji modułu sprawdzającego pocztę (stare konto Jacka + współdzielone przez zarząd konto Hakierspejsu)
1. awarie są bardziej akceptowalne niż dodatkowa złożoność wynikająca z high availability; dopuszczalne jest okazjonalna konieczność ręcznej ingerencji w działanie programu

TODO: dopisać więcej

## Testowanie

Ksiemgowy zawiera następujące testy:

1. testy jednostkowe, które sprawdzają pracę poszczególnych modułów w izolacji,
2. test "systemowy", w którym funkcjonalność e-mail została zastąpiona mockami,
3. testy jakości kodu oraz adnotacje typów

Aby zobaczyć instrukcje uruchomienia testów, zerknij do konfiguracji CI
znajdującej się w katalogu `.github`.

Wykonanie pełnego testu end-to-end dla ksiemgowego byłoby dość trudne ze
względu na następujące czynniki:

1. potrzebę uruchomienia serwera IMAP oraz SMTP oraz testowania ich skutków
ubocznych,
2. to że ksiemgowy pracuje w pętli nieskończonej, powtarzając swoje zadania
co jakiś (zwykle długi) czas.

## Znane bugi/wady projektu/brakująca funkcjonalność

1. aktualnie brakuje obsługi przelewów wewnętrznych

Bardziej wyczerpującą listę niedoskonałości ksiemgowego można znaleźć tutaj:

https://github.com/hakierspejs/ksiemgowy/issues?q=is%3Aissue+is%3Aopen+sort%3Aupdated-desc

## Powiązane systemy

Hakierspejs używa Ksiemgowego aby wyświetlać informację na stronie
internetowej: https://hs-ldz.pl.

## Bezpieczeństwo, polityka przechowywania danych

Autor stara się podchodzić do danych finansowych jak gdyby były radioaktywne,
choć oczywiście w przypadku przelewów bankowych trudno mówić o mówić o rozsądnym
poziomie prywatności. Kompletem informacji z pewnością dysponuje Google (bo na
ich skrzynkę ustawione są powiadomienia mBanku) oraz mBank.

Ksiemgowy trzyma zanonimizowaną (poprzez hashowanie oraz
<a href="https://en.wikipedia.org/wiki/Pepper_(cryptography)">pieprzenie</a>)
kopię historii przelewów. Dzięki temu możliwe jest generowanie raportów o
tym, kto spóźnia się z przelewem, jaka jest średnia wielkość składki itd.

Informacje potrzebne do skorelowania zahashowanych informacji o nadawcy z adresem
e-mail przechowywane są w oddzielnej bazie danych.

Dane trzymane są także jako zwykły tekst na monitorowanym adresie e-mail, w celach
diagnostycznych. Dzięki temu możliwe jest zrekonstruowanie większości bazy danych
w przypadku awarii.

Na ten moment nie ma planu usuwania danych. Oczywiście, zgodnie z prawem możliwy
jest wgląd do danych oraz ich usunięcie na życzenie. Administratorem danych
osobowych jest Jacek Wielemborek.
