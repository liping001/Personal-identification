#!/bin/bash
export FLASK_DEBUG=0
export FLASK_APP=main.py

export PORT=5001
[ $# -gt 0 ] && PORT=$1
if [ "$PORT" -eq "5002" ]; then
	export config_file_name=config2
elif [ "$PORT" -eq "5003" ]; then
	export config_file_name=config3
fi

flask run --port=$PORT --host=0.0.0.0
