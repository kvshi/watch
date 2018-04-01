from cx_Oracle import DatabaseError, OperationalError
from watch import app, task_pool, notification_pool, lock
from watch.utils.chat_bot import send_message
import threading
from time import sleep
from datetime import datetime, timedelta


class Worker(threading.Thread):
    def __init__(self):
        super(Worker, self).__init__()
        self.active = True

    def run(self):
        while self.active:
            with lock:
                active_tasks = tuple(k for k in task_pool.keys() if task_pool[k][7] == 'wait')
            for task in active_tasks:
                with lock:
                    if not task_pool.get(task):
                        continue
                    if task_pool[task][5]:
                        pt = task_pool[task][9][-1:]
                        pv = task_pool[task][9][:-1]
                        next_call = task_pool[task][5] + timedelta(weeks=int(pv) if pt == 'w' else 0
                                                                   , days=int(pv) if pt == 'd' else 0
                                                                   , hours=int(pv) if pt == 'h' else 0
                                                                   , minutes=int(pv) if pt == 'm' else 0
                                                                   , seconds=int(pv) if pt == 's' else 0)
                        if next_call > datetime.now():
                            continue
                    task_pool[task][7] = 'run'
                try:
                    finished, message = app.view_functions[task_pool[task][0]](task)
                    r = 0
                    if message:
                        notification_pool.appendleft((datetime.now()
                                                      , task_pool[task][3]
                                                      , task_pool[task][1]
                                                      , ', '.join(str(v) for v in task_pool[task][8].values())
                                                      , message))
                        if task_pool[task][10]:
                            message_parameters = {'chat_id': task_pool[task][10]
                                                  , 'text': message
                                                  , 'parse_mode': 'HTML'}
                            if task_pool[task][11]:
                                message_parameters['reply_to_message_id'] = task_pool[task][11]
                            r = send_message(message_parameters)
                    if finished:
                        del task_pool[task]
                    else:
                        task_pool[task][5] = datetime.now()
                        task_pool[task][6] += 1
                        task_pool[task][7] = 'wait' if r == 0 else 'msg error'
                except (DatabaseError, OperationalError) as e:
                    app.logger.error(f'{task} {e.args[0].message}')
                    task_pool[task][7] = 'db error'
            sleep(app.config['WORKER_FREQ_SEC'])

    def shutdown(self):
        self.active = False
