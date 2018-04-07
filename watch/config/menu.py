menu_tree = {'get_user': ['user', []]
             , 'get_target': ['target'
                              , ['get_top_activity'
                                 , 'get_top_sql'
                                 , 'get_sql_monitor'
                                 , 'get_session_monitor'
                                 , 'get_plans_cache'
                                 , 'get_target_waits'
                                 , 'get_target_long_ops'
                                 , 'get_temp_usage'
                                 , 'get_rman_status'
                                 , 'get_dml_locks']]
             , 'get_target_snapshot': ['target'
                                       , ['get_awr_report'
                                          , 'get_ash_report'
                                          , 'get_advisor_tasks'
                                          , 'get_advisor_findings'
                                          , 'get_alert_history'
                                          , 'get_outstanding_alerts']]
             , 'get_target_objects': ['target'
                                      , ['get_table_stats'
                                          , 'get_index_stats'
                                          , 'get_segment_usage'
                                          , 'get_tablespace_usage'
                                          , 'get_ts_fragmentation'
                                          , 'get_users'
                                          , 'get_privileges'
                                          , 'get_too_partitioned'
                                          , 'get_modifications']]
             , 'get_query': ['query'
                             , ['get_query_text'
                                , 'get_query_plan'
                                , 'get_query_waits'
                                , 'get_query_long_ops'
                                , 'get_query_plan_stats'
                                , 'get_query_report']]
             , 'get_table': ['table'
                             , ['get_table_columns'
                                , 'get_table_indexes'
                                , 'get_table_partitions'
                                , 'get_table_ddl'
                                , 'get_row_count']]
             , 'get_task': ['target', ['wait_for_execution'
                                       , 'wait_for_status'
                                       , 'wait_for_heavy'
                                       , 'wait_for_temp'
                                       , 'wait_for_ts'
                                       , 'wait_for_expiry'
                                       , 'wait_for_uncommitted']]
             , 'get_ext': ['target', []]
             , 'get_app': ['user'
                           , ['get_notifications'
                              , 'get_error_log'
                              , 'stop_server']]
             , 'logout': ['user', []]}
