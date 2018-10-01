# 4/11 7:36pm JD - added functions for prediction indicator

class CameraDbRow(object):
	def __init__(self, row=None):
		self.id = None
		self.ip = None
		self.left_camera_id = None
		self.right_camera_id = None
		self.is_online = None

		self.has_motion = False
		self.has_predicted_motion = False

		if row:
			self.id = row[0]
			self.ip = row[1]
			self.left_camera_id = row[2]
			self.right_camera_id = row[3]
			self.is_online = row[4] == 'T'

	def getID(self):
		return self.id

	def setID(self, id):
		self.id = id;

	def getIP(self):
		return self.ip

	def setIP(self, ip):
		self.ip = ip

	def getLeftCamera(self):
		return self.left_camera_id

	def setLeftCameraID(self, id):
		self.left_camera_id = id

	def getRightCameraID(self):
		return self.right_camera_id

	def setRightCameraID(self, id):
		self.right_camera_id = id

	def isOnline(self):
		return self.is_online

	def setIsOnline(self, online):
		self.is_online = online

	def getSelectStatement(self):
		return "select id, camera_IP, left_cam_id, right_cam_id, is_online from camera where id = %s" % self.id

	def getUpdateStatement(self):
		return "update camera set camera_IP = '%s', left_cam_id = %s, right_cam_id = %s, is_online = '%s' where id = %s" % (self.ip, (self.left_camera_id if self.left_camera_id else 'null'), (self.right_camera_id if self.right_camera_id else 'null'), ('T' if self.is_online  else 'F'), self.id)

	def getInsertStatement(self):
		return "insert into camera (id, camera_IP, left_cam_id, right_cam_id) values(%s, '%s', %s, %s)" % (self.id, self.ip, (self.left_camera_id if self.left_camera_id else 'null'), (self.right_camera_id if self.right_camera_id else 'null'))

	def hasMotion(self):
		return self.has_motion

	def setHasMotion(self, b):
		self.has_motion = b

	def hasPredictedMotion(self):
		return self.has_predicted_motion

	def setHasPredictedMotion(self, b):
		self.has_predicted_motion = b