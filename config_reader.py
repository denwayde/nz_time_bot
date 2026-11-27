from pydantic import BaseSettings, SecretStr


class Settings(BaseSettings):
    # It is recommended to use SecretStr instead of str
    # for sensitive data such as the bot token
    bot_token: SecretStr

    # Telegram ID of the administrator (the /users and /send_all commands,
    # and receiving messages from users)
    admin_id: int = 1949640271

    # Nested class with extra instructions for the settings
    class Config:
        # Name of the file the values are read from
        # (relative to the current working directory)
        env_file = '.env'
        # Encoding of the file being read
        env_file_encoding = 'utf-8'


# When this file is imported, the config object is immediately created
# and validated; it can then be imported from other places
config = Settings()
# config.bot_token.get_secret_value()
