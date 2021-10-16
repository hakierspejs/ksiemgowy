# Ksiemgowy ![open the documentation](https://readthedocs.org/projects/pip/badge/?version=latest&style=plastic)

It is a project that checks e-mails about new messages from mBank
transfers. When a transfer arrives, ksiemgowy enters it in the internal database
data and updates the Hakierspejs homepage. It also sends notifications about
received transfers and reminders for the ones who are overdue.

## Architecture

When designing Ksiemgowy, the following assumptions were made:

1. The first project will run on Jacek's private computer ("regular desktop" / a cheap VM)
1. The project will support a maximum of three-digit number of members with at most a three-digit number of transfers per month,
1. Ultimately, the project will be transferred under the control of the management board of the organization, but it would be good not to provide them with the login and password for my old e-mail, so for this reason:
    * external database support is needed
    * the project should be divided into modules with the possibility of running more than one instance of the email checking module (old Jacek's account + Hakierspejs account shared by the management board)
1. failures are more acceptable than the added complexity of high availability; it is permissible to occasionally intervene in the operation of the program by hand

TODO: add more

## Testing

Ksiemgowy includes the following tests:

1. unit tests that check the operation of individual modules in isolation,
2. a "system" test, in which the e-mail functionality was replaced with mocks,
3. code quality tests and type annotations

For instructions on how to run the tests, see the CI configuration
located in the `.github` directory.

It would be quite difficult to perform a full end-to-end test for ksiemgowy
due to the following factors:

1. the need to run the IMAP and SMTP server and test their effects
side effects,
2. that ksiemgowy works in an endless loop, repeating his tasks
every (usually long) time.

## Known bugs / design flaws / missing functionality

1. Currently, there is no support for internal transfers (belonging to the same owner).
This means that the money wired by the account owner is not going to be visible to the system.

A more comprehensive list of accountant's imperfections can be found here:

https://github.com/hakierspejs/ksiemgowy/issues?q=is%3Aissue+is%3Aopen+sort%3Aupdated-desc

## Associated Systems

Hakierspejs uses Ksiemgowy to display information on the website website: https://hs-ldz.pl.

## Security, data storage policy

The author tries to approach the financial data as if it was radioactive,
although, of course, in the case of bank transfers, it is difficult to speak of a reasonable
privacy level. The complete information is certainly available to Google (because on
their mailbox is set up with mBank notifications) and mBank.

Ksiemgowy keeps an anonymized (by hashing and
<a href="https://en.wikipedia.org/wiki/Pepper_(cryptography)">peppering</a>)
copy of the history of transfers. Thanks to this, it is possible to generate reports on
who is late with the transfer, what is the average amount of the premium, etc.

The data is also kept in plain text on a monitored e-mail address for diagnostic purposes.
This makes it possible to reconstruct most of the database
in case of failure.

There is no data deletion plan at the moment. Of course, it is legally possible
to see which data is being collected and have it removed. Jacek Wielemborek is the
official administrator of the data.
