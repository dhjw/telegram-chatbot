# Telegram Chatbot
OpenAI-compatible and Gemini-native LLM queries for private chat, groups and channels on Telegram.

## Setup
- Clone the repo `git clone https://github.com/dhjw/telegram-chatbot && cd telegram-chatbot`
- Set up and enter a virtualenv (optional). `python -m venv venv` then `source ./venv/bin/activate` (Linux) or `.\venv\Scripts\activate` (Windows)
- Install requisites to the current environment  `pip install -r requirements.txt`
- Get a bot token from [@Botfather](https://t.me/BotFather)
- Get API keys from [Google](https://aistudio.google.com), [OpenAI](https://platform.openai.com/) and [xAI](https://console.x.ai/) (you will need credits except for Google; note OpenAI's expire in a year and mini models are cheap so just get $5 to start)
- Copy `config.example.json` to `config.json` and configure it
- Search for your bot and add it to your groups/channels (click profile name > Add to group), or open a private chat
- When happy with the active groups, use BotFather's `/setjoingroups` command to prevent the bot being added to more
- Use the hidden `/id` command to find out the `chat_id` for each chat. Add them to `allow_chat_ids` in config.json in an array, e.g. `[-12312312, 123123],`
- When you restart the bot all other chats will be ignored
- Be careful not to break the strict json config file