#!/usr/bin/env python

import rospkg
from gazebo_msgs.srv import SpawnModel
from geometry_msgs.msg import Pose
from yaml import load
from tf.transformations import quaternion_from_euler
from math import pi
import random
import std_msgs.msg
import rospy, sys, numpy as np
import geometry_msgs.msg
import moveit_msgs.msg
import time

from std_msgs.msg import Header
from std_msgs.msg import Bool
from std_srvs.srv import Empty
from time import sleep


import group_interface

def gripper_on():
    # Wait till the srv is available
    rospy.wait_for_service('/ur5/vacuum_gripper/on')
    try:
        # Create a handle for the calling the srv
        turn_on = rospy.ServiceProxy('/ur5/vacuum_gripper/on', Empty)
        # Use this handle just like a normal function and call it
        resp = turn_on()
        return resp
    except rospy.ServiceException, e:
        print "Service call failed: %s" % e

def gripper_off():
    rospy.wait_for_service('/ur5/vacuum_gripper/off')
    try:
        turn_off = rospy.ServiceProxy('/ur5/vacuum_gripper/off', Empty)
        resp = turn_off()
        return resp
    except rospy.ServiceException, e:
        print "Service call failed: %s" % e

def callback(message):

    global matriz
    matriz = np.matrix(message.data)
    return matriz


def callback2(message2):

    if message2.data == 90 or message2.data == -90:
        rospy.loginfo("STOP ROBOT (%s)", message2.data)
    elif message2.data == 0:
        rospy.loginfo("ROBOT WORKING (%s)", message2.data)  
        print(matriz)
    else:
        rospy.loginfo("ERROR (invalid entry)")

def simple_subscriber():
    # create a subscriber by defining the topic name, the message class and a function to call when data is received (callback)

    matrix_topic = rospy.Subscriber("/chatter", std_msgs.msg.String,callback) 

    phone_topic = rospy.Subscriber("/device/screen_orientation", std_msgs.msg.Int32, callback2)

    # register client node with the master under the specified name
    rospy.init_node("node_subscriber", anonymous=False)
    # blocks program until ROS node is shutdown
    rospy.spin()


class Model(object):
    def __init__(self, **entries): 
        self.__dict__.update(entries)

    def __repr__(self):
       return '{}({!r}, {!r}, {!r})'.format(
           self.__class__.__name__,
           self.name,self.type,self.package)

    def __unicode__(self):
        return u'name: %s, type: %s, package: %s' % (self.name,self.type,self.package)

    def __str__(self):
        return unicode(self).encode('utf-8')

def rename_duplicates( old ):
    """
    Append count numbers to duplicate names in a list
    So new list only contains unique names
    """
    seen = {}
    for x in old:
        if x in seen:
            seen[x] += 1
            yield "%s_%d" % (x, seen[x])
        else:
            seen[x] = 0
            yield x

def parse_yaml(package_name,yaml_relative_path):
    """ Parse a yaml into a dict of objects containing all data to spawn models
        Args:
        name of the package (string, refers to package where yaml file is located)
        name and path of the yaml file (string, relative path + complete name incl. file extension)
        Returns: dictionary with model objects
    """
    complete_path = rospkg.RosPack().get_path(package_name)+yaml_relative_path
    f = open(complete_path, 'r')
    # populate dictionary that equals to the yaml file tree data
    yaml_dict = load(f)

    # create a list of the names of all models parsed
    modelNames = [yaml_dict['models'][k]['name'] for k in range(len(yaml_dict['models']))]
    # create new list with count numbers on all names that were duplicated
    modelNamesUnique = list(rename_duplicates(modelNames))
    
    rospy.loginfo("List of model names: %s" % modelNamesUnique)
    rospy.logdebug("Total number of models: ", len(yaml_dict['models']))

    # create a dict of Model objects where each key is the name of the model
    model_dict = {name: Model() for name in modelNamesUnique}
    # create list containing all nested dictionaries that hold data about each model   
    list_of_dict = [x for x in yaml_dict['models']]
    # parse YAML dictionary entries to Model class object attributes
    for idx, name in enumerate(modelNamesUnique):
        args = list_of_dict[idx]
        model_dict[name] = Model(**args)

    # add a unique model name that can be used to spawn an model in simulation
    count = 0
    for dict_key, mod_obj in model_dict.iteritems():
        mod_obj.unique_name = modelNamesUnique[count] # add attribute 'unique_name'
        count += 1

    return model_dict

