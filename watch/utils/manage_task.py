from watch import app, task_pool, lock
from datetime import datetime
from uuid import uuid4


def add_task(endpoint, user_name, target, parameters, chat_id=None, reply_to_message_id=None, period=None):
    uuid = uuid4().hex
    task_pool[uuid] = [endpoint                                                  # 0  task func name
                       , getattr(app.view_functions[endpoint], 'title', 'Task')  # 1  task name
                       , datetime.now()                                          # 2  created at
                       , user_name                                               # 3  user
                       , target                                                  # 4  target
                       , None                                                    # 5  last call
                       , 0                                                       # 6  execs
                       , 'wait'                                                  # 7  state
                       , parameters                                              # 8  params dict
                       , period or app.view_functions[endpoint].period           # 9  period
                       , chat_id                                                 # 10 chat to send message
                       , reply_to_message_id                                     # 11 reply to message
                       , None]                                                   # 12 task runtime data

    return uuid


def cancel_task(uuid):
    try:
        del task_pool[uuid]
    except KeyError:
        pass


def reset_task(uuid=None):
    with lock:
        if uuid:
            try:
                if task_pool[uuid][7].endswith('error'):
                    task_pool[uuid][7] = 'wait'
            except KeyError:
                pass
        else:
            for task in task_pool.values():
                if task[7].endswith('error'):
                    task[7] = 'wait'
