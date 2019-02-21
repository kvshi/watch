# Watch
![Python 3.6](https://img.shields.io/badge/python-3.6-brightgreen.svg)
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/8d35de9129b4497385b6aa7446893038)](https://www.codacy.com/app/dtbx/watch?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=alx-sdv/watch&amp;utm_campaign=Badge_Grade)

Is another try to make a monitoring of the Oracle Database more handy.

The Watch created for people who have to deal with long-term sql queries. In other words, if you are data warehouse developer or admin, it could be helpful.

Oracle DB has an infinity number of system views which may give answers for questions like:
* Why does my query run slow?
* Which user consumes too much resources?
* What is going on my database right now?
* How many rows were inserted in my table?
* and many many others.

The problem is you have no GUI to work with these views. So, you retype the same query every time you need some DB statistics.
This app provides easy way to wrap a query to a web report and share it with your team.
Of course, it is actual if your company don't want to buy Oracle Enterprise Manager.

### Features
* Flask-based. Minimum dependencies. Easy to customize.
* Permanent links to all reports and objects can be sent to other people or can be saved to favourites in your browser.
* Defining permitted targets to each user.
* Background monitoring tasks.
* Interacting through Telegram chat (notifications & commands).

![Report example](/docs/top_activity.png) ![Report example](/docs/longops.png)

### Requirements
* Python 3.6+
* Flask
* cx_Oracle
* Pygal

### Installation
First thing you should know: cx_Oracle needs Oracle Instant Client. Installing it could be a bit painful, please read cx_Oracle guide.

Then create a new virtual environment if you don't want to mess your python instance.

Install The Watch:
`pip install git+https://github.com/alx-sdv/watch.git`

### Settings
Open `/config/config.py` and follow instructions inside.

Please check your database account privileges. By default the Watch is not going to modify any data, but for heaven's sake make all accounts read-only. 

Also restrict an access to critical business data if you find it necessary. All you need is to read system statistic views.

### Launch
Use `run.py` to run the application on internal web-server provided by Flask.

It is not recommended for production, so you can attach app object from `run.py` to your favourite wsgi server.

See the official Flask docs, it contains a lot of scenarios to deploy flask-based application.

### Usage
Some popular system views already included as reports:

Report | View
------ | ----
Top activity | Inspired by OEM chart view, will be improved in further versions.
Top SQL | v$sqlarea
SQL monitor | v$sql_monitor
Session monitor | v$session
Plans cache | v$sql_plan
Top object waits | v$active_session_history
Long operations | v$session_longops
Temp usage | v$sort_usage
Undo usage | v$session
Rman status | v$rman_status
DML locks | dba_dml_locks
Workload | Oracle DB reports, generated by dbms_workload_repository functions.
Objects | all_objects
Table stats | all_tab_statistics
Index stats | all_ind_statistics
Segments | dba_segments
Segment usage | v$segment_statistics
Tabspace usage | dba_free_space
Tabspace fragmentation | dba_segments
Users | dba_users
Synonyms | dba_synonyms
Privileges | dba_tab_privs
Tab partition count | Helps to find extremely partitioned tables.
Ind partition count | Helps to find extremely partitioned indexes.
Modifications | all_tab_modifications
Query text | v$sql
Query plan | dbms_xplan.display_cursor
Query waits | v$active_session_history
Query long ops | v$session_longops
Query plan stats | v$sql_plan_monitor
Monitor report | dbms_sqltune.report_sql_monitor
Table columns | all_tab_columns
Table indexes | all_indexes
Table partitions | all_tab_partitions
DDL | dbms_metadata.get_ddl
Row count | To count rows grouped by specified date.

And some tasks:

Task | Description
---- | -----------
Wait for execution | Notify when specified query will be finished.
Wait for session | Notify when specified session will be inactive (for example, when the client has got first portion of rows). 
Wait for status | Notify when specified table will contain specified row.
Wait for heavy | Notify if some query executes too long or consumes too much temp space.
Temp usage | Notify when free temp space ends up.
Tabspace usage | Notify when some tablespace becomes full.
Expired users | Notify if some user account expires.
Uncommitted transactions | Notify when somebody has an inactive session containing locks.
Wait for queued | Notify if some query has been queued too long.
Wait for recycled | Notify to take out the trash.
Check segment size | Notify when segment (table, index, ...) size has reached specified threshold. 
Check resource usage | Notify when some of server resource usage reached specified threshold
Wait for SQL error | Notify if some query has failed. It is based on sql monitor, but a trigger on servererror is much better.
Ping target | Notify if ping to the target has failed.
Check redo switches | Notify if redo logs switch too often.
Check logs deletion | Notify if too many archived redo logs wait for deletion.
Wait for zombie | Notify if some sessions do nothing but still are active.
Check job status | Notify if Oracle Job became broken.

All functions were tested on Oracle 11.2 & 12.1 (single instance mode).

### Making your own view
There is two ways to add your code to the app:
* Create a regular flask-view, and do everything you want inside it.
* Use some provided conveniences.

Let's open `/views/target.py` and go to a function named `get_target_objects`.
```python
@app.route('/<target>/objects')
@title('Objects')
@template('list')
@snail()
@select("all_objects")
@columns({"owner": 'str'
         , "object_name": 'str'
         , "subobject_name": 'str'
         , "object_type": 'str'
         , "created": 'datetime'
         , "last_ddl_time": 'datetime'
         , "status": 'str'})
@default_filters("object_type = 'TABLE' and object_name like '%%'")
@default_sort("object_name, subobject_name")
def get_target_objects(target):
    return render_page()
```
As you can see this view does not contain any specific python code.

How it works:
* You click "OBJECTS" item in the main menu.
* Your request maps to get_target_objects: `@app.route('/<target>/objects')`
* The server returns the view page. The page is generated on "standard" template: `@template('list')`.
* The page contains these controls:
  * "Filter" field with default value: `@default_filters("object_type = 'TABLE' and object_name like '%%'", ..., ...)`
  * "Sort" field with default value: `@default_sort("object_name, subobject_name")`
  * Draggable labels for columns names: `@columns({"owner": 'str' ... '})`. Use in for sorting and filtering. Note that both values will be parsed before sending to database. See the main page of the app for more information.
  * Draggable labels of all preset filters.
  * "Run" button.
* You press "Run" button.
* The app receives your request with "do" parameter, and executes `get_target_objects`.
* get_target_objects call render_page function.
* render_page parses params, builds a sql query to specified table: `@select("all_objects")`.
* render_page sends the query do DB, then renders "standard" template with fetched data.
* get_target_objects returns rendered template to your browser.

You can make your own view in the same way. 
* If any additional steps needed, use `execute` function from `/utils/oracle.py` inside your view to send custom query to DB.
* To render "non-standard" template use `render_template` function from Flask.
* Put your view in a new python file into `/ext` folder.
* Add the view name in the menu structure by importing it from `config.menu` and setting a new key. `@title('<Choose a name>')` will be displayed.

### How to register a bot
* Add the BotFather to contacts and follow its instructions to create a bot.
* Send `/id` command to your new bot, it will show your account id.
* Set the bot name and token in local_config.py.
* Put your id into account properties (see `USERS` dict).
* Now you are able to get notifications an send some commands to the application.

### Making you own task
The Watch task looks like a view, the difference is: it's code will never be executed in http request context.

Open `/views/task.py` and find `wait_for_execution` function:
* `@template('task')` lets the app know that `wait_for_execution` is not a report-view.
* `@period('1m')` defines default execution frequency.
* `@command('/wait')` is a command name that can be sent from a chat to register a new instance of the task.
* The task always must return two params: 
  * The first one is a flag of completion (if true, the task will be deleted from the task queue).
  * The second is a message that should be sent to a subscriber.

### Contributing
Feel free to submit a pull request to improve or extend an existing functionality or just open an issue.

### Road map
* `usage` New data types 'bytes' and 'msecs' for pretty formatting and filtering (1.1Gb, 00:00:21.000, 1.1h).
* `usage` Ability to download report result or send it by e-mail.
* `usage` Easy copying to clipboard.
* `usage` User-specific report settings, recent views history.
* `general` Review all sql code.
* `usage` More detailed error messages from parser.
* `usage` Param parser should supports braces and IN operator.
* `usage` New value directive t(trunc). -t10d for date fields.
* `usage` Display elapsed time for heavy reports.
* `usage` Ability to cancel heavy view directly from it's form. Not only from administration page.
* `general` Logging more user activity, add user name to log message.
* `general` Make a logo.
* `usage` Restrict registering duplicating tasks.
* `usage` Sign up via Telegram.
* `usage` Improve chat commands, use buttons, instant views and other fantastic features.
* `report` Monitor for specified part of active sql text.
* `report` Which queries has been executed too often.
* `task` Improve "Wait for status" task, consider backdating inserts.
* `usage` Generate script for all necessary grants.
* `report` Add measures, filters, date frame to "Top activity".
* `usage` Add an optional numeric argument to @auto() which will refresh a report each N minutes automatically.
* `report` Go deeper to [ASH](https://www.slideshare.net/jberesni/ash-architecture-and-advanced-usage-rmoug2014-36611678).
* `security` Encrypt app data.
* `security` Add CSRF protection.
* `usage` Ability to set hyperlinks via decorators. Add useful links to existing views.
* `report` Make a forecast for disk space usage.
* `report` Find unused indexes, partitions, tables.
* `general` Improve styles, IE support.
* `general` Fix spelling inaccuracies.