def spawn_model(model_object):
    """ Spawns a model in a particular position and orientation
        Args:
        - model object containing name, type, package and pose of the model
        Returns: None
    """
    ## unpack object attributes
    package_name = model_object.package
    spawn_pose = Pose()
    #spawn_pose.position.x = model_object.pose[0]
    spawn_pose.position.x = 0 #round(random.uniform(-0.4,0.4),3)
    #spawn_pose.position.y = model_object.pose[1]
    spawn_pose.position.y =  -1.00755#round(random.uniform(-0.8851,-1.13),3)
    #spawn_pose.position.z = model_object.pose[2]
    spawn_pose.position.z = 0.91
    # conversion from Euler angles (RPY) in degrees to radians
    degrees2rad = pi / 180.0
    roll = model_object.pose[3] * degrees2rad
    pitch = model_object.pose[4] * degrees2rad
    yaw = model_object.pose[5] * degrees2rad
    # create list that contains conversion from Euler to Quaternions
    quat = quaternion_from_euler (roll,pitch,yaw)
    spawn_pose.orientation.x = quat[0]
    spawn_pose.orientation.y = quat[1]
    spawn_pose.orientation.z = random.random()
    spawn_pose.orientation.w = quat[3]
    
    # Spawn SDF model
    if model_object.type == 'sdf':
        try:
            model_path = rospkg.RosPack().get_path(package_name)+'/models/'
            model_xml = ''
        except rospkg.ResourceNotFound as e:
            rospy.logerr("Cannot find package [%s], check package name and that package exists, error message:  %s"%(package_name, e))

        try:
            with open(model_path + model_object.name + '/model.sdf', 'r') as xml_file:
                model_xml = xml_file.read().replace('\n', '')
        except IOError as err:
            rospy.logerr("Cannot find or open model [1] [%s], check model name and that model exists, I/O error message:  %s"%(model_object.name,err))
        except UnboundLocalError as error:
            rospy.logdebug("Cannot find package [%s], check package name and that package exists, error message:  %s"%(package_name, error))

        try:
            rospy.logdebug("Waiting for service gazebo/spawn_sdf_model")
            # block max. 5 seconds until the service is available
            rospy.wait_for_service('gazebo/spawn_sdf_model',5.0)
            # create a handle for calling the service
            spawn_model_prox = rospy.ServiceProxy('gazebo/spawn_sdf_model', SpawnModel)
        except (rospy.ServiceException, rospy.ROSException), e:
            rospy.logerr("Service call failed: %s" % (e,))

    elif model_object.type == "urdf":
        try:
            model_path = rospkg.RosPack().get_path(package_name)+'/urdf/'
            file_xml = open(model_path + model_object.name + '.' + model_object.type, 'r')
            model_xml = file_xml.read()
        except IOError as err:
            rospy.logerr("Cannot find model [2] [%s], check model name and that model exists, I/O error message:  %s"%(model_object.name,err))
        except UnboundLocalError as error:
            rospy.logdebug("Cannot find package [%s], check package name and that package exists, error message:  %s"%(package_name, error))

        try:
            rospy.logdebug("Waiting for service gazebo/spawn_urdf_model")
            # block max. 5 seconds until the service is available
            rospy.wait_for_service('gazebo/spawn_urdf_model')
            # create a handle for calling the service
            spawn_model_prox = rospy.ServiceProxy('/gazebo/spawn_urdf_model', SpawnModel)
        except (rospy.ServiceException, rospy.ROSException), e:
            rospy.logerr("Service call failed: %s" % (e,))

    else:
        rospy.logerr("Error: Model type not know, model_type = " + model_object.type)

    try:
        # use handle / local proxy just like a normal function and call it
        print "Now spawning: %s" % model_object.unique_name
        res = spawn_model_prox(model_object.unique_name,model_xml, '',spawn_pose, 'world')
        # evaluate response
        if res.success == True:
            # SpawnModel: Successfully spawned entity 'model_name'
            rospy.loginfo(res.status_message + " " + model_object.name + " as " + model_object.unique_name)
        else:
            rospy.logerr("Error: model %s not spawn, error message = "% model_object.name + res.status_message)
    except UnboundLocalError as error:
        rospy.logdebug("Cannot find package [%s], check package name and that package exists, error message:  %s"%(package_name, error))


