import logging

import sqlalchemy


LOGGER = logging.getLogger(__name__)


class PrivateState:
    def __init__(self, db_uri):
        self.db = sqlalchemy.create_engine(db_uri)
        metadata = sqlalchemy.MetaData(self.db)

        self.observed_email_ids = sqlalchemy.Table(
            'observed_email_ids', metadata,
            sqlalchemy.Column(
                'id', sqlalchemy.Integer, primary_key=True),
            sqlalchemy.Column(
                'imap_id', sqlalchemy.String, unique=True),
        )
        try:
            self.observed_email_ids.create()
        except sqlalchemy.exc.OperationalError:
            pass

    def was_imap_id_already_handled(self, imap_id):
        for entry in self.observed_email_ids.select().execute().fetchall():
            LOGGER.debug(
                'was_imap_id_already_handled: %r vs %r', imap_id, entry.imap_id
            )
            if entry.imap_id == imap_id:
                return True
        return False

    def mark_imap_id_already_handled(self, imap_id):
        LOGGER.debug('mark_imap_id_already_handled(%r)', imap_id)
        self.observed_email_ids.insert(None).execute(imap_id=imap_id)
