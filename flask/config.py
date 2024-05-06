import ijson
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'secret_key_here')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    @property
    def SQLALCHEMY_BINDS(self):
        return self.load_database_config()

    @staticmethod
    def load_database_config():
        connection_string = "postgresql://openpg:openpgpwd@host.docker.internal:5432/"
        with open('config.json', 'rb') as config_file:
            databases = ijson.items(config_file, 'databases.item')
            config_data = {item['id']: item for item in databases}
        
        for key, value in config_data.items():
            value['connection_string'] = connection_string
        return config_data

