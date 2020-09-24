# Ksiemgowy

To projekt sprawdzający maila pod kontem wiadomości z mBanku o nowych
przelewach.  Kiedy przyjdzie przelew, ksiemgowy zapisuje go w wewnętrznej bazie
danych i aktualizuje stronę główną Hakierspejsu.

Ksiemgowy trzyma też zanonimizowaną (poprzez hashowanie oraz
<a href="https://en.wikipedia.org/wiki/Pepper_(cryptography)">pieprzenie</a>)
kopię historii przelewów. Dzięki temu możliwe jest generowanie raportów o
tym, kto spóźnia się z przelewem, jaka jest średnia wielkość składki itd.
