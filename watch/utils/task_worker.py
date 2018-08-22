from cx_Oracle import DatabaseError, OperationalError
from watch import app, task_pool, notification_pool, lock
from watch.utils.chat_bot import send_message
from watch.utils.parse_args import get_offset
import threading
from time import sleep
from datetime import datetime


class Worker(threading.Thread):
    def __init__(self):
        super(Worker, self).__init__()
        self.active = True

    def run(self):
        while self.active:
            with lock:
                active_tasks = tuple(v for v in task_pool.values() if v.state == 'wait')
            for task in active_tasks:
                with lock:
                    if not task_pool.get(task.uuid):
                        continue
                    if task.last_call:
                        pt = task.period[-1:]
                        pv = task.period[:-1]
                        next_call = task.last_call + get_offset(pv, pt)
                        if next_call > datetime.now():
                            continue
                    task.state = 'run'
                try:
                    finished, message = app.view_functions[task.endpoint](task)
                    r = 0
                    if message:
                        notification_pool.appendleft((datetime.now()
                                                      , task.user_name
                                                      , task.name
                                                      , ', '.join(str(v) for v in task.parameters.values())
                                                      , message))
                        if task.chat_id and not app.config['MUTE_MESSAGES']:
                            message_parameters = {'chat_id': task.chat_id
                                                  , 'text': message
                                                  , 'parse_mode': 'HTML'}
                            if task.reply_to_message_id:
                                message_parameters['reply_to_message_id'] = task.reply_to_message_id
                            r = send_message(message_parameters)
                    if finished:
                        del task_pool[task.uuid]
                    else:
                        task.last_call = datetime.now()
                        task.execs += 1
                        task.state = 'wait' if r == 0 else 'msg error'
                except (DatabaseError, OperationalError) as e:
                    app.logger.error(f'{task.uuid} {e.args[0].message}')
                    task.state = 'db error'
            sleep(app.config['WORKER_FREQ_SEC'])

    def shutdown(self):
        self.active = False
