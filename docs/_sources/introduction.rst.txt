Introduction
============

What is ksiemgowy?
------------------

Ksiemgowy is a tool used for bookkeeping of membership dues in Hakierspejs,
a `hackerspace`_ in Łódź, Poland. Long story short, one day we decided to start
collecting dues in order to build up some money that would eventually let us
rent our headquarters. The person who asked for money also had a secondary
goals:

* transparency: everyone should have access to current information about the
  status of fundraising,
* privacy: the information should be reasonably anonymized, e.g. aggregated in
  a way that would make it difficult to de-anonymize,
* automation: ideally, the person managing the account should be able to take
  some time off on holidays and the system should operate normally,
* good feedback: the system should notify organization members once they are
  overdue or once a payment has been accounted for.

How does ksiemgowy work?
------------------------

  *Every program attempts to expand until it can read mail. Those programs
  which cannot so expand are replaced by ones which can.*

  *Jamie Zawinski*

Most hackerspaces solve the problem of bookkeeping with the aid of `screen
scraping`_, but the author was worried about raising eyebrows when their
program automatically logged in using a script. Because of that, it was
decided to look for passive ways of detecting that a transfer was mode.

mBank, the bank in which Hakierspejs has an account, has daily billing updates,
which is a perfect match for this scenario. Should this feature be enabled,
account owner receives daily updates on which transactions took place. Given
that this includes all incoming and outcoming transfers related to the bank
account, it is a reasonably reliable way to estimate the current balance and
detect who transferred the money. The act of viewing the e-mail is not possible
to observe, which means that we are probably at a lower risk of getting our
account locked.

Another way to think of ksiemgowy is as of a stateful email-to-email bot:
it reads mail and sends mail. All e-mails relevant to ksiemgowy's operation
are parsed and logged in a database, which enables it to send notifications
about overdue payments.

.. _hackerspace: https://en.wikipedia.org/wiki/Hackerspace
.. _screen scraping: https://en.wikipedia.org/wiki/Screen_scraping
