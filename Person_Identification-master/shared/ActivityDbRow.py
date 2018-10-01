# 4/16 8:07pm JD - added has arrived attributes to keep track of when a tracked person arrives at the predicted camera

class ActivityDbRow(object):
	def __init__(self, row=None):
		# these values correspond with the columns in the database
		self.id = None
		self.label = None
		self.start_time = None
		self.end_time = None
		self.camera_id = None
		self.next_camera_id = None
		self.has_arrived = None

		# these values are used at runtime to track various aspects of the tracked person
		self.rect_start = None # the x,y upper left coordinate of the bounding rect
		self.rect_end = None # the x, y of the lower right ...
		self.detected = False # this value gets marked as true on each pass through the main camera loop until the person leaves and then becomes false
		self.not_detected_count = 0 #an additional value used to decide when a person has left the camera
		self.updateLabelCounter = 0
		if row: # when reconsituting from the database we will have a row of column values that we use to populate this instance
			self.id = row[0]
			self.label = row[1]
			self.start_time = row[2]
			self.end_time = row[3]
			self.camera_id = row[4]
			self.next_camera_id = row[5]
			self.has_arrived = True if row[6] and row[6] == 'T' else False

#below are general setter and getter methods for the above attributes
	def getID(self):
		return self.id

	def setID(self, id):
		self.id = id;

	def getLabel(self):
		return self.label

	def setLabel(self, label):
		if self.label == None or self.label == "Unknown":
			self.updateLabelCounter == 0
			self.label = label;
		elif self.updateLabelCounter == 5:
			self.updateLabelCounter == 0
			if label != "Unknown":
				self.label = label;
		else:
			self.updateLabelCounter += 1

	def getStart_time(self):
		return self.start_time

	def setStart_time(self, start_time):
		self.start_time = start_time;

	def getEnd_time(self):
		return self.end_time

	def setEnd_time(self, end_time):
		self.end_time = end_time;

	def getCamera_id(self):
		return self.camera_id

	def setCamera_id(self, camera_id):
		self.camera_id = camera_id;

	def getNext_camera_id(self):
		return self.next_camera_id

	def setNext_camera_id(self, next_camera_id):
		self.next_camera_id = next_camera_id;

	def get_has_arrived(self):
		return self.has_arrived

	def set_has_arrived(self, b):
		self.has_arrived =b 

	def getRect_start(self):
		return self.rect_start

	def setRect_start(self, point):
		self.rect_start = point

	def getRect_end(self):
		return self.rect_end

	def setRect_end(self, point):
		self.rect_end = point

	def set_detected(self, b):
		if b:
			self.not_detected_count = 0
		self.detected = b

	def was_detected(self):
		return self.detected

	#only if this gets called 5 times does it finally return true
	#it insures that we have indeed encountered an activity that
	#has left the camera but we don't know which way they went
	#five times = a half a second of time
	def has_left_the_scene(self):
		self.not_detected_count += 1
		return self.not_detected_count > 5

	#some basic sql methods for common operations on an activitydbrow
	def getSelectStatement(self):
		return "select id, label, start_time, end_time, camera_id, next_camera_id, has_arrived from tracking where id = %s" % self.id

	#when updating a tracking record we are only updating the end_time, next_camera_id and has_arrived columns
	def getUpdateStatement(self):
		return "update tracking set end_time = current_timestamp, next_camera_id = %s, has_arrived = '%s' where id = %s" % ((self.next_camera_id if self.next_camera_id else 'null'), 'T' if self.has_arrived else 'F', self.id)

	#when inserting we are populating the lable, camera_id, raw_time and has_arrived columns ( the database uses an auto increment id field that assigns the id )
	def getInsertStatement(self):
		return "insert into tracking (label, camera_id, raw_time, has_arrived) values('%s', %s, '%s', 'F')" % (self.label, (self.camera_id if self.camera_id else 'null'), self.start_time)
