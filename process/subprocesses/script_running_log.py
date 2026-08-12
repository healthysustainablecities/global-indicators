"""
Log script completion to sql.

This script assumes the specified postgresql database has already been
created.
"""


import psycopg2

# Import os environment variables and time set for configured analysis timezone
from ghsci import time


def script_running_log(config, script='', task='', start='', prefix=''):
    """Define script logging to study region database function."""
    db = config['db']
    db_host = config['db_host']
    db_port = config['db_port']
    db_user = config['db_user']
    db_pwd = config['db_pwd']
    # Initialise postgresql connection
    conn = psycopg2.connect(
        dbname=db, user=db_user, password=db_pwd, host=db_host, port=db_port,
    )
    curs = conn.cursor()
    date_time = time.strftime('%Y-%m-%d_%H%M')
    duration = (time.time() - start) / 60

    log_table = """
       -- If log table doesn't exist, its created
       CREATE TABLE IF NOT EXISTS script_log
       (
       script varchar,
       task varchar,
       datetime_completed varchar,
       duration_mins numeric
       );
       -- Insert completed script details
       INSERT INTO script_log VALUES ($${}$$,$${}$$,$${}$$,{});
       """.format(
        script, task, date_time, duration,
    )
    try:
        curs.execute(log_table)
        conn.commit()
        print(
            """\nProcessing completed at {}\n- Task: {}\n- Duration: {:04.2f} minutes\n""".format(
                date_time, task, duration,
            ),
        )
    except Exception as e:
        raise Exception(
            f'An error occurred: {e}\r\n(Has the database for this study region been created?)',
        )
    finally:
        conn.close()
