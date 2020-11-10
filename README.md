# Ksiemgowy

To projekt sprawdzający maila pod kontem wiadomości z mBanku o nowych
przelewach.  Kiedy przyjdzie przelew, ksiemgowy zapisuje go w wewnętrznej bazie
danych i aktualizuje stronę główną Hakierspejsu. Wysyła także powiadomienia o
otrzymanych przelewach oraz przypomnienia w przypadku zalegania ze składkami.

## Architektura

TODO

## Plan rozwoju aplikacji

W zasadzie, najchętniej bym ten projekt przepisał. Wydzieliłbym wtedy część
"gadającą" z imap oraz zapisującą zahashowane powiadomienia e-mail w bazie. W
ten sposób części: wysyłająca maile oraz aktualizująca stronę WWW mogłyby
funkcjonować niezależnie od parsera maili.

Alternatywą, która przychodzi mi do głowy jest podzielenie projektu na
"podprogramy", które `schedule` odpala z różnym interwałem. Byłby to dużo
prostszy refactor: kontenerów by ubyło, nie musiałbym też od razu trzymać tak
dużo stanu w bazie. Wydaje mi się to jednak mniej eleganckie.

## Testowanie

TODO

## Znane bugi/wady projektu/brakująca funkcjonalność

1. aktualnie brakuje obsługi przelewów wychodzących oraz wewnętrznych

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

Na ten moment nie ma planu usuwania danych. Oczywiście, zgodnie z prawem możliwy jest
wgląd do danych oraz ich usunięcie na życzenie. Administratorem danych osobowych
jest Jacek Wielemborek.
