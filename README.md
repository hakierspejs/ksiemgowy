# Ksiemgowy

To projekt sprawdzający maila pod kontem wiadomości z mBanku o nowych
przelewach.  Kiedy przyjdzie przelew, ksiemgowy zapisuje go w wewnętrznej bazie
danych i aktualizuje stronę główną Hakierspejsu. Wysyła także powiadomienia o
otrzymanych przelewach oraz przypomnienia w przypadku zalegania ze składkami.

## Architektura

TODO

## Plan rozwoju aplikacji

TODO

## Testowanie

TODO

## Wady projektu

TODO

## Powiązane systemy

TODO

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

Na ten moment nie ma planu usuwania danych. Oczywiście, zgodnie z prawem możliwy jest
wgląd do danych oraz ich usunięcie na życzenie. Administratorem danych osobowych
jest Jacek Wielemborek.
