c = get_config()
c.Application.log_level = 'CRITICAL'
c.ServerApp.use_redirect_file = False
c.ServerApp.custom_display_url = 'http://127.0.0.1:8888/lab'
# set the notebook ip to the Docker container ip
c.ServerApp.allow_origin = 'host.docker.internal'
c.ServerApp.ip = '0.0.0.0'
c.ServerApp.port = 8888
