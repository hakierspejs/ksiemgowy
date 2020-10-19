import dateutil.parser
import sqlalchemy


import ksiemgowy.mbankmail


class PublicState:
    def __init__(self, db_uri):
        self.db = sqlalchemy.create_engine(db_uri)
        metadata = sqlalchemy.MetaData(self.db)

        self.mbank_actions = sqlalchemy.Table(
            'mbank_actions', metadata,
            sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True),
            sqlalchemy.Column('mbank_action', sqlalchemy.JSON, unique=True),
        )
        try:
            self.mbank_actions.create()
        except sqlalchemy.exc.OperationalError:
            pass

    def list_mbank_actions(self):
        for entry in self.mbank_actions.select().execute().fetchall():
            ret = entry.mbank_action
            ret['timestamp'] = dateutil.parser.parse(ret['timestamp'])
            # FIXME: use fractions.fraction instead?
            ret['amount_pln'] = float(ret['amount_pln'].replace(',', '.'))
            yield ksiemgowy.mbankmail.MbankAction(**ret)

    def add_mbank_action(self, mbank_action):
        self.mbank_actions.insert(None).execute(mbank_action=mbank_action)
