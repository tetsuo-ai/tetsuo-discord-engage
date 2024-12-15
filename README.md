# tetsuo-discord-engage
# discord.py doesn't like newer versions of python, stick with 3.11

INSTALL:
```
 git clone https://github.com/tetsuo-ai/tetsuo-discord-engage
 cd tetsuo-discord-engage/
 python3.11 -m venv .venv
 source .venv/bin/activate
 pip install -r requirements.txt
 playwright install --with-deps --only-shell
 
 .env only needs DISCORD_TOKEN=[TOKEN_GOES_HERE]

```
EXAMPLE:
```
To start bot:
python3 main.py
