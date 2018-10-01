drop SCHEMA if exists securedb;

CREATE SCHEMA securedb;

USE securedb;

CREATE TABLE camera (
	id 						int primary key,
	camera_IP 		varchar(20),
	left_cam_id 	int,
	right_cam_id 	int,
	is_online 		char(1)
);

CREATE TABLE tracking (
	id 							int primary key AUTO_INCREMENT,
	label 					varchar(50),
	raw_time 				varchar(50),
	start_time 			datetime default current_timestamp,
	end_time 				datetime,
	camera_id 			int,
	next_camera_id 	int,
	has_arrived 		char(1)
);

grant all PRIVILEGES ON *.* to 'secuser'@'*' IDENTIFIED BY 'password';