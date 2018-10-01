# main.py
# 4/11 6:55pm SH & JD - added extra call to updateDetailInDb()

import sys
sys.path.append("..")
from flask import Flask, request, render_template, Response
from flaskext.mysql import MySQL
from camera import VideoCamera
import cv2
import time, os, threading, socket
from flask_cors import CORS
import configparser
from shared.CameraDbRow import CameraDbRow
import atexit

config_file='config'
if 'config_file_name' in os.environ:
	config_file=os.environ['config_file_name']

#read in parameters form the config file
config = configparser.ConfigParser()
config.read(config_file)
# set up flask and mysql
app = Flask(__name__)
CORS(app)
mysql = MySQL()
app.config['MYSQL_DATABASE_USER'] = config['DB']['user']
app.config['MYSQL_DATABASE_PASSWORD'] = config['DB']['password']
app.config['MYSQL_DATABASE_DB'] = config['DB']['schema']
app.config['MYSQL_DATABASE_HOST'] = config['DB']['host']
mysql.init_app(app)

#hacky way to get my own ip address - connect to mysql and then disconnect
def get_ip_address():
	global config
	testIp = config['DB']['host']
	testPort = 3306
	#Only connect to the db as the test Ip when it's not localhost.  If it's localhost, then use googles dns.  
	#We don't always use googles dns because we might not have an internet connection.
	if testIp == 'localhost' or testIp == '127.0.0.1':
		print('using google dns')
		testIp = '8.8.8.8'
		testPort = 80

	#initialize ip to what the ip found using this method
	ip = socket.gethostbyname(socket.gethostname())
	print(ip)
	#then try a more advanced method because it's more likely to find the right ip
	try:
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		s.connect((testIp, testPort))
		ip = s.getsockname()[0]
		s.close()
	except:
		None

	return ip

#in order to facilitate running more than one VideoController on the same computer, 
#this method will allow for a flexible port assignment
def get_port():
	port = "5001"
	if 'PORT' in os.environ:
		port = os.environ['PORT']
	return port

#Called to store specific details about this camer in the database
def updateDetailsInDb():
	global mysql, config
	cameraDetails = None
	try:
		i=0
		cameraDetails = CameraDbRow()
		cameraDetails.setID(config['APP']['camera_id'])
		cameraDetails.setIP("%s:%s" % (get_ip_address(), get_port()))
		if 'left_camera_id' in config['APP']:
			cameraDetails.setLeftCameraID(config['APP']['left_camera_id'])
		if 'right_camera_id' in config['APP']:
			cameraDetails.setRightCameraID(config['APP']['right_camera_id'])
		cameraDetails.setIsOnline(True)
		conn = mysql.connect()
		cursor = conn.cursor()
		#see if this camera is already in the db and update it instead of inserting it
		cursor.execute(cameraDetails.getSelectStatement())
		data = cursor.fetchone()
		if data:
			cursor.execute(cameraDetails.getUpdateStatement())
		else:
			cursor.execute(cameraDetails.getInsertStatement())
		conn.commit()
	except:
		print("Unexpected error:", sys.exc_info())
	return cameraDetails

#global variables to hold onto a reference to the camera and camera details 
camera=None
cameraDetails=None

#called by the shutdown flask route to stop the video camera hardware
def shutdownCamera():
	global mysql, camera
	try:
		cameraDetails.setIsOnline(False)
		conn = mysql.connect()
		cursor = conn.cursor()
		cursor.execute(cameraDetails.getUpdateStatement())
		conn.commit()
		if camera:
			camera.stop()
			camera = None
	except:
		print(sys.exc_info())

#a hook to try and shutdown the camer if the video controller exits ( doesn't seem to work on windows )
atexit.register(shutdownCamera)

#during startup we update the camera details in the database and return a reference to store for later use by this flask application
cameraDetails = updateDetailsInDb()

#if this happens, we have a camera id collision and this camera id is already running on the network
if not cameraDetails:
	print("Not able to start video controller. Make sure this controller has a unique camera ID in config.")
	exit()

def countCameras():
	global config, mysql, camera, cameraDetails
	count = 0
	for i in range(0, 3):
		try:
			x = cv2.VideoCapture(int(i))
			if x.get(cv2.CAP_PROP_FPS) > 0:
				count+=1
		except:
			None
	return count

#a method called by flask to start the thread that manages the camera
def checkCamera():
	global config, mysql, camera, cameraDetails
	# this allows the method to be called more than once without starting an additional camera thread
	if not camera:
		cv2_index = config['APP']['cv2_index'] if 'cv2_index' in config['APP'] else 0
		camera = VideoCamera(cv2_index, cameraDetails, mysql)
		#the main camera loop in the start method is invoked here by the thread
		thread = threading.Thread(target=camera.start)
		thread.daemon = True
		thread.start()
	#this method also updates the database with current state of this camera instance
	updateDetailsInDb()

# a flask route for shutting down this camera hardware - called by the main ui when the user clicks the "on" link
@app.route('/shutdown')
def shutdown():
	shutdownCamera()
	return 'Camera stopped.'

# a flask route for starting this camera hardware - called by the main ui when the user clicks the "off" link
@app.route('/')
def index():
	checkCamera()
	return render_template('index.html') 

#serves up frames of video to the browser
def gen(camera):
	frame = None
	while True:
		if not frame:
			time.sleep(.3)
		frame = camera.get_frame()

		yield (b'--frame\r\n'
					 b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')

#entry point to get the video feed returned by the "gen" method
@app.route('/video_feed')
def video_feed():
	checkCamera()
	return Response(gen(camera),
										mimetype='multipart/x-mixed-replace; boundary=frame')
