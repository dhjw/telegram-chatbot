# Telegram Chatbot
OpenAI-compatible and Gemini-native LLM queries for groups, channels and private chats on Telegram.

## Setup
- Clone the repo into a working folder `git clone https://github.com/dhjw/telegram-chatbot && cd telegram-chatbot`
- Set up and enter a virtualenv (optional). `python -m venv venv` then `source ./venv/bin/activate` (Linux) or `.\venv\Scripts\activate` (Windows)
- Install requisites to the current environment  `pip install -r requirements.txt`
- Get a bot token from [@Botfather](https://t.me/BotFather)
- Get API keys from [Google](https://aistudio.google.com), [OpenAI](https://platform.openai.com/) and [xAI](https://console.x.ai/) (you will need credits except for Google; note OpenAI's expire in a year and mini models are cheap so just get $5 to start)
- Copy `config.example.json` to `config.json` and configure it
- Search for your bot and add it to your groups/channels (click profile name > Add to group), or open a private chat
- When happy with the active groups, use BotFather's `/setjoingroups` command to prevent the bot being added to more
- Use the hidden `/id` command to find out the `chat_id` for each chat. Add them to `allow_chat_ids` in config.json in an array, e.g. `[-12312312, 123123],`
- When you restart the bot all other chats will be ignored
- Be careful not to break the strict JSON config file

## Run
There's a few ways to do it.
 - Activate the venv, as in Setup, and run `python ./bot.py`, or make it executable `chmod +x ./bot.py` and run it directly `./bot.py`
 - Run it from the venv without activating `/path/to/venv/bin/python /path/to/bot.py`
 - If you're not using a venv, run it with the system python3 or make it executable and run it

## Update
Clone the repo, copy your config.json and venv into it and see if it still runs, I guess!

```
cd /path/to/parent
mv ./telegram-chatbot ./telegram-chatbot.old
git clone https://github.com/dhjw/telegram-chatbot
cp ./telegram-chatbot.old/config.json ./telegram-chatbot
cp -r ./telegram-chatbot.old/venv ./telegram-chatbot/venv
```

## TODO, maybe
- Gemini grounding + live search (big free-tier)
- Grok 3 live search (expensive)
- Media input support
