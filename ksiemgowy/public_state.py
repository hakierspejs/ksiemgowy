import sqlalchemy


class PublicState:
    def __init__(self):
        self.db = sqlalchemy.create_engine('sqlite:///public_state.sqlite')
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
            yield entry.mbank_action

    def add_mbank_action(self, mbank_action):
        self.mbank_actions.insert(None).execute(mbank_action=mbank_action)
