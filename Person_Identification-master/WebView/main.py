# main.py
# 4/11 6:55pm SH & JD - Work realated with camera link ajax loding
# 4/11 7:36pm JD - work related to the prediction indicator
# 4/13 8:51pm JL - fixed a small bug in the querry of getCameraListWithPredictedMotion()
# 4/15 5:05pm LH - added method to load activity from database and added route to sent it back to the browser
# 4/16 6:34pm JD - updated query to exclude activity where the expected person has arrived
# 4/18 8:00pm JL - added a reset method for resetting the activity table

from flask import Flask, jsonify, render_template, Response, jsonify,json, redirect
from flaskext.mysql import MySQL
import time, socket, sys
import os
import configparser
sys.path.append("..") #Add my parent folder so that I can get access to shared classes
from shared.CameraDbRow import CameraDbRow
from shared.ActivityDbRow import ActivityDbRow

# read in the contents of the config file so we know how to find the database
config = configparser.ConfigParser()
config.read('config')
# configure the mysql database connection and the flask framework
mysql = MySQL()
app = Flask(__name__)
app.config['MYSQL_DATABASE_USER'] = config['DB']['user']
app.config['MYSQL_DATABASE_PASSWORD'] = config['DB']['password']
app.config['MYSQL_DATABASE_DB'] = config['DB']['schema']
app.config['MYSQL_DATABASE_HOST'] = config['DB']['host']

#clear the camera and tracking tables on each restart to make demos easier
mysql.init_app(app)
conn = mysql.connect()
cursor = conn.cursor()
cursor.execute("delete from tracking")
cursor.execute("delete from camera")
conn.commit()

# connect ot the database and read in all the camera info
def getCameraList():
	global mysql
	cursor = mysql.connect().cursor()
	cursor.execute("SELECT * from camera order by id")
	data = cursor.fetchall()
	camera_list=[]
	# these lists contain camera ids for green (motion detected) cameras or yellow (predicted arrival) cameras
	cameras_with_motion = getCameraListWithMotion()
	cameras_with_predicted_motion = getCameraListWithPredictedMotion()

	#loop of the data from the db and create each CameraDbRow instance and add to the list
	for d in data:
		c = CameraDbRow(d)
		camera_list.append(c)
		if c.getID() in cameras_with_motion:
			c.setHasMotion(True)
		if c.getID() in cameras_with_predicted_motion:
			c.setHasPredictedMotion(True)
	return camera_list

#get the list of ids of cameras with motion happening
def getCameraListWithMotion():
	global mysql
	cursor = mysql.connect().cursor()
	cursor.execute("SELECT distinct camera_id from tracking where end_time is null and start_time > DATE_SUB(current_timestamp, INTERVAL 5 MINUTE) order by camera_id desc")
	data = cursor.fetchall()
	return [c for sublist in data for c in sublist]

#get the list of ids of cameras with predicted arrivals pending
def getCameraListWithPredictedMotion():
	global mysql
	cursor = mysql.connect().cursor()
	cursor.execute("SELECT distinct a.next_camera_id from tracking a left join tracking b on a.next_camera_id = b.camera_id and a.label = b.label where a.next_camera_id is not null and b.camera_id is null and a.has_arrived = 'F' and a.end_time > DATE_SUB(current_timestamp, INTERVAL 1 MINUTE)")
	data = cursor.fetchall()

	# ugly syntax for collapsing list of lists into a simple list of ids
	# [[1], [2], [3]] becomes [1, 2, 3]
	return [c for sublist in data for c in sublist]

#get the activity data form the database to render at the foot of the page
def getActivityList():
	global mysql
	cursor = mysql.connect().cursor()
	cursor.execute("SELECT id, label, start_time, end_time, camera_id, next_camera_id, has_arrived from tracking order by start_time desc limit 20")
	activity_list = []
	data = cursor.fetchall()
	for d in data:
		a = ActivityDbRow(d)
		activity_list.append(a)
	return activity_list

#flask route for the main index page
@app.route('/')
def index():
	camera_list = getCameraList()
	# get our ip to render on the main view so it's easier to setup each videoController ( they all need the ip of the database )
	ip=socket.gethostbyname(socket.gethostname())
	return render_template('index.html', camera_list=camera_list, database_ip=ip) 

# route for viewing the feed of a specific camera by it's "id"
@app.route('/view_camera/<int:camera_id>')
def view_camera(camera_id):
	cursor = mysql.connect().cursor()
	cursor.execute("SELECT * from camera where id = " + str(camera_id))
	data = cursor.fetchone()
	#we load the details for the specified camera and pass on to be rendered by the view.html template
	return render_template('_view.html', camera_id=camera_id, data=data)
	
#Flask route for polling by Jquery to update the activity_list html
@app.route('/activity')
def activity():
	activity_list = getActivityList()
	return render_template('_activity.html', activity_list=activity_list)

#route for rendering the camera link list including the indicators
@app.route('/cameras')
def cameras():
	camera_list = getCameraList()
	return render_template('_cameras.html', camera_list=camera_list)

#route for home
@app.route('/home')
def home():
	return render_template('_home.html')

#a link for resetting ( clearing ) the tracking activity
@app.route('/reset')
def reset():
        global mysql
        conn = mysql.connect()
        cursor = conn.cursor()
        cursor.execute("delete from tracking")
        conn.commit()
        return redirect("/")