from watch import app
from urllib.request import urlopen
from urllib.parse import urlencode
from json import loads
from html import escape


def send_message(parameters):
    try:
        with urlopen('{}{}{}/{}?{}'.format(app.config['BOT_SIMPLE_PROXY']
                                         , app.config['BOT_PATH']
                                         , app.config['BOT_TOKEN']
                                         , 'sendMessage'
                                         , urlencode(parameters))) as r:
            message = loads(r.read().decode('utf-8'))
            if not message.get('ok', False):
                app.logger.error(message.get('description', 'Unknown bot error (sendMessage)'))
                return -1
        return 0
    except Exception as e:
        app.logger.error(f'messaging error: {e}')
        return -1


def get_updates(offset):
    return urlopen('{}{}/{}?{}'.format(app.config['BOT_PATH']
                                       , app.config['BOT_TOKEN']
                                       , 'getUpdates'
                                       , urlencode({'offset': offset
                                                    , 'timeout': app.config['BOT_TOKEN']})))


def t_esc(s):
    return escape(s)


def t_link(url_part, text):
    return f'<a href="http://{app.config["SERVER_NAME"]}/{t_esc(url_part)}">{t_esc(text)}</a>'


def t_pre(text):
    return f'<pre>{t_esc(text)}</pre>'


def t_italic(text):
    return f'<i>{t_esc(text)}</i>'
