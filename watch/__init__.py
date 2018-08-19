from flask import Flask
import logging
from logging.handlers import RotatingFileHandler
from os import path, makedirs
from collections import deque
from threading import RLock

from urllib.request import ProxyHandler, build_opener, install_opener
from datetime import datetime

app = Flask(__name__)
app.config.from_pyfile(path.join(path.dirname(__file__), 'config', 'config.py'))
app.jinja_env.lstrip_blocks = True
app.jinja_env.trim_blocks = True

startup_time = datetime.now()
lock = RLock()
target_pool = {}
active_connections = {}
from watch.utils.manage_task import restore_tasks
task_pool = restore_tasks()
notification_pool = deque(maxlen=app.config['MAX_KEPT_NOTIFICATIONS'])

from watch.utils.task_worker import Worker
worker = Worker()

from watch.utils.chat_bot import Bot
bot = Bot()

import watch.views.error
import watch.views.application
import watch.views.task
import watch.views.target
import watch.views.top
import watch.views.workload
import watch.views.query
import watch.views.session
import watch.views.table
from watch.ext import *

title = {k: getattr(f, 'title', '') for k, f in app.view_functions.items()}
columns = {k: f.columns for k, f in app.view_functions.items() if hasattr(f, 'columns')}
for view in columns:
    columns[view] = {kf: vf for kf, vf in zip([kfs.strip().split(' ')[-1].split('.')[-1]
                                               for kfs in columns[view].keys()]
                                              , columns[view].values())}

from watch.utils.hook_request import validate_request, set_template_context, render_form
app.before_request(validate_request)
app.before_request(set_template_context)
app.before_request(render_form)

makedirs(path.join(path.dirname(__file__), 'logs'), exist_ok=True)
log_handler = RotatingFileHandler(path.join(path.dirname(__file__), 'logs', app.config['ERROR_LOG_NAME'])
                                  , maxBytes=app.config['LOG_MAX_BYTES']
                                  , backupCount=app.config['LOG_BACKUP_COUNT']
                                  , encoding='utf-8')
log_handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'
                                           , app.config['DATETIME_FORMAT']))
log_handler.setLevel(logging.ERROR)
app.logger.addHandler(log_handler)

if app.config['BOT_PROXY']:
    install_opener(build_opener(ProxyHandler(app.config['BOT_PROXY'])))

if app.config['WORKER_FREQ_SEC'] > 0:
    worker.start()

if app.config['BOT_POLLING_FREQ_SEC'] > 0:
    bot.start()
