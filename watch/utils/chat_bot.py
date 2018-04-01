from watch import app
from watch.utils.parse_args import parse_command
from watch.utils.manage_task import add_task
from watch.utils.manage_message import send_message, get_updates, t_link
import threading
from json import loads


class Bot(threading.Thread):
    def __init__(self):
        super(Bot, self).__init__()
        self.active = True
        self.offset = 0

    def run(self):
        while self.active:
            try:
                updates = loads(get_updates(self.offset).read().decode('utf-8'))
                if not updates.get('ok', False):
                    app.logger.error(updates.get('description', 'Unknown bot error (getUpdates)'))
                    break
                for update in updates['result']:
                    self.offset = update['update_id'] + 1
                    if not update.get('message'):
                        continue
                    if not update['message'].get('text'):
                        continue
                    if update['message']['text'] == '/id':
                        send_message({'chat_id': update['message']['chat']['id']
                                      , 'text': f'id = {update["message"]["chat"]["id"]}.'})
                        continue

                    user_list = tuple(k for k, v in app.config['USERS'].items()
                                      if v[1] and v[1] == update['message']['from']['id'])
                    user_name = None
                    if len(user_list) == 1:
                        user_name = user_list[0]

                    if not user_name:
                        if update['message']['chat']['id'] in app.config['BOT_CHAT_LIST'].keys():
                            send_message({'chat_id': update['message']['chat']['id']
                                          , 'text': f'I don\'t know who you are.'
                                                    f' Please open @{app.config["BOT_NAME"]} and send me /id command.'
                                                    f' Then forward my reply to system administrator.'})
                        continue
                    if update['message']['text'] == '/help':
                        send_message({'chat_id': update['message']['chat']['id']
                                      , 'text': 'God help you.'})
                        continue
                    rr, endpoint, target, parameters = parse_command(update['message']['text'])
                    if rr:
                        send_message({'chat_id': update['message']['chat']['id']
                                      , 'text': f'Incorrect value: {rr}.'})
                        continue
                    if target and target not in app.config['USERS'][user_name][2]:
                        send_message({'chat_id': update['message']['chat']['id']
                                      , 'text': f'Target "{target}" does not exist or not allowed.'})
                        continue
                    uuid = add_task(endpoint
                                    , user_name
                                    , target
                                    , parameters
                                    , update['message']['chat']['id']
                                    , update['message']['message_id'])
                    send_message({'chat_id': update['message']['chat']['id']
                                  , 'text': '{} added.'.format(t_link(f'get_app?task_id={uuid}', 'Task'))
                                  , 'parse_mode': 'HTML'})
            except Exception as e:
                app.logger.error(e, exc_info=True)
                break

    def shutdown(self):
        self.active = False
