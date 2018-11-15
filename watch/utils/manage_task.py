from watch import app, lock
from datetime import datetime
from uuid import uuid4
from pickle import load as unpickle, dump as pickle, HIGHEST_PROTOCOL
from os import path
from pprint import pformat


class Task:
    def __init__(self, uuid=None, endpoint=None, name=None, create_date=None, user_name=None, target=None,
                 last_call=None, execs=None, state=None, parameters=None, period=None, chat_id=None,
                 reply_to_message_id=None, data=None, optional=None):
        self.uuid = uuid or uuid4().hex
        self.endpoint = endpoint
        self.name = name or getattr(app.view_functions[endpoint], 'title', 'Task')
        self.create_date = create_date or datetime.now()
        self.user_name = user_name
        self.target = target
        self.last_call = last_call
        self.execs = execs or 0
        self.state = 'wait' if (state is None or state == 'run') else state  # if an exception has happened
        self.parameters = parameters
        self.period = period or app.view_functions[endpoint].period
        self.chat_id = chat_id
        self.reply_to_message_id = reply_to_message_id
        self.data = data
        self.optional = optional

    def to_list(self):
        return [self.uuid
                , self.endpoint
                , self.name
                , self.create_date
                , self.user_name
                , self.target
                , self.last_call
                , self.execs
                , self.state
                , self.parameters
                , self.period
                , self.chat_id
                , self.reply_to_message_id
                , self.data
                , self.optional]

    def __str__(self):
        return pformat(self.__dict__, width=160).replace('\'', '')


def cancel_task(task_pool, uuid):
    try:
        del task_pool[uuid]
    except KeyError:
        pass


def reset_task(task_pool, uuid=None):
    with lock:
        if uuid:
            try:
                if task_pool[uuid].state.endswith('error'):
                    task_pool[uuid].state = 'wait'
            except KeyError:
                pass
        else:
            for task in task_pool.values():
                if task.state.endswith('error'):
                    task.state = 'wait'


def store_tasks(task_pool):
    with lock:
        if app.config['STORE_FILE']:
            with open(app.config['STORE_FILE'], 'wb') as f:
                pickle({k: v.to_list() for k, v in task_pool.items()}, f, HIGHEST_PROTOCOL)
                return True
        else:
            return False


def restore_tasks():
    if app.config['STORE_FILE'] and path.exists(app.config['STORE_FILE']):
        with open(app.config['STORE_FILE'], 'rb') as f:
            return {k: Task(*v) for k, v in unpickle(f).items()}
    return {}
