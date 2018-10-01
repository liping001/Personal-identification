# camera.py
# 4/10 9:51pm LH - person tracking enhancement and some comment
# 4/13 8:49pm JL - modified label assgignment logic to reuse original label for the same person at new camera.
# 4/16 8:07pm JD - better detection of when someone leaves view and more accurate label reuse
# 4/17 9:00pm LH,JS - Fixed the get_label query to update the has_arrived correctly
# 4/18 7:46pm SH,JL - add better matching logic when additional people come into view of a camera
import sys
sys.path.append("..")
import cv2
import datetime
import numpy as np
import imutils
import time, os
from threading import Lock
from shared.CameraDbRow import CameraDbRow
from shared.ActivityDbRow import ActivityDbRow
import face_recognition

port=5001
if 'PORT' in os.environ:
	port=int(os.environ['PORT'])

def whichHalf(x):
	if x < 128:
		return 0
	else:
		return 1

# used as part of the prediction algorithm and also to help facility keeping the same person labeled correctly
def distance(p1, p2):
	# calculates the distance between two points
	return ((p2[0]-p1[0])**2+(p2[1]-p1[1])**2)**0.5

#an instance of this class manages the camera hardware
class VideoCamera(object):
	def __init__(self, cv2_index, cameraDetails, mysql):
		# Using OpenCV to capture from device identified by cv2_index.  Some laptops have a built in camera in addition
		# to the usb camera we are using and these cameras are assigned an integer value starting with 0
		self.cameraDetails = cameraDetails # the db info about this particular camera - see CameraDbRow for more info
		self.mysql = mysql # mysql db reference
		self.shutItDown = False # as long as this flag is false the camer will keep running
		self.camera = cv2.VideoCapture(int(cv2_index)) #a cv2 specific class for talking to camera hardware
		self.net = cv2.dnn.readNetFromCaffe("MobileNetSSD_deploy.prototxt.txt", "MobileNetSSD_deploy.caffemodel")
		# initialize the list of class labels MobileNet SSD was trained to
		# detect, then generate a set of bounding box colors for each class
		
		ret, self.no_video = cv2.imencode('.jpg', cv2.imread(os.path.realpath("./no_video.jpg"))); #set the no_video image to display when the camer is off
		self.jpeg = self.no_video
		self.capturing=False #the initial state is that no capturing is happening until the start method is activated
		self.lock = Lock() # a lock used when allowing access to the video feed by the browser
		self.tracked_list = [] # the list of currently tracked activities ( simultaneous people refrences )
		self.used_activity = [] # of the activities being tracked, on each frame this list keeps track of the activities that are still active, all other activities represent people who have left
		self.recently_left = None # this keeps track of the person that most recently left and is used to detect if they happen to return again to the same camera

	def __del__(self):
		self.camera.release()

	#given a activity id this method can load the corresponding row from the database into an ActivityDbRow instance
	#used when we are trying to determine if we are seeing the same recently left person return
	def loadActivityDb(self, id):
		a = ActivityDbRow()
		a.setID(id)
		cursor = self.mysql.connect().cursor()
		cursor.execute(a.getSelectStatement())
		data = cursor.fetchone()
		if data:
			a = ActivityDbRow(data)
		return a

	#insert a new activity in the tracking table
	#after the insert we must select the assigned id back into the activity record for future use
	def insertActivity(self, activity):
		conn = self.mysql.connect()
		cursor = conn.cursor()
		cursor.execute(activity.getInsertStatement())
		conn.commit()
		cursor = self.mysql.connect().cursor()
		# raw_time field is an alternate key that allows us to find the newly inserted row and get it's id
		sql = "select id from tracking where raw_time = '%s' and camera_id = %s" % (activity.getStart_time(), activity.getCamera_id())
		cursor.execute(sql)
		data = cursor.fetchone()
		if data:
			activity.setID(data[0])

	#update a preexisting activity in the tracking table
	def saveActivity(self, activity):
		if activity.getID():
			conn = self.mysql.connect()
			cursor = conn.cursor()
			cursor.execute(activity.getUpdateStatement())
			conn.commit()

	def saveRecoveredActivity(self, activity):
		if activity.getID():
			conn = self.mysql.connect()
			cursor = conn.cursor()
			cursor.execute("update tracking set end_time = null, next_camera_id = null, has_arrived = 'F' where id = %s" % activity.getID())
			conn.commit()

	#We use this to interact with the neural net data returned form cv2 to build up the list of starting rectangle coordinates for all detected people
	#this method is called up front to know ahead of the detection logic how many people we are dealing with
	def get_all_detected_points(self, detections, h, w):
		# filter out weak detections by ensuring the confidence is
		# greater than the minimum confidence 
		points = []
		for i in np.arange(0, detections.shape[2]):
			confidence = detections[0, 0, i, 2]
			if confidence > 0.2:
				idx = int(detections[0, 0, i, 1])
				if confidence > 0.5 and (idx == 15): # at this point we know we are dealing with a person ( see similar logic below with comments )
					box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
					points.append(box.astype("int")[0:2])

		return points
		
	# look for a face inside the rectangle bounding a person.
	# using the location of the face, find a smaller region 
	# rougly where the chest should be to detect shirt color
	# def identify(self, sub_frame, cv2):
	# 	BLUE=(255, 0, 0)
	# 	SHIRT_DY = 1.75;	# Distance from top of face to top of shirt region, based on detected face height.
	# 	SHIRT_SCALE_X = 0.6;	# Width of shirt region compared to the detected face
	# 	SHIRT_SCALE_Y = 0.6;	# Height of shirt region compared to the detected face
	# 	label = None
	# 	try:
	# 		gray = cv2.cvtColor(sub_frame, cv2.COLOR_BGR2GRAY)
	# 		gray = cv2.GaussianBlur(gray, (21, 21), 0)
	# 		face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_alt2.xml')
	# 		faces = face_cascade.detectMultiScale(gray, 1.3, 5)
	# 		for (x,y,w,h) in faces:
	# 			x = x + int(0.5 * (1.0-SHIRT_SCALE_X) * w);
	# 			y = y + int(SHIRT_DY * h) + int(0.5 * (1.0-SHIRT_SCALE_Y) * h);
	# 			w = int(SHIRT_SCALE_X * w);
	# 			h = int(SHIRT_SCALE_Y * h);
	# 			cv2.rectangle(sub_frame, (x, y), (x+w, y+h), BLUE, 1)
	# 			label = "Person %s" % self.getIdentitiyCode(sub_frame[y:(y+h),x:(x+w)])
	# 			print(label)
	# 	except Exception:
	# 		None
	# 	return label


	def identify(self, sub_frame, cv2):
		BLUE=(255, 0, 0)
		SHIRT_DY = 1.75;	# Distance from top of face to top of shirt region, based on detected face height.
		SHIRT_SCALE_X = 0.6;	# Width of shirt region compared to the detected face
		SHIRT_SCALE_Y = 0.6;	# Height of shirt region compared to the detected face
		label = None
		# Convert the image from BGR color (which OpenCV uses) to RGB color (which face_recognition uses)
		rgb_frame = sub_frame[:, :, ::-1]

		# Find all the faces and face enqcodings in the frame of video
		face_locations = face_recognition.face_locations(rgb_frame)
		face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
		# Loop through each face in this frame of video
		for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
			x = left
			y = top
			w = right-left
			h = bottom-top
			x = x + int(0.5 * (1.0-SHIRT_SCALE_X) * w);
			y = y + int(SHIRT_DY * h) + int(0.5 * (1.0-SHIRT_SCALE_Y) * h);
			w = int(SHIRT_SCALE_X * w);
			h = int(SHIRT_SCALE_Y * h);
			cv2.rectangle(sub_frame, (x, y), (x+w, y+h), BLUE, 1)
			label = "Person %s" % self.getIdentitiyCode(sub_frame[y:(y+h),x:(x+w)])

		return label

	def saveActivityLabel(self, t):
		conn = self.mysql.connect()
		cursor = conn.cursor()
		print("saving %s", t.getLabel())
		cursor.execute("update tracking set label = '%s' where id = %s" % (t.getLabel(), t.getID()))
		conn.commit()

	#given a subregion ( at chest level ) we calculate the average pixel color and then
	# use that to index down to a numeric value in the range of 1-6.
	def getIdentitiyCode(self, img):
		avg_color_per_row = np.average(img, axis=0)
		avg_color = np.average(avg_color_per_row, axis=0)
		(b, g, r) = avg_color
		print("%s %s %s" % (r, g, b))
		if r < 128 and b < 128 and g < 128:
			return 1
		elif r > 200 and b > 200 and g > 200:
			return 2
		elif r > b and r > g:
			return 3
		elif b > g and b > r:
			return 4
		elif g > b and g > r:
			return 5
		else:
			return 6

	#start contains the main camera loop and is called by our background thread - see main.py for how it gets called
	def start(self):
		GREEN = (0,255,0) # a color value for drawing our green boxes
		BLUE=(0, 0, 255)
		#each loop is a frame of video - do we see people in this frame?
		while self.camera.isOpened(): # loop until the camer is closed
			self.used_activity = [] # initialize to an empty list on each frame
			if self.shutItDown: # when this flag is true we shutdown camera and then the loop exits
				self.camera.release()
				break

			self.capturing = True # indicate to the outside world that we are capturing a feed from the video hardware
			(grabbed, frame) = self.camera.read() #read a frame of video from cv2 camera instance
			if not grabbed: # if no frame is returned this will be false and we'll loop back to the top of the while loop
				continue
			# grab the frame from the threaded video stream and resize it
			# to have a maximum width of 400 pixels
			frame = imutils.resize(frame, width=400)

			# grab the frame dimensions and convert it to a blob
			(h, w) = frame.shape[:2]
			blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)),
				0.007843, (300, 300), 127.5)

			# pass the blob through the network and obtain the detections and
			# predictions
			self.net.setInput(blob)
			detections = self.net.forward()
			# count how many people we are tracking up front here
			all_detected_points = self.get_all_detected_points(detections, h, w)
			# initialize detected value of the activities we are tracking to false up front and those that are 
			# still false at the end of the loop are activities we may no longer be observiing
			for t in self.tracked_list:
				t.set_detected(False)

			# loop over the detections
			for i in np.arange(0, detections.shape[2]):
				# extract the confidence (i.e., probability) associated with
				# the prediction
				confidence = detections[0, 0, i, 2]

				# filter out weak detections by ensuring the `confidence` is
				# greater than the minimum confidence
				if confidence > 0.2:
					# extract the index of the class label from the
					# `detections`, if it's 15 then we know it's a person
					idx = int(detections[0, 0, i, 1])
					# the rectangle bounding the person
					box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
					#extract into variables
					(startX, startY, endX, endY) = box.astype("int")
					if confidence > 0.5 and (idx == 15):
						#we've found a person with a confidence level greater than 50 percent
						rect_start = (startX, startY) # rectangle start coordinate upper left
						rect_end = (endX, endY) # rectangle end coordinate - lower right

						#we use this function call to associate the bounding box we are working on 
						#right now with the closest activity from the previous frame
						#if no previous activities are being tracked then a new activity is created
						newLabel = self.identify(frame[startY:endY,startX:endX], cv2)
						t = self.find_closest_tracked_activity(rect_start, newLabel, all_detected_points)
						#only use a label if we found one
						if newLabel != None:
							t.setLabel(newLabel)
							self.saveActivityLabel(t)
						t.set_detected(True) # mark it as being detected so we know it's an active tracking
						t.setRect_start(rect_start)
						t.setRect_end(rect_end)
						# draw the prediction on the frame
						label = "{}: {:.2f}%".format(t.getLabel(), confidence * 100)
						cv2.rectangle(frame, rect_start, rect_end, GREEN, 2)

						y = startY - 15 if startY - 15 > 15 else startY + 15
						cv2.putText(frame, label, (startX, y),
							cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREEN, 2)

			time.sleep(.1) # performance enhancement to only grab a frame once per 100 milliseconds ( 10 frames per second )
			
			# this logic tries to determine who left the camera
			removed_from_tracking=[]
			# loop over everthing we are currently tracking
			for t in self.tracked_list:
				if not t.was_detected(): #we think this one is gone
					#guard againest false positives 'person should not have been in view for only 2 seconds'
					if time.time() - t.getStart_time() > 2:
						#which way did they go?
						if self.went_left(t):
							print("went left heading to %s" % self.cameraDetails.left_camera_id)
							t.setNext_camera_id(self.cameraDetails.left_camera_id)
							removed_from_tracking.append(t)
						elif self.went_right(t):
							print("went right heading to %s" % self.cameraDetails.right_camera_id)
							t.setNext_camera_id(self.cameraDetails.right_camera_id)
							removed_from_tracking.append(t)
				elif t.has_left_the_scene():
					#if someone leaves view and we don't detect it correctly, mark them arrived and remove from tracking
					#the threshold for this is 5 times through the loop and we don't see them
					t.set_has_arrived(True)
					removed_from_tracking.append(t)

			# now we can remove all activities that are truly gone and save them in the db
			# this has to be done separate than the above loop because we can't modify the list 
			# we are activly looping over
			for t in removed_from_tracking:
				#remove tracked entries from tacked_list that were in removed_from_tracking list
				self.saveActivity(t)
				t.setEnd_time(time.time())
				self.recently_left = t
				del self.tracked_list[self.tracked_list.index(t)]

			#update the jpeg that we serve back to clients
			self.lock.acquire()
			ret, self.jpeg = cv2.imencode('.jpg', frame)
			self.lock.release()

		#while loop has exited so we are no longer capturing video, set the jpeg to the no_video image
		self.capturing=False
		self.lock.acquire()
		self.jpeg = self.no_video
		self.lock.release()
	print('camera released.')

	# used to get an integer identifier for a new tracked person
	def get_next_person_number(self):
		conn = self.mysql.connect()
		cursor = conn.cursor()
		cursor.execute("select count(distinct label) from tracking")
		data = cursor.fetchone()
		if data:
			return int(data[0]) + 1

	# get the label to display and to store in the tracking table
	def get_label(self):
		conn = self.mysql.connect()
		cursor = conn.cursor()
		camera_id = self.cameraDetails.getID()
		l = "Unknown"
		#try to find the original label for this tracked person rather than creating a new label
		#the label for an activity record (for this camera) that indicates that someone is supposed to arrive but hasn't, needs to be used as the label if one is found
		#because we predicted someone would arrive and now someone has, we are assuming it's the same person so reuse the label
		cursor.execute("SELECT id, label from tracking where next_camera_id is not null and next_camera_id = %s and has_arrived = 'F' order by start_time asc limit 1" % (camera_id))
		data = cursor.fetchone()
		if data:
			previous_id = data[0]
			# use this label instead of the one we were going to use
			l = data[1]
			#update the prediction logic so that the yellow indicator turns off at the same time the motion indicator turns on at this camera
			if previous_id:
				conn.cursor().execute("update tracking set has_arrived = 'T' where id = %d" % previous_id)
				conn.commit()
		return l

	#method to find a tracking activity record that corresponds with the person detected in this frame represented by rect_start and newLabel
	def find_closest_tracked_activity(self, rect_start, newLabel, all_detected_points):
		#populate a variable with the number of detected people in frame at this time
		detected_person_count = len(all_detected_points)
		#remove rect_start from all_detected_points - any points in the list that are not rect_start are kept by this lambda expression
		all_detected_points_except_this_one = list(filter(lambda x: x[0] != rect_start[0] or x[1] != rect_start[1], all_detected_points))
		#find all the traced activities not yet paired up with a person in this frame
		self.unused_tracked_list = list(set(self.tracked_list) - set(self.used_activity))
		# if list is empty then just add a new activity
		if not self.tracked_list:
			return self.begin_new_tracking(rect_start)
		else:
			# otherwise use the distance formula to find the tracked activity that is closest to this new point
			closest_t = None
			for t in self.unused_tracked_list:
				if closest_t:
					#first find the next closest match
					closest_t = t if distance(t.getRect_start(), rect_start) < distance(closest_t.getRect_start(), rect_start) else closest_t
					#use if the labels match.  This keeps a "swap" from happening when multiple people are close together
					if newLabel != None and closest_t.getLabel() == newLabel:
						self.used_activity.append(closest_t)
						return closest_t # just return this one because it must be the match
				else:
					closest_t = t

			#we might not want to use this one if it's closer to someone else
			#and we are tracking more than one person
			more_people_than_activities = detected_person_count > len(self.tracked_list)
			#if the activity found above is actually closer to one of the other people in frame, then don't pair it to this person, instead create a new one
			if not closest_t or (more_people_than_activities and self.is_this_activity_closer_to_someone_else(closest_t, all_detected_points_except_this_one, rect_start)):
				print(more_people_than_activities)
				print(closest_t)
				closest_t = self.begin_new_tracking(rect_start)

			#mark it as used here so that the next pass through the detection loop above, we don't try to use it again
			self.used_activity.append(closest_t)
			return closest_t

	#search through the list "the_others" and find any matches that are closer to "activity" than "me"
	def is_this_activity_closer_to_someone_else(self, activity, the_others, me):
		#closeness is determined by using the upper left rectangle coordinates and the distance formula
		activity_rect = activity.getRect_start()
		#find the distance between me and the activity that I am being matched with
		distance_to_me = distance(activity_rect, me)
		# use that distance to filter out other matches that are closer
		matches = list(filter(lambda x: distance(activity_rect, x) < distance_to_me, the_others))
		return len(matches) > 0 # if any were found, return true otherwise false

	#begin a new ActivityDbRow instance to track a new person in frame
	def begin_new_tracking(self, rect_start):
		t = None
		#see if a recently leaving activity has returned
		if self.recently_left:
			d = distance(rect_start, self.recently_left.getRect_start())
			# did they return close to where they left?
			if d < 100 and time.time() - self.recently_left.getEnd_time() < 6: # did they return in a reasonable amount of time?
			
				#check to see if they've arrived at their expected destination before trying to reuse here
				#if they arrived at the predicted camera then they are probably not returning to this one
				a = self.loadActivityDb(self.recently_left.getID())
				if not a.get_has_arrived():
					#since that is not the case, lets reuse the previous tracking record and unset the end time and predicted next camera
					t = self.recently_left
					t.setEnd_time(None)
					t.setNext_camera_id(None)
					self.saveRecoveredActivity(t)

				#blank out the recently_left field to indicate that we no longer expect someone to return soon
				self.recently_left = None

		#if no previous activity found then create a new one
		if not t:
			t = ActivityDbRow()
			t.setCamera_id(self.cameraDetails.getID())
			t.setLabel(self.get_label())
			t.setRect_start(rect_start)
			t.setStart_time(time.time())
			self.insertActivity(t)


		#keep track of the activity
		self.tracked_list.append(t)
		
		return t

	#this simple calculation decides if a recently leaving person went left based on the fact that their 
	# bottom right x coordinate is greater than the mid point of the frame
	def went_left(self, activity):
		return (activity.getRect_end()[0] > 200)

	#this simple calculation decides if a recently leaving person went right based on the fact that their 
	# top left x coordinate is less than the mid point of the frame
	def went_right(self, activity):
		return (activity.getRect_start()[0] < 200)

	#method called from flask main to toggle a flag causing the start "while" loop to exit and shut down the camera
	def stop(self):
		self.shutItDown = True

	# getter method fir the capturing boolean field
	def is_capturing(self):
		return self.capturing

	# when the browser "polls" the flask app for a frame of video, it is retrieved by calling this method
	# We use a "lock" here because jpeg might be in the middle of an update by the camera thread even
	# at the same time that the browser is trying to access it.
	def get_frame(self):
		self.lock.acquire()
		bytes = self.jpeg.tobytes()
		self.lock.release()
		return bytes