# entry point to the program
if __name__ == "__main__":

    for value in range(1000): 

        #simple_subscriber()
        #if message2.data == 90 or message2.data == -90:     

        interface = group_interface.GroupInterface()

        # ROS node initialization
        #rospy.init_node('object_spawner_node', log_level=rospy.INFO)

        ###### usage example
        
        # retrieve node configuration variables from param server
        yaml_package_name = rospy.get_param('~yaml_package_name', 'object_spawner')
        yaml_relative_path = rospy.get_param('~yaml_relative_path', '/config/models03.yaml')
        random_order = rospy.get_param('~random_order', 'true')
        #time_interval = rospy.get_param('~time_interval', 1.0)
        # parse yaml file to dictionary of Model objects
        m = parse_yaml(yaml_package_name,yaml_relative_path) # create dict called 'm'




    ## spawn a random model parsed from yaml file
        
        for key in random.sample(m.keys(), len(m)):
            spawn_model(m[key])
            # remove item form dict
            del m[key]
            break
            # sleep for duration (seconds, nsecs)
            #d = rospy.Duration(time_interval)
                #rospy.sleep(d)
                # to silence "sys.excepthook is missing" error
            #sys.stdout.flush() 
        ####
        ####
        ####

        

        print("")
        print("MoveIt group: manipulator")
        print("Current joint states (radians): {}".format(interface.get_joint_state("manipulator")))
        print("Current joint states (degrees): {}".format(interface.get_joint_state("manipulator", degrees=True)))
        print("Current cartesian pose: {}".format(interface.get_cartesian_pose("manipulator")))

        print("")
        print("MoveIt group: endeffector")
        print("Current joint states (meters): {}".format(interface.get_joint_state("endeffector")))
        print("Current cartesian pose: {}".format(interface.get_cartesian_pose("endeffector")))



        # print("Planning group: manipulator")
        # print("  |-- Adjusting pose for the camera calibration...")
        # interface.reach_joint_state("manipulator", [30, -90, 90, 0, 0, -20], degrees=True)

        # print("Planning group: manipulator")
        # print("  |-- Adjusting pose for the camera calibration...")
        # interface.reach_joint_state("manipulator", [25, -90, 90, 0, 5, -20], degrees=True)

        print("Planning group: manipulator")
        print("  |-- Adjusting pose for the camera calibration...")
        interface.reach_joint_state("manipulator", [35, -90, 90, 0, -5, -20], degrees=True)

        exit()
        print("  |-- Reaching Home...")
        interface.reach_joint_state("manipulator", [30, -90, 90, 0, 0, 0], degrees=True)

        

        # APPROACH GRIPPER TO PIECE
        print("  |-- Locating piece...")
        pose = interface.get_cartesian_pose("manipulator")
        pose.position.x = 0
        pose.position.y = -1.00755
        pose.position.z = 1
        interface.reach_cartesian_pose("manipulator", pose)
        gripper_on()
        sleep(1)
        # APPROACH HOME
        print("  |-- Reaching Home...")
        interface.reach_joint_state("manipulator", [30, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)

        # APPROACH GRIPPER TO YELLOW BIN
        print("  |-- Approaching Yellow Bin Position...")
        interface.reach_joint_state("manipulator", [90, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)
        print("  |-- Placing the piece in the Yellow bin...")
        pose = interface.get_cartesian_pose("manipulator")
        pose.position.x = 0.6
        pose.position.y = -0.42
        pose.position.z = 1.05
        interface.reach_cartesian_pose("manipulator", pose)
        gripper_off()
        sleep(1)
        # APPROACH HOME
        print("  |-- Reaching Home...")
        interface.reach_joint_state("manipulator", [30, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)
        
        for key in random.sample(m.keys(), len(m)):
            spawn_model(m[key])
            # remove item form dict
            del m[key]
            break
        sleep(0.5)

        # APPROACH GRIPPER TO PIECE
        print("  |-- Locating piece...")
        pose = interface.get_cartesian_pose("manipulator")
        pose.position.x = 0
        pose.position.y = -1.00755
        pose.position.z = 1
        interface.reach_cartesian_pose("manipulator", pose)
        gripper_on()
        sleep(1)
        # APPROACH HOME
        print("  |-- Reaching Home...")
        interface.reach_joint_state("manipulator", [30, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)

        # APPROACH GRIPPER TO BLUE BIN
        print("  |-- Approaching Blue Bin Position...")
        interface.reach_joint_state("manipulator", [145, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)
        print("  |-- Placing the piece in the Blue bin...")
        pose = interface.get_cartesian_pose("manipulator")
        pose.position.x = 0.6
        pose.position.y = 0.11
        pose.position.z = 1.05
        interface.reach_cartesian_pose("manipulator", pose)
        gripper_off()
        sleep(1)
        # APPROACH HOME
        print("  |-- Reaching Home...")
        interface.reach_joint_state("manipulator", [30, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)

        for key in random.sample(m.keys(), len(m)):
            spawn_model(m[key])
            # remove item form dict
            del m[key]
            break
        sleep(0.5)


        # APPROACH GRIPPER TO PIECE
        print("  |-- Locating piece...")
        pose = interface.get_cartesian_pose("manipulator")
        pose.position.x = 0
        pose.position.y = -1.00755
        pose.position.z = 1
        interface.reach_cartesian_pose("manipulator", pose)
        gripper_on()
        sleep(1)
        # APPROACH HOME
        print("  |-- Reaching Home...")
        interface.reach_joint_state("manipulator", [30, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)

        # APPROACH GRIPPER TO GREEN BIN
        print("  |-- Approaching Green Bin Position...")
        interface.reach_joint_state("manipulator", [-60, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)
        print("  |-- Placing the piece in the Green bin...")
        pose = interface.get_cartesian_pose("manipulator")
        pose.position.x = -0.6
        pose.position.y = -0.42
        pose.position.z = 1.05
        interface.reach_cartesian_pose("manipulator", pose)
        gripper_off()
        sleep(1)
        # APPROACH HOME
        print("  |-- Reaching Home...")
        interface.reach_joint_state("manipulator", [30, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)

        for key in random.sample(m.keys(), len(m)):
            spawn_model(m[key])
            # remove item form dict
            del m[key]
            break
        sleep(0.5)

        # APPROACH GRIPPER TO PIECE
        print("  |-- Locating piece...")
        pose = interface.get_cartesian_pose("manipulator")
        pose.position.x = 0
        pose.position.y = -1.00755
        pose.position.z = 1
        interface.reach_cartesian_pose("manipulator", pose)
        gripper_on()
        sleep(1)
        # APPROACH HOME
        print("  |-- Reaching Home...")
        interface.reach_joint_state("manipulator", [30, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)
       
        # APPROACH GRIPPER TO BROWN BIN
        print("  |-- Approaching Brown Bin Position...")
        interface.reach_joint_state("manipulator", [-110, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)
        print("  |-- Placing the piece in the Blue bin...")
        pose = interface.get_cartesian_pose("manipulator")
        pose.position.x = -0.6
        pose.position.y = 0.11
        pose.position.z = 1.05
        interface.reach_cartesian_pose("manipulator", pose)
        gripper_off()
        sleep(1)
        # APPROACH HOME
        print("  |-- Reaching Home...")
        interface.reach_joint_state("manipulator", [30, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)
     
        for key in random.sample(m.keys(), len(m)):
            spawn_model(m[key])
            # remove item form dict
            del m[key]
            break
        sleep(0.5)
      
        # APPROACH GRIPPER TO PIECE
        print("  |-- Locating piece...")
        pose = interface.get_cartesian_pose("manipulator")
        pose.position.x = 0
        pose.position.y = -1.00755
        pose.position.z = 1
        interface.reach_cartesian_pose("manipulator", pose)
        gripper_on()
        sleep(1)
        # APPROACH HOME
        print("  |-- Reaching Home...")
        interface.reach_joint_state("manipulator", [30, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)    

        # APPROACH GRIPPER TO DISCARD BIN
        print("  |-- Approaching Discard Bin Position...")
        interface.reach_joint_state("manipulator", [-160, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)
        print("  |-- Placing the piece in the Discard bin...")
        pose = interface.get_cartesian_pose("manipulator")
        pose.position.x = 0.014
        pose.position.y = 0.45
        pose.position.z = 1.2
        interface.reach_cartesian_pose("manipulator", pose)
        gripper_off()
        sleep(1)
        # APPROACH HOME
        print("  |-- Reaching Home...")
        interface.reach_joint_state("manipulator", [30, -90, 90, 0, 0, 0], degrees=True)  
        sleep(0.5)



        # APPROACH HOME
        print("  |-- Adjusting pose for the camera calibration...")
        interface.reach_joint_state("manipulator", [30, -90, 90, 0, 0, -20], degrees=True)
        
        sleep(1) 
